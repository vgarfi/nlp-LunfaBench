"""EDA figure: the 90 items of the curated set by decade and layer.

Grid of decade (of fragment A, according to Genius) by layer, with the number
of items written in each cell and the color on a single blue scale (darker,
more items). Since the numbers are written, the figure does not depend on
color to be read. Each row shows the total of its layer in parentheses. The
labels are in Spanish because the figure goes in the report.

Usage: python -m analysis.figure_curated  (after analysis.eda)
Output: reports/figura_curado.png
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pipeline import common  # noqa: E402

OUTPUT = os.path.join(common.REPORTS, "figura_curado.png")
SURFACE, TEXT, TEXT_2, EMPTY = "#fcfcfb", "#0b0b0b", "#52514e", "#f0efec"
# Sequential blue scale from the visualization guide (steps 250 to 650).
BLUES = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]
LAYERS = [("falso_amigo", "Falsos amigos"), ("lunfardo_sin_homonimo", "Sin homónimo"),
          ("polisemico_interno", "Polisémicos"), ("control_negativo", "Controles")]
DECADES = [str(d) for d in range(1910, 2030, 10)] + ["sin anio"]


def main():
    with open(os.path.join(common.REPORTS, "eda_numeros.json"), encoding="utf-8") as f:
        eda = json.load(f)
    maximum = max(n for layer, _ in LAYERS
                  for n in eda["por_capa"][layer]["fragmentos_a_por_decada"].values())
    plt.rcParams.update({"font.family": ["Arial", "Helvetica", "DejaVu Sans"], "font.size": 9})
    fig, ax = plt.subplots(figsize=(6.3, 1.55), dpi=220)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for row, (layer, _) in enumerate(LAYERS):
        counts = eda["por_capa"][layer]["fragmentos_a_por_decada"]
        for col, decade_label in enumerate(DECADES):
            n = counts.get(decade_label, 0)
            color = EMPTY if n == 0 else BLUES[min(len(BLUES) - 1,
                                                   round((n - 1) / max(maximum - 1, 1)
                                                         * (len(BLUES) - 1)))]
            ax.add_patch(plt.Rectangle((col + 0.04, row + 0.06), 0.92, 0.88, color=color,
                                       linewidth=0))
            if n:
                dark = BLUES.index(color) >= 3
                ax.text(col + 0.5, row + 0.5, str(n), ha="center", va="center", fontsize=8,
                        color="white" if dark else TEXT, fontweight="bold")
    ax.set_xlim(0, len(DECADES))
    ax.set_ylim(len(LAYERS), 0)
    ax.set_xticks([i + 0.5 for i in range(len(DECADES))])
    ax.set_xticklabels([d if d != "sin anio" else "sin año" for d in DECADES], color=TEXT_2,
                       fontsize=8)
    ax.set_yticks([i + 0.5 for i in range(len(LAYERS))])
    # Each row shows the total number of terms of the layer.
    ax.set_yticklabels([f'{n} ({eda["por_capa"][layer]["terminos"]})' for layer, n in LAYERS],
                       color=TEXT)
    ax.tick_params(length=0)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUTPUT, facecolor=SURFACE)
    print(f"-> {OUTPUT}")


if __name__ == "__main__":
    main()
