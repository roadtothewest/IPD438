"""Figuras de la presentación de avance generadas desde datos medidos.

  python3 figuras.py            # lee datos/perdida_gop.csv, escribe figuras/*.pdf

Los datos salen de ../experimentos/perdida_gop.py.
"""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

AQUI = Path(__file__).parent
AZUL = (0 / 255, 50 / 255, 100 / 255)
ROJO = (170 / 255, 30 / 255, 30 / 255)
GRIS_P = (0.86, 0.87, 0.9)
CONGELADO = (0.35, 0.35, 0.38)
CAIDA_MAX = 8.0  # dB de caída de PSNR-Y que satura el color

plt.rcParams.update({
    "text.usetex": True,
    "font.family": "sans-serif",
    "text.latex.preamble": r"\usepackage[T1]{fontenc}\usepackage{helvet}"
                           r"\usepackage{amssymb}\usepackage{sansmath}\sansmath",
    "font.size": 9,
})
ROJOS = LinearSegmentedColormap.from_list("caida", [(1, 1, 1), ROJO])


def leer():
    with open(AQUI / "datos" / "perdida_gop.csv") as f:
        return list(csv.DictReader(f))


def segundos(frames):
    s = frames / 30
    return f"{s:.0f} s" if s == int(s) else f"{s:.1f} s".replace(".", "{,}")


def propagacion(filas):
    n = len(filas)
    # (etiqueta, columna, frame perdido, columna sin pérdida de esa codificación)
    escenarios = [
        ("Se pierde un P", "pierde_P45", 45, "sin_perdida"),
        ("Se pierde un I (no IDR)", "pierde_I30", 30, "sin_perdida_B"),
        ("Se pierde el IDR", "pierde_IDR30", 30, "sin_perdida"),
    ]
    fig, ax = plt.subplots(figsize=(5.5, 2.3))
    alto, sep = 0.62, 1.0

    # Fila de estructura: un intra cada 30 frames.
    y0 = len(escenarios) * sep
    for i, f in enumerate(filas):
        intra = f["tipo_A"] == "IDR"
        ax.add_patch(Rectangle((i, y0), 1, alto, lw=0.25, ec="white",
                               fc=AZUL if intra else GRIS_P))
    ax.text(-1.5, y0 + alto / 2, "30 fps, GoP 30", ha="right", va="center")
    for k in range(0, n, 30):
        ax.text(k + 0.5, y0 + alto + 0.1, "intra", ha="left", va="bottom",
                fontsize=7, color=AZUL)

    for fila, (etiqueta, col, perdido, base) in enumerate(escenarios):
        y = (len(escenarios) - 1 - fila) * sep
        danados = congelados = 0
        for i, f in enumerate(filas):
            if f[f"entregado_{col}"] == "0":
                color = CONGELADO
                congelados += 1
            else:
                caida = float(f[f"psnr_{base}"]) - float(f[f"psnr_{col}"])
                color = ROJOS(min(max(caida, 0) / CAIDA_MAX, 1))
            danados += f[f"danado_{col}"] == "1"
            ax.add_patch(Rectangle((i, y), 1, alto, lw=0.25, ec="white", fc=color))
        ax.plot(perdido + 0.5, y + alto + 0.13, marker="v", ms=3.5, color="black")
        ax.text(-1.5, y + alto / 2, etiqueta, ha="right", va="center")
        resumen = rf"\textbf{{{danados} frames}} $=$ {segundos(danados)}"
        if congelados > 1:
            resumen = rf"\shortstack[l]{{{resumen}\\{congelados} congelados}}"
        ax.text(n + 1.5, y + alto / 2, resumen, ha="left", va="center", fontsize=8)

    ax.set_xlim(0, n)
    ax.set_ylim(-0.1, y0 + alto + 0.45)
    ax.set_yticks([])
    ax.set_xticks(range(0, n + 1, 30))
    ax.set_xticklabels([segundos(k) for k in range(0, n + 1, 30)])
    ax.tick_params(axis="x", length=2, pad=2)
    for lado in ("left", "right", "top"):
        ax.spines[lado].set_visible(False)

    # Leyenda en una línea bajo el eje: escala de caída y congelado.
    ly, lh = -1.05, 0.38
    ax.text(-1.5, ly + lh / 2, r"$\blacktriangledown$ frame perdido", ha="right",
            va="center", fontsize=7)
    lx = 0
    ax.text(lx, ly + lh / 2, r"ca\'ida de PSNR-Y:\ 0", ha="left", va="center",
            fontsize=7)
    lx += 25
    for j in range(16):
        ax.add_patch(Rectangle((lx + j * 0.8, ly), 0.8, lh, lw=0,
                               fc=ROJOS(j / 15), clip_on=False))
    ax.text(lx + 13.3, ly + lh / 2, f"{CAIDA_MAX:.0f} dB", ha="left",
            va="center", fontsize=7)
    lx += 26
    ax.add_patch(Rectangle((lx, ly), 2.4, lh, lw=0, fc=CONGELADO, clip_on=False))
    ax.text(lx + 3.2, ly + lh / 2, "congelado (no entregado por el decodificador)",
            ha="left", va="center", fontsize=7)

    fig.subplots_adjust(left=0.255, right=0.775, top=0.98, bottom=0.19)
    destino = AQUI / "figuras" / "propagacion.pdf"
    destino.parent.mkdir(exist_ok=True)
    fig.savefig(destino)
    plt.close(fig)


if __name__ == "__main__":
    propagacion(leer())
