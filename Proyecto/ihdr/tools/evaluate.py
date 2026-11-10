#!/usr/bin/env python3
"""Corre el emulador en varios casos con la MISMA historia de cortes y guarda métricas por frame.

Cada corrida: ihdr_sim (codificador -> edge -> espectador) -> .ts recibido -> decodificador H.264 de FFmpeg
(con su ocultamiento de errores) -> imagen que vería el espectador. Un frame que no llega se repite (congelado).

Métricas por frame, solo sobre la luminancia Y:
  psnr_ref  PSNR contra el mismo stream decodificado sin pérdida.
  ssim_ref  SSIM contra el mismo stream decodificado sin pérdida.
  ssim_src  SSIM contra la fuente cruda (lo que el espectador debería ver).
SSIM (Wang et al., 2004), implementado aquí para que se sepa exactamente qué calcula:
  - luminancia promediada en bloques de FxF, con F = max(1, round(min(alto, ancho)/256)) = 3 en 720p,
    como en la implementación de referencia de los autores (aproxima la distancia de visión);
  - ventana gaussiana de 11x11 con sigma = 1,5; C1 = (0,01*255)^2, C2 = (0,03*255)^2;
  - SSIM(x,y) = (2 mx my + C1)(2 sxy + C2) / ((mx^2 + my^2 + C1)(sx^2 + sy^2 + C2)), promedio del mapa
    sin los 5 píxeles del borde.
Los frames idénticos al stream sin pérdida no se recalculan: toman el valor de la decodificación sin pérdida.

Salida (en --out):
  base.npz            métricas por frame del stream sin pérdida (ssim_src, psnr_src).
  <tag>.npz           por corrida "caso|semilla": arreglo (4, N) = psnr_ref, ssim_ref, ssim_src, psnr_src.
  <tag>.csv           por corrida: lo que informa el simulador (tasas, descartes, detección, I-headers).
Uso: ver tools/reproducir.sh.
"""
import argparse, subprocess, tempfile
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter

