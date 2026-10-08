# -*- coding: utf-8 -*-
"""Fig. 1 | Six-type semantic looseness: empirical evidence from three sheets.

Panels: a) code values per sheet (anchor codes highlighted); b) one-code-many-
meanings (decisive evidence inside code 01); c) three annotation label systems;
d) same-slot mixing and variant glyphs; e) completeness gradients; f) attitude
as spatial coupling of three cartographic elements.
"""
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
import numpy as np

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 6.5,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.7,
    "legend.frameon": False,
})

BLUE = "#0F4D92"
RED = "#B64342"
GREY = "#767676"
GOLD = "#C9A227"

fig = plt.figure(figsize=(7.0, 5.2))
gs = fig.add_gridspec(2, 3, hspace=0.62, wspace=0.5,
                      left=0.055, right=0.985, top=0.95, bottom=0.06)

# ---- a) code values per sheet ----------------------------------------------
ax = fig.add_subplot(gs[0, 0])
sheets = ["Kurgan", "Yingjisha", "Aoyiyayilake"]
codes = {
    "Kurgan": ["01", "04", "05", "07", "16", "18", "28", "31", "41"],
    "Yingjisha": ["01", "02", "03", "05", "16", "35", "37"],
    "Aoyiyayilake": ["01", "02", "03", "05", "16", "18", "35", "40"],
}
ANCHOR = {"01", "05", "16"}
for row, s in enumerate(sheets):
    y = 2 - row
    for col, c in enumerate(codes[s]):
        colr = BLUE if c in ANCHOR else "#B9C6D8"
        ax.add_patch(plt.Rectangle((col, y - 0.32), 0.82, 0.64,
                                   facecolor=colr, edgecolor="none"))
        ax.text(col + 0.41, y, c, ha="center", va="center", fontsize=5.6,
                color="#272727")
ax.set_xlim(-0.5, 9.2)
ax.set_ylim(-0.5, 2.6)
ax.set_yticks([0, 1, 2])
ax.set_yticklabels(sheets[::-1])
ax.set_xticks([])
ax.set_title("a  Code values per sheet\n(anchor codes 01/05/16 in blue)",
             fontsize=6.5, loc="left")

# ---- b) one code, many meanings --------------------------------------------
ax = fig.add_subplot(gs[0, 1])
# decisive evidence inside code 01 (own-level calibration, Kurgan)
own = [("Reverse", 34), ("Thrust", 3), ("Normal", 3), ("Inferred", 1)]
names = [p[0] for p in own][::-1]
vals = [p[1] for p in own][::-1]
ax.barh(names, vals, color=[RED, BLUE, "#8BCF8B", GREY][::-1], height=0.6)
ax.set_title("b  Code 01 pools decisive evidence\n(155 segments, one sheet)",
             fontsize=6.5, loc="left")
ax.set_xlabel("Segments with decisive segment-level evidence")
ax.tick_params(axis="y", labelsize=6)

# ---- c) three label systems -------------------------------------------------
ax = fig.add_subplot(gs[0, 2])
ax.axis("off")
ax.set_title("c  Annotation categories: three label systems",
             fontsize=6.5, loc="left")
sys_rows = [
    ("Kurgan", "代号 / 产状 / 断层辅助点 / 化石…"),
    ("Yingjisha", "地质注释 / 断层性质 / 产状注释 / 同位素注释…"),
    ("Aoyiyayilake", "地质注释 / 产状注释 / 断层辅助点 / 断层注释…"),
]
for i, (s, txt) in enumerate(sys_rows):
    ax.text(0.02, 0.86 - i * 0.3, f"{s}:", fontsize=6, fontweight="bold",
            color="#272727", transform=ax.transAxes)
    ax.text(0.02, 0.80 - i * 0.3, txt, fontsize=5.8, color=GREY,
            transform=ax.transAxes)

# ---- d) same-slot mixing -----------------------------------------------------
ax = fig.add_subplot(gs[1, 0])
ax.axis("off")
ax.set_title("d  Same-slot mixing and variant glyphs", fontsize=6.5, loc="left")
items = [
    ("Axis-plane dip (one field)", "“南倾”  vs  “225”"),
    ("Dip direction (one field)", "“360-180”"),
    ("Unit-code glyphs", "Cyrillic г for γ;  ∑ (math variant)"),
]
for i, (k, v) in enumerate(items):
    ax.text(0.02, 0.85 - i * 0.3, k, fontsize=6, fontweight="bold",
            color="#272727", transform=ax.transAxes)
    ax.text(0.02, 0.79 - i * 0.3, v, fontsize=5.8, color=GREY,
            transform=ax.transAxes)

# ---- e) completeness gradients ----------------------------------------------
ax = fig.add_subplot(gs[1, 1])
metrics = ["GZECD\n(dip direction)", "GZEHH\n(activity text)"]
kur = [0, 0]
yin = [34, 0]
aoy = [10, 18]
x = np.arange(2)
w = 0.26
ax.bar(x - w, kur, w, color=BLUE, label="Kurgan")
ax.bar(x, yin, w, color=RED, label="Yingjisha")
ax.bar(x + w, aoy, w, color="#8BCF8B", label="Aoyiyayilake")
ax.set_xticks(x)
ax.set_xticklabels(metrics, fontsize=5.8)
ax.set_ylabel("Non-empty values\n(segments or %)")
ax.set_title("e  Completeness gradients", fontsize=6.5, loc="left")
ax.legend(fontsize=5.4, loc="upper left", handlelength=1.2)

# ---- f) attitude as spatial coupling -----------------------------------------
ax = fig.add_subplot(gs[1, 2])
ax.axis("off")
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.set_title("f  An attitude exists only as spatial coupling",
             fontsize=6.5, loc="left")
# fault trace
ax.plot([0.5, 9.5], [3.0, 3.0], color="#272727", lw=1.4)
# dip arrow (1894)
ar = FancyArrowPatch((5.0, 3.0), (6.6, 4.35), arrowstyle="-|>",
                     mutation_scale=10, color=BLUE, lw=1.3)
ax.add_patch(ar)
ax.text(6.8, 4.5, "dip arrow\n(1894)", fontsize=5.4, color=BLUE)
# paired ticks (1281 pair)
for dx in (-1.1, -0.25):
    ax.plot([4.0 + dx, 4.0 + dx], [2.45, 3.55], color=RED, lw=1.6)
ax.text(1.2, 2.25, "hanging-wall\nticks (1281 pair)", fontsize=5.4, color=RED,
        ha="center")
# dip annotation (text 0)
ax.text(5.1, 3.65, "50°", fontsize=6.5, color="#272727", ha="center")
ax.text(7.4, 3.35, "dip annotation\n(text)", fontsize=5.4, color=GREY)

for lbl, (r, c) in zip("abcdef", [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]):
    pass  # titles already carry panel letters

import sys
sys.path.insert(0, r"C:\Users\Administrator\.claude\skills\nature-figure\scripts")
from audit_panel_alignment import require_matplotlib_panel_alignment

require_matplotlib_panel_alignment(
    fig,
    json_out=r"D:\geosciml4china\docs\publication\figures\fig1.alignment.json",
    overlay_svg=r"D:\geosciml4china\docs\publication\figures\fig1.alignment.svg",
    tolerance_pt=1.5,
    strict=True,
)
fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig1_looseness_taxonomy.svg",
            bbox_inches="tight")
fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig1_looseness_taxonomy.pdf",
            bbox_inches="tight")
print("fig1 saved (alignment gate passed)")
