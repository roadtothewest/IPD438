#!/usr/bin/env python3
"""Análisis de results/final: métricas de experiencia de usuario, figuras (una por GoP) y resumen numérico.

Uso: analizar.py results/final ../informe

Métrica principal (lo que ve el espectador):
  dSSIM_k = SSIM(fuente, sin pérdida)_k - SSIM(fuente, recibido)_k
  Es cuánto peor se ve el frame k que lo que el espectador habría visto sin pérdida, ambos medidos contra
  la fuente cruda. Una deriva del I-header que se ve igual de bien que el P original da dSSIM ~ 0; el
  macroblocking da dSSIM grande. Un frame tiene "artefacto visible" si dSSIM_k > THETA = 0,05.
  THETA es fijo y no se ajusta al método: con GoP 90, el 90 % de los frames con deriva queda bajo 0,017 y
  la mediana de los frames dañados sin I-header supera 0,12. Para no depender de THETA se informan la
  sensibilidad (0,02 y 0,1) y una métrica sin umbral: el SSIM perdido acumulado, suma de dSSIM / fps.
"""
import csv, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path(sys.argv[1] if len(sys.argv) > 1 else "results/final")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "../informe")
FPS, N = 30, 300
REG = [("r20", "20 ms"), ("r200", "200 ms"), ("r600", "600 ms")]
CASES = [("udp", "UDP"), ("udp+ih", "UDP + I-header"), ("srt", "SRT"), ("srt+ih", "SRT + I-header")]
OWD, UDP_BUF, L_SRT = 15, 20, 120
RETARDO = {"udp": OWD + UDP_BUF, "udp+ih": OWD + UDP_BUF, "srt": OWD + L_SRT, "srt+ih": OWD + L_SRT}
COL = {"udp": "#f2b38a", "udp+ih": "#c4510f", "srt": "#9cc3e4", "srt+ih": "#1f5f99"}
coma = lambda x, nd=1: f"{x:.{nd}f}".replace(".", ",")
lines = []
say = lambda *a: (print(*a), lines.append(" ".join(str(x) for x in a)))

def cargar(gop, tag):
    d = R / f"gop{gop}"
    curv = dict(np.load(d / f"{tag}.npz"))
    info = {}
    with open(d / f"{tag}.csv") as f:
        for r in csv.DictReader(f):
            info[(r["caso"], r["semilla"])] = r
    return curv, info

def base(gop):
    return np.load(R / f"gop{gop}" / "base.npz")["ssim_src"]

def dssim(gop, m):
    return base(gop) - m[2]

def rachas(mask):
    """Duraciones (en frames) de los tramos seguidos con artefacto."""
    out, cur = [], 0
    for x in mask:
        if x: cur += 1
        elif cur: out.append(cur); cur = 0
    if cur: out.append(cur)
    return out

