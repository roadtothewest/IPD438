#!/usr/bin/env python3
"""Video lado a lado: SRT sin I-header | SRT con I-header, mismo flujo y mismos cortes (una semilla).

Repite las dos corridas de evaluate.py, decodifica con FFmpeg (como el espectador) y rotula cada cuadro:
  - su dSSIM (la métrica del informe, tomada de results/final) y si cuenta como artefacto visible;
  - "congelado" cuando el cuadro no llegó y se repite el anterior (durante el corte);
  - el cuadro en que el edge entrega el I-header (el primero en que los dos flujos difieren) y los IDR.
Uso: video_comparacion.py --seed 19 [--gop 90 --tag r200 --loss 0.04 --burst-ms 200] --out video.mp4
"""
import argparse, subprocess, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, N = 1280, 720, 30, 300
PW, PH, TOP, BOT = 960, 540, 56, 70
FONT = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
FONT_I = "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"
FONT_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def decode(path):
    cmd = ["ffmpeg", "-v", "error", "-threads", "1", "-flags", "+output_corrupt", "-i", str(path),
           "-fps_mode", "cfr", "-r", str(FPS), "-frames:v", str(N), "-vf", f"scale={PW}:{PH}:flags=area",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, PH, PW, 3)
    if len(a) < N:
        a = np.concatenate([a, np.repeat(a[-1:], N - len(a), 0)])
    return a

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--gop", type=int, default=90); ap.add_argument("--tag", default="r200")
    ap.add_argument("--loss", type=float, default=0.04); ap.add_argument("--burst-ms", type=float, default=200)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    S = root / "media" / f"gop{a.gop}"
    A, B = S / f"A_gop{a.gop}.h264", (S / "candidatos.txt").read_text().strip()
    res = root / "results" / "final" / f"gop{a.gop}"
    base = np.load(res / "base.npz")["ssim_src"]
    z = np.load(res / f"{a.tag}.npz")
    d = {c: base - z[f"{c}|{a.seed}"][2] for c in ("srt", "srt+ih")}

    vid = {}
    with tempfile.TemporaryDirectory() as tmp:
        for caso, mode in (("srt", "plain"), ("srt+ih", "ack")):
            ts = f"{tmp}/{caso}.ts"
            cmd = [str(root / "build" / "ihdr_sim"), "--a", str(A), "--mode", mode, "--out", ts, "--loss", str(a.loss),
                   "--burst-ms", str(a.burst_ms), "--seed", str(a.seed), "--latency-ms", "120", "--owd-ms", "15",
                   "--fps", str(FPS), "--frames", str(N), "--arq", "1"] + (["--b", B] if mode != "plain" else [])
            subprocess.run(cmd, check=True, capture_output=True)
            vid[caso] = decode(ts)
    dif = [k for k in range(N) if not np.array_equal(vid["srt"][k], vid["srt+ih"][k])]
    k_ih = dif[0] if dif else None
    congelado = {c: [k > 0 and np.array_equal(v[k], v[k - 1]) for k in range(N)] for c, v in vid.items()}

    f_t, f_s, f_i, f_b = (ImageFont.truetype(FONT, 30), ImageFont.truetype(FONT, 24),
                          ImageFont.truetype(FONT_I, 30), ImageFont.truetype(FONT_B, 22))
    WT, HT = 2 * PW + 12, TOP + PH + BOT
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WT}x{HT}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                            "-threads", "1", "-pix_fmt", "yuv420p", a.out], stdin=subprocess.PIPE)
    for k in range(N):
        img = Image.new("RGB", (WT, HT), (20, 20, 20))
        dr = ImageDraw.Draw(img)
        for j, caso in enumerate(("srt", "srt+ih")):
            x0 = j * (PW + 12)
            img.paste(Image.fromarray(vid[caso][k]), (x0, TOP))
            # título
            if caso == "srt":
                dr.text((x0 + 12, 12), "SRT sin ", font=f_t, fill="white")
            else:
                dr.text((x0 + 12, 12), "SRT con ", font=f_t, fill="white")
            w0 = dr.textlength("SRT sin " if caso == "srt" else "SRT con ", font=f_t)
            dr.text((x0 + 12 + w0, 12), "I-header", font=f_i, fill="white")
            # estado del cuadro
            v = float(d[caso][k])
            if congelado[caso][k]:
                txt, col = "congelado: el cuadro no llegó (corte de red)", (230, 150, 30)
            elif v > 0.05:
                txt, col = "artefacto visible", (215, 48, 39)
            else:
                txt, col = "sin artefacto", (90, 170, 90)
            y = TOP + PH + 10
            dr.rectangle([x0 + 12, y + 4, x0 + 30, y + 22], fill=col)
            dr.text((x0 + 40, y), f"{txt}    ΔSSIM = {v:.3f}".replace(".", ","), font=f_s, fill="white")
            # eventos sobre la imagen
            if k % a.gop == 0:
                dr.text((x0 + 14, TOP + 12), "IDR (intra)", font=f_b, fill="yellow", stroke_width=2, stroke_fill="black")
            if caso == "srt+ih" and k_ih is not None and k_ih <= k < k_ih + 45:
                dr.text((x0 + 14, TOP + 12), "llega el I-header", font=f_b, fill="yellow", stroke_width=2, stroke_fill="black")
        t = f"cuadro {k}   {k / FPS:5.2f} s   (GoP {a.gop}, SRT L = 120 ms, cortes de {a.burst_ms:.0f} ms, semilla {a.seed})"
        dr.text((12, HT - 30), t.replace(".", ","), font=f_s, fill=(170, 170, 170))
        enc.stdin.write(img.tobytes())
    enc.stdin.close(); enc.wait()
    print("guardado", a.out, "I-header en el cuadro", k_ih)

if __name__ == "__main__":
    main()
