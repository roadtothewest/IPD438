#!/usr/bin/env python3
"""Tabla y figuras del informe a partir de results/r*.csv y .npz (salida de evaluate.py --save)."""
import csv, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

R = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "../informe")
REG = [("r1_2pc_20ms", "20"), ("r2_4pc_200ms", "200"), ("r3_4pc_600ms", "600")]
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.linewidth": 0.6,
                     "lines.linewidth": 1.1, "figure.dpi": 200})

def load(tag):
    rows = {}
    with open(R / f"{tag}.csv") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["escenario"], []).append({k: float(v) for k, v in r.items() if k not in ("escenario",)})
    return rows

data = {tag: load(tag) for tag, _ in REG}
mean = lambda tag, sc, k: float(np.mean([r[k] for r in data[tag][sc]]))
coma = lambda x, nd: f"{x:.{nd}f}".replace(".", ",")  # decimal con coma

# Tabla
order = [("udp", "UDP"), ("udp+ih", "UDP + I-header"), ("srt", "SRT"), ("srt+ih", "SRT + I-header"), ("srt+ih_rep", "SRT + I-h., aviso"),
         ("srt_gop30", "SRT, GoP 30"), ("srt@250", "SRT, $L=250$ ms"), ("srt@500", "SRT, $L=500$ ms"),
         ("srt@1000", "SRT, $L=1000$ ms")]
lines = [r"\begin{table}[t]", r"\centering",
         r"\caption{Frames dañados en 10~s (promedio de 8 semillas), con 2~\% de pérdida (corte medio de 20~ms) y 4~\% de pérdida (cortes de 200 y 600~ms). GoP~90 y $L=120$~ms salvo que se indique. Las dos últimas columnas son del régimen de 200~ms: PSNR promedio contra la fuente (sin pérdida: 36,37~dB con GoP~90) y tasa hacia el espectador, incluidas las retransmisiones.}",
         r"\label{tab:res}", r"\footnotesize", r"\setlength{\tabcolsep}{3pt}", r"\begin{tabular}{@{}lrrrrr@{}}", r"\toprule",
         r" & \multicolumn{3}{c}{Frames dañados, $D=$} & \multicolumn{2}{c}{$D=200$ ms} \\ \cmidrule(lr){2-4}\cmidrule(l){5-6}",
         r"Escenario & 20 ms & 200 ms & 600 ms & PSNR$_\mathrm{fuente}$ (dB) & Tasa (kbps) \\", r"\midrule"]
for sc, label in order:
    vals = [coma(mean(t, sc, 'danados'), 1) for t, _ in REG]
    kb = f"{mean('r2_4pc_200ms', sc, 'kbps'):.0f}"
    pf = coma(mean('r2_4pc_200ms', sc, 'psnr_src'), 2)
    lines.append(f"{label} & " + " & ".join(vals) + f" & {pf} & {kb} \\\\")
    if sc in ("udp+ih", "srt+ih_rep"):
        lines.append(r"\addlinespace[2pt]")
lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
(OUT / "tabla_resultados.tex").write_text("\n".join(lines) + "\n")

# Figura del evento: semilla de 200 ms con más daño en SRT
tag = "r2_4pc_200ms"
cur = np.load(R / f"{tag}.npz")
seeds = [k.split("|")[1] for k in cur.files if k.startswith("srt|")]
seed = max(seeds, key=lambda s: (cur[f"srt|{s}"] < 35).sum())
p = cur[f"srt|{seed}"]
bad = np.where(p < 99)[0]
a, b = max(0, bad[0] - 8), min(len(p), bad[0] + 70)
fig, ax = plt.subplots(figsize=(3.45, 1.75))
t = np.arange(a, b) / 30.0
for sc, lab, st in [("srt", "SRT", "-"), ("srt_gop30", "SRT, GoP 30", ":"), ("srt+ih", "SRT + I-header", "-"),
                    ("udp+ih", "UDP + I-header", "--")]:
    y = np.minimum(cur[f"{sc}|{seed}"][a:b], 60)
    ax.plot(t, y, st, label=lab, lw=1.4 if sc == "srt+ih" else 1.0)
ax.axhline(35, color="0.5", lw=0.5)
ax.text(t[-1], 36, "umbral 35 dB", color="0.4", fontsize=7, ha="right")
ax.set_xlabel("tiempo (s)")
ax.set_ylabel(r"PSNR$_{\mathrm{ref}}$ (dB, tope 60)")
ax.set_ylim(0, 62)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: coma(x, 1)))
ax.legend(loc="lower right", fontsize=7, frameon=False, ncol=2, borderaxespad=0.2)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_evento.pdf")
(OUT / "evento.txt").write_text(f"{tag} semilla {seed}, frames {a}-{b}\n")

# Figura de latencia
fig, ax = plt.subplots(figsize=(3.45, 1.75))
L = [120, 250, 500, 1000]
for (tg, D), mk in zip(REG, "osd"):
    ys = [mean(tg, "srt" if l == 120 else f"srt@{l}", "danados") for l in L]
    ln, = ax.plot(L, ys, marker=mk, ms=3.5, label=f"SRT, $D$={D} ms")
    ax.plot([120], [mean(tg, "srt+ih", "danados")], marker=mk, ms=6, mfc="none", color=ln.get_color(), ls="none")
ax.plot([], [], marker="o", ms=6, mfc="none", color="k", ls="none", label="SRT + I-header ($L$=120)")
ax.set_xscale("log")
ax.set_xticks(L)
ax.set_xticklabels([str(l) for l in L])
ax.set_xlabel("latencia de SRT $L$ (ms)")
ax.set_ylabel("frames dañados")
ax.legend(fontsize=7, frameon=False)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_latencia.pdf")
print("ok", seed)