def decode(path, w, h, fps, n):
    cmd = ["ffmpeg", "-v", "error", "-y", "-threads", "1", "-flags", "+output_corrupt", "-i", str(path),
           "-fps_mode", "cfr", "-r", str(fps), "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    fs = w * h * 3 // 2
    k = len(raw) // fs
    a = np.frombuffer(raw[:k * fs], np.uint8).reshape(k, fs)[:, :w * h].reshape(k, h, w)
    if k < n:  # lo que falta al final se congela
        pad = np.repeat(a[-1:] if k else np.zeros((1, h, w), np.uint8), n - k, axis=0)
        a = np.concatenate([a, pad])
    return a

C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2

def prep(y):
    """Promedio en bloques FxF (F = 3 en 720p) -> float64."""
    h, w = y.shape
    f = max(1, round(min(h, w) / 256))
    y = y[: h // f * f, : w // f * f].astype(np.float64)
    return y.reshape(h // f, f, w // f, f).mean(axis=(1, 3))

def ssim(x, y):
    g = lambda z: gaussian_filter(z, 1.5, truncate=3.5)  # radio 5 -> ventana 11x11
    mx, my = g(x), g(y)
    sxx, syy, sxy = g(x * x) - mx * mx, g(y * y) - my * my, g(x * y) - mx * my
    m = ((2 * mx * my + C1) * (2 * sxy + C2)) / ((mx * mx + my * my + C1) * (sxx + syy + C2))
    return float(m[5:-5, 5:-5].mean())

def psnr(x, y):
    d = x.astype(np.int32) - y.astype(np.int32)
    mse = float(np.mean(d * d))
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)

def parse_log(log):
    info = {}
    for line in log.splitlines():
        for tok in line.replace(":", " ").replace("(", " ").replace(")", " ").split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                info[k] = v
    return info

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--streams", required=True, help="carpeta con A_gop{G}.h264 y candidatos.txt")
    ap.add_argument("--gop", type=int, required=True)
    ap.add_argument("--sim", default=str(Path(__file__).resolve().parent.parent / "build" / "ihdr_sim"))
    ap.add_argument("--w", type=int, default=1280); ap.add_argument("--h", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30); ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--loss", type=float, default=0.0); ap.add_argument("--burst-ms", type=float, default=20)
    ap.add_argument("--owd-ms", type=int, default=15); ap.add_argument("--udp-buffer-ms", type=int, default=20)
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--cases", default="udp,udp+ih,srt,srt+ih",
                    help="udp, udp+ih, srt, srt+ih; srt y srt+ih aceptan @L (latencia en ms, 120 por defecto)")
    ap.add_argument("--force-ih", default=None, help="sin pérdida: lista de frames donde forzar un I-header (deriva)")
    ap.add_argument("--out", required=True); ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    S = Path(a.streams); n = a.frames
    A = S / f"A_gop{a.gop}.h264"
    B = (S / "candidatos.txt").read_text().strip()
    fs = a.w * a.h * 3 // 2
    src = np.fromfile(a.src, np.uint8, count=n * fs).reshape(n, fs)[:, :a.w * a.h].reshape(n, a.h, a.w)
    ref = decode(A, a.w, a.h, a.fps, n)
    src_p = [prep(f) for f in src]
    ref_p = [prep(f) for f in ref]
    base_f = out / "base.npz"
    if base_f.exists():
        base = np.load(base_f)
        b_ssim, b_psnr = base["ssim_src"], base["psnr_src"]
    else:
        b_ssim = np.array([ssim(src_p[k], ref_p[k]) for k in range(n)], np.float32)
        b_psnr = np.array([psnr(src[k], ref[k]) for k in range(n)], np.float32)
        np.savez_compressed(base_f, ssim_src=b_ssim, psnr_src=b_psnr)

    def measure(rec):
        m = np.empty((4, n), np.float32)
        for k in range(n):
            if np.array_equal(rec[k], ref[k]):
                m[:, k] = (99.0, 1.0, b_ssim[k], b_psnr[k])
            else:
                rp = prep(rec[k])
                m[:, k] = (psnr(rec[k], ref[k]), ssim(ref_p[k], rp), ssim(src_p[k], rp), psnr(rec[k], src[k]))
        return m

    runs = []  # (caso, semilla, modo, latencia, arq, extra)
    if a.force_ih:
        for f in a.force_ih.split(","):
            runs.append((f"forzado@{f}", "0", "report", 120, 1, ["--force-ih", f]))
    else:
        seeds = a.seeds.split("-")
        seeds = [str(s) for s in range(int(seeds[0]), int(seeds[1]) + 1)] if len(seeds) == 2 else a.seeds.split(",")
        for c in a.cases.split(","):
            base_c, _, lat = c.partition("@")
            mode = {"udp": "plain", "udp+ih": "report", "srt": "plain", "srt+ih": "ack"}[base_c]
            arq = 0 if base_c.startswith("udp") else 1
            L = a.udp_buffer_ms if arq == 0 else int(lat or 120)
            for s in seeds:
                runs.append((c, s, mode, L, arq, []))

    curves, rows = {}, []
    keys = ["edge->viewer", "retx_kbps", "encoder->edge", "encoder->edge_sin_ih", "ih_enviados", "descartados", "marcados", "verdaderos",
            "descartes_reales", "au_ih_max", "p_medio", "perdidos", "parciales"]
    with tempfile.TemporaryDirectory() as tmp:
        for case, seed, mode, L, arq, extra in runs:
            ts = f"{tmp}/r.ts"
            cmd = [a.sim, "--a", str(A), "--mode", mode, "--out", ts, "--loss", str(a.loss), "--burst-ms", str(a.burst_ms),
                   "--seed", seed, "--latency-ms", str(L), "--owd-ms", str(a.owd_ms), "--fps", str(a.fps),
                   "--frames", str(n), "--arq", str(arq)] + extra
            if mode != "plain":
                cmd += ["--b", B]
            info = parse_log(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
            m = measure(decode(ts, a.w, a.h, a.fps, n))
            curves[f"{case}|{seed}"] = m
            rows.append([case, seed, str(L)] + [info.get(k, "") for k in keys])
            print(f"{a.tag} {case:12s} {seed:>3s} dañados(psnr<35)={int((m[0] < 35).sum()):4d} "
                  f"ssim_src={m[2].mean():.4f} kbps={info.get('edge->viewer', '')}", flush=True)
    np.savez_compressed(out / f"{a.tag}.npz", **curves)
    with open(out / f"{a.tag}.csv", "w") as f:
        f.write("caso,semilla,latencia_ms,kbps_espectador,kbps_retx,kbps_subida,kbps_subida_sin_ih,ih_enviados,"
                "descartados,marcados,verdaderos,descartes_reales,au_ih_max,p_medio,au_perdidos,au_parciales\n")
        for r in rows:
            f.write(",".join(r) + "\n")

if __name__ == "__main__":
    main()
