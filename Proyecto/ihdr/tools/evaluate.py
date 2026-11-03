#!/usr/bin/env python3
"""Corre el emulador en varios escenarios con la MISMA historia de pérdidas y mide la calidad.

Métricas por escenario (Y de 4:2:0, un valor por frame):
  psnr_ref  : PSNR contra el mismo stream decodificado sin pérdida (lo que se degrada por la pérdida).
  psnr_src  : PSNR contra la fuente cruda (calidad total, incluye la compresión).
  dañados   : frames con psnr_ref < UMBRAL dB (35 por defecto: artefacto visible; la deriva del I-header queda ~40 dB).
  racha     : la racha más larga de frames dañados seguidos.
VMAF: no disponible en este ffmpeg (sin libvmaf); queda pendiente.
Uso: evaluate.py --src SRC.yuv --streams DIR --w 1280 --h 720 [--loss 0.02 --burst-ms 20 --latency-ms 120 --seeds 1,2,3]
"""
import argparse, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

def decode(ts_or_h264, w, h, fps, n):
    cmd = ["ffmpeg", "-v", "error", "-y", "-flags", "+output_corrupt", "-i", str(ts_or_h264),
           "-fps_mode", "cfr", "-r", str(fps), "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    fs = w * h * 3 // 2
    k = len(raw) // fs
    a = np.frombuffer(raw[:k * fs], np.uint8).reshape(k, fs)[:, :w * h]
    if k < n:  # lo que falta al final se congela
        pad = np.repeat(a[-1:] if k else np.zeros((1, w * h), np.uint8), n - k, axis=0)
        a = np.concatenate([a, pad])
    return a

def psnr(a, b):
    """PSNR por frame (luminancia, 8 bits). Frame a frame para no ocupar GB de memoria."""
    out = np.empty(len(a))
    for k in range(len(a)):
        d = a[k].astype(np.int32) - b[k].astype(np.int32)
        mse = float(np.mean(d * d))
        out[k] = 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)
    return out

def runs(bad):
    best = cur = 0
    for x in bad:
        cur = cur + 1 if x else 0
        best = max(best, cur)
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--streams", required=True)
    ap.add_argument("--sim", default=str(Path(__file__).resolve().parent.parent / "build" / "ihdr_sim"))
    ap.add_argument("--w", type=int, default=1280); ap.add_argument("--h", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30); ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--loss", type=float, default=0.02); ap.add_argument("--burst-ms", type=float, default=20)
    ap.add_argument("--latency-ms", type=int, default=120); ap.add_argument("--owd-ms", type=int, default=15)
    ap.add_argument("--seeds", default="1,2,3"); ap.add_argument("--umbral", type=float, default=35.0)
    ap.add_argument("--b", default=None, help="stream de I-headers (por defecto B_gop{long}_ih{n}.h264)")
    ap.add_argument("--latencies", default=None, help="latencias extra para plain90, ej. 250,500")
    ap.add_argument("--scenarios", default="udp,udp+ih,srt,srt+ih,srt_gop30")
    ap.add_argument("--udp-latency-ms", type=int, default=20)
    ap.add_argument("--save", default=None, help="prefijo para guardar resultados (.csv y .npz)")
    ap.add_argument("--long-gop", type=int, default=90); ap.add_argument("--short-gop", type=int, default=30)
    ap.add_argument("--ih-every", type=int, default=5)
    a = ap.parse_args()
    S = Path(a.streams); n = a.frames
    A = S / f"A_gop{a.long_gop}.h264"; C = S / f"C_gop{a.short_gop}.h264"; B = Path(a.b) if a.b else S / f"B_gop{a.long_gop}_ih{a.ih_every}.h264"
    src = np.fromfile(a.src, np.uint8, count=n * a.w * a.h * 3 // 2).reshape(n, -1)[:, :a.w * a.h]
    ref = {A: decode(A, a.w, a.h, a.fps, n), C: decode(C, a.w, a.h, a.fps, n)}
    # nombre: (modo, stream, I-headers, latencia, arq)
    sc = {"udp": ("plain", A, None, a.udp_latency_ms, 0),
          "udp+ih": ("report", A, B, a.udp_latency_ms, 0),
          "srt": ("plain", A, None, a.latency_ms, 1),
          "srt+ih": ("ack", A, B, a.latency_ms, 1),
          "srt+ih_rep": ("report", A, B, a.latency_ms, 1),
          "srt_gop30": ("plain", C, None, a.latency_ms, 1)}
    names = a.scenarios.split(",")
    for L in (a.latencies.split(",") if a.latencies else []):
        sc[f"srt@{L}"] = ("plain", A, None, int(L), 1); names.append(f"srt@{L}")
    print(f"pérdida={a.loss} ráfaga={a.burst_ms}ms latencia={a.latency_ms}ms owd={a.owd_ms}ms umbral={a.umbral}dB frames={n}")
    print(f"{'escenario':12s} {'seed':>4s} {'dañados':>8s} {'racha':>6s} {'psnr_ref':>9s} {'psnr_src':>9s} {'descart':>8s} {'kbps':>6s} {'retx':>5s} {'ih':>3s}")
    agg = {}; curves = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            mode, sa, sb, lat, arq = sc[name]
            for seed in a.seeds.split(","):
                out = f"{tmp}/{name}_{seed}.ts"
                cmd = [a.sim, "--a", str(sa), "--mode", mode, "--out", out, "--loss", str(a.loss), "--burst-ms", str(a.burst_ms),
                       "--seed", seed, "--latency-ms", str(lat), "--owd-ms", str(a.owd_ms), "--fps", str(a.fps),
                       "--frames", str(n), "--ih-every", str(a.ih_every), "--arq", str(arq)]
                if sb: cmd += ["--b", str(sb)]
                log = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
                info = {}
                for line in log.splitlines():
                    for tok in line.replace(":", " ").replace("(", " ").replace(")", " ").split():
                        if "=" in tok: k, v = tok.split("="); info[k] = v
                rec = decode(out, a.w, a.h, a.fps, n)
                pr = psnr(rec, ref[sa]); ps = psnr(rec, src)
                bad = pr < a.umbral
                row = (int(bad.sum()), runs(bad), float(pr.mean()), float(ps.mean()), int(info.get("descartados", 0)),
                       float(info.get("edge->viewer", 0)), int(info.get("retx", 0)), int(info.get("ih_enviados", 0)))
                agg.setdefault(name, []).append(row)
                curves[f"{name}|{seed}"] = pr
                print(f"{name:12s} {seed:>4s} {row[0]:8d} {row[1]:6d} {row[2]:9.2f} {row[3]:9.2f} {row[4]:8d} {row[5]:6.0f} {row[6]:5d} {row[7]:3d}")
    if a.save:
        np.savez_compressed(a.save + ".npz", **curves)
        with open(a.save + ".csv", "w") as f:
            f.write("escenario,seed,danados,racha,psnr_ref,psnr_src,descartados,kbps,retx,ih\n")
            for name, rows in agg.items():
                for sd, r in zip(a.seeds.split(","), rows):
                    f.write(f"{name},{sd}," + ",".join(f"{x:.3f}" for x in r) + "\n")
    print("\nPROMEDIO sobre semillas")
    for name, rows in agg.items():
        m = np.mean(rows, axis=0)
        print(f"{name:12s} dañados={m[0]:6.1f} racha={m[1]:5.1f} psnr_ref={m[2]:6.2f} psnr_src={m[3]:6.2f} descartados={m[4]:5.1f} kbps={m[5]:6.0f} ih={m[7]:4.1f}")

if __name__ == "__main__":
    main()
