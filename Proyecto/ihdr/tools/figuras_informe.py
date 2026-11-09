#!/usr/bin/env python3
"""Figura de resultados del informe: los 4 casos (UDP, UDP + I-header, SRT, SRT + I-header) con un mismo GoP.

Uso: figuras_informe.py <dir_resultados> <dir_informe> <gop>
  <dir_resultados> tiene r1_2pc_20ms.csv, r2_4pc_200ms.csv y r3_4pc_600ms.csv (salida de evaluate.py --save).
  Genera <dir_informe>/fig_resultados_gop<gop>.pdf. Una figura por GoP: no se mezclan GoP en una comparación.

Paneles:
  (a) Calidad: frames con macroblocking en 10 s (PSNR_ref < 35 dB), media de las semillas ± error estándar.
  (b) Duración del macroblocking por evento, en las semillas donde el caso sin I-header tuvo macroblocking.
  (c) Retardo extremo a extremo del emulador (parámetro, no medición).
  (d) Ancho de banda: tasa hacia el espectador (D = 200 ms) y tasa codificador -> edge.
"""
import csv, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "../informe")
GOP = sys.argv[3] if len(sys.argv) > 3 else "90"
FPS = 30
REG = [("r1_2pc_20ms", "20 ms"), ("r2_4pc_200ms", "200 ms"), ("r3_4pc_600ms", "600 ms")]
CASES = [("udp", "UDP"), ("udp+ih", "UDP + I-header"), ("srt", "SRT"), ("srt+ih", "SRT + I-header")]
# Parámetros del emulador (evaluate.py): retardo de ida 15 ms; búfer de 20 ms sin SRT; latencia SRT 120 ms.
OWD, UDP_BUF, L_SRT = 15, 20, 120
RETARDO = {"udp": OWD + UDP_BUF, "udp+ih": OWD + UDP_BUF, "srt": OWD + L_SRT, "srt+ih": OWD + L_SRT}
# Tasa codificador -> edge (Mbps): stream A y A + I-header cada 5 P con QP del P. Medida el 2026-11-02
# desde el tamaño de los streams (GoP 90). Para GoP 30 hay que medirla y pasarla aquí.
SUBIDA = {"90": (3.1, 5.2)}

COL = {"udp": "#f2b38a", "udp+ih": "#c4510f", "srt": "#9cc3e4", "srt+ih": "#1f5f99"}
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.linewidth": 0.6, "figure.dpi": 200,
                     "axes.spines.top": False, "axes.spines.right": False})
coma = lambda x, nd=1: f"{x:.{nd}f}".replace(".", ",")

def load(tag):
    rows = {}
    with open(R / f"{tag}.csv") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["escenario"], {})[r["seed"]] = {k: float(v) for k, v in r.items() if k not in ("escenario", "seed")}
    return rows

data = {tag: load(tag) for tag, _ in REG}

def stat(tag, sc, k):
    x = np.array([v[k] for v in data[tag][sc].values()])
    return x.mean(), x.std(ddof=1) / np.sqrt(len(x))

def por_evento(tag, sc):
    """Frames con macroblocking en las semillas donde el caso sin I-header tuvo macroblocking (comparación pareada)."""
    base = sc.replace("+ih", "")
    seeds = [s for s, v in data[tag][base].items() if v["danados"] > 0]
    return np.mean([data[tag][sc][s]["danados"] for s in seeds]) if seeds else 0.0, len(seeds)

fig, axs = plt.subplots(1, 4, figsize=(7.16, 2.0), gridspec_kw={"width_ratios": [1.45, 1.0, 0.75, 1.0]})
w = 0.2
off = (np.arange(4) - 1.5) * w
FS = 6  # 60 % de 10 pt
YMAX_A = 60

def etiqueta(ax, x, v, txt, dy, **kw):
    ax.text(x, v + dy, txt, ha="center", va="bottom", fontsize=FS, rotation=90, **kw)

# (a) Calidad
ax = axs[0]
for i, (sc, lab) in enumerate(CASES):
    m = [stat(t, sc, "danados") for t, _ in REG]
    x = np.arange(len(REG)) + off[i]
    ax.bar(x, [min(a, YMAX_A) for a, _ in m], w, color=COL[sc], label=lab)
    for xi, (a, e) in zip(x, m):
        if a > YMAX_A:  # barra recortada: se indica su valor
            etiqueta(ax, xi, YMAX_A - 17, coma(a) + " ↑", 0, color="white" if "+ih" in sc else "black")
        else:
            ax.errorbar(xi, a, yerr=e, color="k", lw=0.6, capsize=1.5)
            etiqueta(ax, xi, a + e, coma(a), 1)
ax.set_xticks(range(len(REG)))
ax.set_xticklabels([d for _, d in REG])
ax.set_xlabel("duración media del corte $D$")
ax.set_ylabel("frames con macroblocking")
ax.set_ylim(0, YMAX_A)
ax.set_title("(a) Calidad", fontsize=8)

# (b) Duración del macroblocking por evento
t200 = "r2_4pc_200ms"
ax = axs[1]
T6 = "r3_4pc_600ms"
for i, (sc, _) in enumerate(CASES):
    vals = [por_evento(t, sc)[0] / FPS for t in (t200, T6)]
    x = np.arange(2) + off[i]
    ax.bar(x, vals, w, color=COL[sc])
    for xi, v in zip(x, vals):
        etiqueta(ax, xi, v, coma(v, 2), 0.03)
ax.set_xticks(range(2))
ax.set_xticklabels(["200 ms", "600 ms"])
ax.set_xlabel("$D$")
ax.set_ylabel("s por evento")
ax.set_ylim(0, 1.6)
ax.set_title("(b) Duración", fontsize=8)

# (c) Retardo extremo a extremo
ax = axs[2]
for i, (sc, _) in enumerate(CASES):
    ax.bar(off[i], RETARDO[sc], w, color=COL[sc])
    etiqueta(ax, off[i], RETARDO[sc], str(RETARDO[sc]), 3)
ax.set_xticks([])
ax.set_ylabel("ms")
ax.set_ylim(0, 180)
ax.set_title("(c) Retardo", fontsize=8)

# (d) Ancho de banda
ax = axs[3]
sub = SUBIDA.get(GOP)
for i, (sc, _) in enumerate(CASES):
    esp = stat(t200, sc, "kbps")[0] / 1000
    vals = [esp] + ([sub[1] if "+ih" in sc else sub[0]] if sub else [0])
    x = np.arange(2) + off[i]
    ax.bar(x, vals, w, color=COL[sc])
    for xi, v in zip(x, vals):
        if v:
            etiqueta(ax, xi, v, coma(v, 2), 0.1)
ax.set_xticks(range(2))
ax.set_xticklabels(["espectador", "subida"])
ax.set_ylabel("Mbps")
ax.set_ylim(0, 7)
ax.set_title("(d) Ancho de banda", fontsize=8)

h, l = axs[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=4, frameon=False, fontsize=7, bbox_to_anchor=(0.5, 1.01))
fig.tight_layout(pad=0.4, w_pad=0.8, rect=(0, 0, 1, 0.9))
fig.savefig(OUT / f"fig_resultados_gop{GOP}.pdf")

# Resumen numérico para el texto
for sc, _ in CASES:
    print(sc, "frames:", [coma(stat(t, sc, "danados")[0]) for t, _ in REG],
          "por evento 200/600 ms:", [(coma(por_evento(t, sc)[0]), por_evento(t, sc)[1]) for t in (t200, "r3_4pc_600ms")],
          "kbps 200:", round(stat(t200, sc, "kbps")[0]))
