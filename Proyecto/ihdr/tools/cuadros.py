#!/usr/bin/env python3
"""Cuadros reales del mismo flujo sin pérdida, con SRT y con SRT + I-header (misma semilla, mismos cortes).

Repite las corridas de evaluate.py para una semilla, decodifica con FFmpeg (como el espectador) y arma
una grilla: filas = instantes, columnas = sin pérdida | SRT | SRT + I-header. Sobre cada cuadro se escribe
su dSSIM (la métrica del informe), para comparar el número con lo que se ve.

Uso: cuadros.py --seed 19 --frames 80,86,96,130 [--extra 26:285] --out ../informe/cuadros.png
     --extra S:K agrega una fila con el cuadro K de la semilla S (p. ej. para mostrar una deriva).
"""
import argparse, subprocess, tempfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from evaluate import prep, ssim

W, H, FPS, N = 1280, 720, 30, 300
FS = W * H * 3 // 2

def sim(simbin, A, B, mode, seed, loss, burst, ts):
    cmd = [simbin, "--a", str(A), "--mode", mode, "--out", ts, "--loss", str(loss), "--burst-ms", str(burst),
           "--seed", str(seed), "--latency-ms", "120", "--owd-ms", "15", "--fps", str(FPS), "--frames", str(N), "--arq", "1"]
    if mode != "plain":
        cmd += ["--b", B]
    subprocess.run(cmd, check=True, capture_output=True)

def decode_sel(path, want):
    """Decodifica como evaluate.py y guarda solo los cuadros pedidos (yuv420p completo)."""
    cmd = ["ffmpeg", "-v", "error", "-threads", "1", "-flags", "+output_corrupt", "-i", str(path),
           "-fps_mode", "cfr", "-r", str(FPS), "-frames:v", str(N), "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    out, last, k = {}, None, 0
    while k < N:
        buf = p.stdout.read(FS)
        if len(buf) < FS:
            break
        last = buf
        if k in want:
            out[k] = buf
        k += 1
    p.wait()
    for j in want:  # lo que falta al final se congela, como en evaluate.py
        out.setdefault(j, last)
    return out

def rgb(buf):
    a = np.frombuffer(buf, np.uint8)
    y = a[:W * H].reshape(H, W).astype(np.float32)
    u = a[W * H:W * H * 5 // 4].reshape(H // 2, W // 2).repeat(2, 0).repeat(2, 1).astype(np.float32) - 128
    v = a[W * H * 5 // 4:].reshape(H // 2, W // 2).repeat(2, 0).repeat(2, 1).astype(np.float32) - 128
    c = 1.164 * (y - 16)  # BT.601, rango limitado
    return np.clip(np.stack([c + 1.596 * v, c - 0.392 * u - 0.813 * v, c + 2.017 * u], -1), 0, 255).astype(np.uint8)

def luma(buf):
    return np.frombuffer(buf, np.uint8)[:W * H].reshape(H, W)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--extra", default="", help="S:K[,S:K]: filas extra con el cuadro K de la semilla S")
    ap.add_argument("--gop", type=int, default=90)
    ap.add_argument("--loss", type=float, default=0.04); ap.add_argument("--burst-ms", type=float, default=200)
    ap.add_argument("--zoom", action="store_true", help="recorta la zona más dañada (en vez del cuadro entero)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    S = root / "media" / f"gop{a.gop}"
    A, B = S / f"A_gop{a.gop}.h264", (S / "candidatos.txt").read_text().strip()
    simbin = str(root / "build" / "ihdr_sim")
    src = np.memmap(root / "media" / "src720.yuv", np.uint8, "r", shape=(N, FS))

    filas = [(a.seed, int(k)) for k in a.frames.split(",")]
    filas += [(int(x.split(":")[0]), int(x.split(":")[1])) for x in a.extra.split(",") if x]
    ref = decode_sel(A, {k for _, k in filas})
    rec = {}
    with tempfile.TemporaryDirectory() as tmp:
        for seed in sorted({s for s, _ in filas}):
            want = {k for s, k in filas if s == seed}
            for caso, mode in (("srt", "plain"), ("srt+ih", "ack")):
                ts = f"{tmp}/{caso}.ts"
                sim(simbin, A, B, mode, seed, a.loss, a.burst_ms, ts)
                rec[(seed, caso)] = decode_sel(ts, want)

    cols = [("Sin pérdida", None), ("SRT", "srt"), ("SRT + $\\mathit{I}$-$\\mathit{header}$", "srt+ih")]
    plt.rcParams.update({"font.size": 8, "font.family": "serif", "mathtext.fontset": "custom",
                         "mathtext.rm": "serif", "mathtext.it": "serif:italic", "mathtext.cal": "serif"})
    fig, axs = plt.subplots(len(filas), 3, figsize=(7.16, 1.38 * len(filas) + 0.25), squeeze=False)
    for i, (seed, k) in enumerate(filas):
        fsrc = src[k][:W * H].reshape(H, W)
        s_ref = ssim(prep(fsrc), prep(luma(ref[k])))
        # zona más dañada (para --zoom): bloque de 320x180 con mayor error de SRT o SRT+IH frente a sin pérdida
        if a.zoom:
            err = np.maximum(np.abs(luma(rec[(seed, "srt")][k]).astype(int) - luma(ref[k])),
                             np.abs(luma(rec[(seed, "srt+ih")][k]).astype(int) - luma(ref[k])))
            bh, bw = 180, 320
            e = err[:H // bh * bh, :W // bw * bw].reshape(H // bh, bh, W // bw, bw).sum(axis=(1, 3))
            r0, c0 = np.unravel_index(np.argmax(e), e.shape)
            win = (slice(r0 * bh, r0 * bh + bh), slice(c0 * bw, c0 * bw + bw))
        for j, (titulo, caso) in enumerate(cols):
            buf = ref[k] if caso is None else rec[(seed, caso)][k]
            img = rgb(buf)
            d = 0.0 if caso is None else s_ref - ssim(prep(fsrc), prep(luma(buf)))
            ax = axs[i][j]
            ax.imshow(img[win] if a.zoom else img, interpolation="nearest" if a.zoom else "antialiased")
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_linewidth(0.4)
            if i == 0:
                ax.set_title(titulo, fontsize=9)
            if j == 0:
                ax.set_ylabel(f"cuadro {k}\n({k / FPS:.2f} s)".replace(".", ","), fontsize=8)
            if caso is not None:
                vis = d > 0.05
                ax.text(0.02, 0.04, f"ΔSSIM = {d:.3f}".replace(".", ","), transform=ax.transAxes, fontsize=7,
                        color="white", bbox=dict(boxstyle="square,pad=0.2", fc="#b2182b" if vis else "#333333", ec="none"))
    fig.tight_layout(pad=0.3, h_pad=0.4, w_pad=0.3)
    fig.savefig(a.out, dpi=200)
    print("guardado", a.out)

if __name__ == "__main__":
    main()
