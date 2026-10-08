# -*- coding: utf-8 -*-
"""Fig. 4 | The adjudication loop: editable mapping table, deterministic
replay, byte-identical revert. Schematic (single panel)."""
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 6.5,
})

BLUE = "#0F4D92"
LBLUE = "#D7E3F2"
RED = "#B64342"
GREY = "#767676"
GOLD = "#C9A227"

fig, ax = plt.subplots(figsize=(7.2, 3.0))
ax.set_xlim(0, 100)
ax.set_ylim(0, 40)
ax.axis("off")

def box(x, y, w, h, fc, ec, text, fs=5.8, tc="#272727"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4",
                                fc=fc, ec=ec, lw=0.9))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc)

def arrow(x1, y1, x2, y2, color=GREY, lw=1.0, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=9, color=color, lw=lw,
                                 linestyle=ls, connectionstyle=f"arc3,rad={rad}"))

# left: mapping table
box(2, 22, 24, 12, "white", BLUE,
    "mapping table (CSV)\nper code: semantic\n+ user_semantic\n+ confidence", fs=5.8)
# middle: replay chain
box(34, 26, 18, 8, LBLUE, BLUE, "calibrate\n(deterministic\nreplay)", fs=5.8)
box(56, 26, 20, 8, LBLUE, BLUE, "pipeline skip-mode\nmaterialize → build\n→ verify → render", fs=5.6)
box(80, 26, 18, 8, "#EDEDED", GREY, "GeoSciML\n+ rendered map\n+ conflict register", fs=5.6)

arrow(26.4, 30, 33.6, 30, color=BLUE, lw=1.2)
arrow(52.4, 30, 55.6, 30, color=BLUE, lw=1.2)
arrow(76.4, 30, 79.6, 30, color=BLUE, lw=1.2)

# revert arc back to the table
arrow(86, 25.2, 26, 23.4, color=RED, lw=1.1, ls=(0, (3, 1.6)), rad=-0.12)
ax.text(56, 16.4, "revert (edit cleared) → replay → byte-identical state",
        fontsize=6, color=RED, ha="center")

# bottom: properties
box(2, 8, 46, 6.5, "white", GOLD,
    "human input enters only through versioned,\nreplayable edits — no hand-edited state", fs=5.4)
box(52, 8, 46, 6.5, "white", GOLD,
    "conflict register = objective observable\n(J = K + λF decreases per adjudication)", fs=5.4)

fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig4_adjudication_loop.svg",
            bbox_inches="tight")
fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig4_adjudication_loop.pdf",
            bbox_inches="tight")
print("fig4 saved")