# --- Umbral desde la deriva ---
theta_por_gop, deriva_res = {}, {}
for gop in (90, 30):
    curv, info = cargar(gop, "deriva")
    vals, minpsnr, maxd = [], [], []
    for key, m in curv.items():
        k = int(key.split("@")[1].split("|")[0])
        nxt = (k // gop + 1) * gop  # IDR siguiente
        seg = slice(k, min(nxt, N))
        d = dssim(gop, m)[seg]
        vals.extend(d.tolist()); minpsnr.append(float(m[0][seg].min())); maxd.append(float(d.max()))
    vals = np.array(vals)
    theta_por_gop[gop] = float(np.percentile(vals, 99))
    deriva_res[gop] = dict(n=len(curv), p99=theta_por_gop[gop], media=float(vals.mean()), p90=float(np.percentile(vals, 90)),
                           p50=float(np.median(vals)), n_sobre=int(np.sum(np.array(maxd) > 0.05)),
                           psnr_min_med=float(np.median(minpsnr)), psnr_min_min=float(np.min(minpsnr)),
                           frac_psnr35=float(np.mean(np.array(minpsnr) < 35)), dmax=float(np.max(maxd)))
THETA = 0.05
say(f"THETA = {THETA}")
for gop, r in deriva_res.items():
    say(f"deriva GoP{gop}: {r['n']} I-headers forzados; dSSIM mediana {r['p50']:.4f}, p90 {r['p90']:.4f}, p99 {r['p99']:.4f}, "
        f"max {r['dmax']:.4f}; {r['n_sobre']} I-headers superan 0,05 en algún frame; "
        f"PSNR_ref mínimo: mediana {r['psnr_min_med']:.1f} dB, peor {r['psnr_min_min']:.1f} dB; "
        f"{100*r['frac_psnr35']:.0f} % bajaría de 35 dB (contaría como daño con el criterio PSNR)")

def metricas(gop, tag, caso, theta=None):
    theta = THETA if theta is None else theta
    curv, info = cargar(gop, tag)
    res = {}
    for key, m in curv.items():
        c, s = key.split("|")
        if c != caso: continue
        d = dssim(gop, m)
        vis = d > theta
        res[s] = dict(vis=int(vis.sum()), ev=rachas(vis), dmean=float(d.mean()), acum=float(np.clip(d, 0, None).sum() / FPS),
                      psnr35=int((m[0] < 35).sum()),
                      kbps=float(info[(c, s)]["kbps_espectador"]), sub=float(info[(c, s)]["kbps_subida"]),
                      sub0=float(info[(c, s)]["kbps_subida_sin_ih"]), info=info[(c, s)])
    return res

def media_se(x):
    x = np.asarray(x, float)
    return float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0

def por_evento(gop, tag, caso):
    """Duración (s) del artefacto en las semillas donde el caso sin I-header tuvo artefacto (pareado)."""
    base_c = caso.replace("+ih", "")
    mb, mc = metricas(gop, tag, base_c), metricas(gop, tag, caso)
    seeds = [s for s, v in mb.items() if v["vis"] > 0]
    return [mc[s]["vis"] / FPS for s in seeds], seeds

def figura(gop):
    plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.linewidth": 0.6, "figure.dpi": 200,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axs = plt.subplots(1, 4, figsize=(7.16, 2.0), gridspec_kw={"width_ratios": [1.45, 1.0, 0.75, 1.0]})
    w, FS = 0.2, 6
    off = (np.arange(4) - 1.5) * w
    lab = lambda ax, x, v, t, dy, **k: ax.text(x, v + dy, t, ha="center", va="bottom", fontsize=FS, rotation=90, **k)
    # (a) segundos con artefacto visible en 10 s
    ax = axs[0]
    ymax = 0
    for i, (c, l) in enumerate(CASES):
        ms = [media_se([v["vis"] / FPS for v in metricas(gop, t, c).values()]) for t, _ in REG]
        x = np.arange(3) + off[i]
        ax.bar(x, [a for a, _ in ms], w, color=COL[c], label=l)
        ax.errorbar(x, [a for a, _ in ms], yerr=[e for _, e in ms], fmt="none", color="k", lw=0.6, capsize=1.5)
        for xi, (a, e) in zip(x, ms):
            lab(ax, xi, a + e, coma(a, 2), 0.05)
        ymax = max(ymax, max(a + e for a, e in ms))
    ax.set_xticks(range(3)); ax.set_xticklabels([d for _, d in REG])
    ax.set_xlabel("duración media del corte $D$"); ax.set_ylabel("s con artefacto visible (de 10 s)")
    ax.set_ylim(0, ymax * 1.35); ax.set_title("(a) Calidad", fontsize=8)
    # (b) duración por evento
    ax = axs[1]
    for i, (c, _) in enumerate(CASES):
        vals = [np.mean(por_evento(gop, t, c)[0]) if por_evento(gop, t, c)[1] else 0 for t in ("r200", "r600")]
        x = np.arange(2) + off[i]
        ax.bar(x, vals, w, color=COL[c])
        for xi, v in zip(x, vals):
            lab(ax, xi, v, coma(v, 2), 0.03)
    ax.set_xticks(range(2)); ax.set_xticklabels(["200 ms", "600 ms"]); ax.set_xlabel("$D$")
    ax.set_ylabel("s por evento"); ax.set_ylim(0, None); ax.set_title("(b) Duración", fontsize=8)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.3)
    # (c) retardo
    ax = axs[2]
    for i, (c, _) in enumerate(CASES):
        ax.bar(off[i], RETARDO[c], w, color=COL[c]); lab(ax, off[i], RETARDO[c], str(RETARDO[c]), 3)
    ax.set_xticks([]); ax.set_ylabel("ms"); ax.set_ylim(0, 180); ax.set_title("(c) Retardo", fontsize=8)
    # (d) ancho de banda
    ax = axs[3]
    for i, (c, _) in enumerate(CASES):
        m = metricas(gop, "r200", c)
        esp = np.mean([v["kbps"] for v in m.values()]) / 1000
        sub = np.mean([v["sub"] if "+ih" in c else v["sub0"] for v in m.values()]) / 1000
        x = np.arange(2) + off[i]
        ax.bar(x, [esp, sub], w, color=COL[c])
        for xi, v in zip(x, [esp, sub]):
            lab(ax, xi, v, coma(v, 2), 0.1)
    ax.set_xticks(range(2)); ax.set_xticklabels(["espectador", "subida"]); ax.set_ylabel("Mbps")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.3); ax.set_title("(d) Ancho de banda", fontsize=8)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=4, frameon=False, fontsize=7, bbox_to_anchor=(0.5, 1.01))
    fig.tight_layout(pad=0.4, w_pad=0.8, rect=(0, 0, 1, 0.9))
    fig.savefig(OUT / f"fig_resultados_gop{gop}.pdf")
    plt.close(fig)

for gop in (90, 30):
    say(f"\n=== GoP {gop} ===")
    for t, d in REG:
        for c, _ in CASES:
            m = metricas(gop, t, c)
            vis = media_se([v["vis"] / FPS for v in m.values()])
            ev, seeds = por_evento(gop, t, c)
            say(f"{t:5s} {c:7s} artefacto {coma(vis[0],2)} ± {coma(vis[1],2)} s; por evento {coma(np.mean(ev) if ev else 0,2)} s "
                f"(n={len(seeds)}); SSIM perdido acumulado {np.mean([v['acum'] for v in m.values()]):.3f} SSIM·s; "
                f"PSNR<35: {np.mean([v['psnr35'] for v in m.values()]):.1f} frames; "
                f"espectador {np.mean([v['kbps'] for v in m.values()]):.0f} kbps; subida {np.mean([v['sub'] for v in m.values()]):.0f} kbps")
        # pareado SRT vs SRT+IH
        a, b = metricas(gop, t, "srt"), metricas(gop, t, "srt+ih")
        dif = np.array([b[s]["vis"] - a[s]["vis"] for s in a])
        say(f"{t:5s} SRT+IH - SRT (frames): media {dif.mean():.1f} ± {dif.std(ddof=1)/np.sqrt(len(dif)):.1f}; "
            f"mejora en {(dif < 0).sum()}, empeora en {(dif > 0).sum()}, igual en {(dif == 0).sum()} de {len(dif)}")
    # L recomendada
    for t in ("r200", "r600"):
        for c in ("srt@180", "srt+ih@180"):
            m = metricas(gop, t, c)
            say(f"{t} {c}: artefacto {coma(np.mean([v['vis'] for v in m.values()]) / FPS, 2)} s")
    # detección
    m = {}
    for t, _ in REG:
        m.update({(t, s): v for s, v in metricas(gop, t, "srt+ih").items()})
    marc = sum(int(v["info"]["marcados"] or 0) for v in m.values())
    verd = sum(int(v["info"]["verdaderos"] or 0) for v in m.values())
    real = sum(int(v["info"]["descartes_reales"] or 0) for v in m.values())
    say(f"detección regla (2), por paquete: marcados {marc}, verdaderos {verd} (precisión {verd / max(marc, 1):.3f}), descartes reales {real}")
    # Por corrida (evento): ¿se envió un I-header sin descarte real? ¿hubo descarte sin I-header?
    fp = sum(1 for v in m.values() if int(v["info"]["ih_enviados"] or 0) > 0 and int(v["info"]["descartes_reales"] or 0) == 0)
    fn = sum(1 for v in m.values() if int(v["info"]["ih_enviados"] or 0) == 0 and int(v["info"]["descartes_reales"] or 0) > 0)
    con = sum(1 for v in m.values() if int(v["info"]["descartes_reales"] or 0) > 0)
    say(f"detección regla (2), por corrida: {len(m)} corridas, {con} con descarte; I-header sin descarte: {fp}; descarte sin I-header: {fn}")
    ih = [(int(v["info"]["au_ih_max"]), float(v["info"]["p_medio"])) for v in m.values() if int(v["info"]["au_ih_max"] or 0) > 0]
    if ih:
        say(f"pico: AU con I-header máx {max(x for x, _ in ih)} B; P medio {ih[0][1]:.0f} B; "
            f"razón {max(x for x, _ in ih) / ih[0][1]:.1f}")
    figura(gop)

# Alternativa: subir L (GoP 90)
for t in ("r200", "r600"):
    for L in (250, 500, 1000):
        f = R / "gop90" / f"{t}_L.npz"
        if f.exists():
            curv = dict(np.load(f))
            v = [(dssim(90, m) > THETA).sum() / FPS for k, m in curv.items() if k.startswith(f"srt@{L}|")]
            say(f"{t} SRT L={L}: artefacto {coma(np.mean(v), 2)} s")

# Sensibilidad al umbral (GoP 90, r200): reducción por evento de SRT+IH frente a SRT
for gop in (90, 30):
    for t in ("r20", "r200", "r600"):
        for th in (0.02, 0.05, 0.1):
            a, b = metricas(gop, t, "srt", th), metricas(gop, t, "srt+ih", th)
            ta, tb = np.mean([v["vis"] for v in a.values()]) / FPS, np.mean([v["vis"] for v in b.values()]) / FPS
            say(f"sensibilidad GoP{gop} {t} theta={th}: SRT {ta:.2f} s -> SRT+IH {tb:.2f} s con artefacto (de 10 s)")

(R / "resumen.txt").write_text("\n".join(lines) + "\n")
