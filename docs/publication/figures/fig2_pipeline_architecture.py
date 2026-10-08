# -*- coding: utf-8 -*-
"""Fig. 2 | Pipeline architecture: six-stage contract, eight calibration
domains, three-level inference. Schematic (single panel)."""
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
LRED = "#FDF2F0"
GREY = "#767676"
GOLD = "#C9A227"
LGOLD = "#F2E7C4"

fig, ax = plt.subplots(figsize=(7.4, 4.4))
ax.set_xlim(0, 100)
ax.set_ylim(0, 62)
ax.axis("off")

def box(x, y, w, h, fc, ec, text, fs=6.2, tc="#272727", ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4",
                                fc=fc, ec=ec, lw=0.9, linestyle=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc)

def arrow(x1, y1, x2, y2, color=GREY, lw=1.0, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=9, color=color, lw=lw,
                                 linestyle=ls))

# ---- top: six-stage chain ----------------------------------------------------
stages = [
    (2, 46, 12, 7, "⓪ preflight\n11 files", LBLUE, BLUE),
    (17, 46, 12, 7, "① convert\nMapGIS→L0", LBLUE, BLUE),
    (32, 46, 14, 7, "② calibrate\n8 domains", LRED, RED),
    (49, 46, 12, 7, "③ stylegen\nsemantics→style", LBLUE, BLUE),
    (64, 46, 10, 7, "④ build\nGML+lite", LBLUE, BLUE),
    (77, 46, 10, 7, "⑤ verify\n29+7 checks", LBLUE, BLUE),
    (90, 46, 8, 7, "⑥ render", LBLUE, BLUE),
]
for x, y, w, h, t, fc, ec in stages:
    box(x, y, w, h, fc, ec, t)
for (x1, _, w1, _, _, _, _), (x2, y2, w2, _, _, _, _) in zip(stages, stages[1:]):
    arrow(x1 + w1 + 0.6, 49.5, x2 - 0.6, 49.5)

# ---- L1 annotation above ② ---------------------------------------------------
ax.text(39, 57.6, "L1  segment-level evidence aggregation\n     + topological operators",
        fontsize=5.6, color=GOLD, ha="center")
arrow(39, 56.4, 39, 53.4, color=GOLD)

# ---- ② eight domains (red title, no container box) ---------------------------
ax.text(25, 37.2, "② calibrate — eight domains, evidence-ordered",
        fontsize=6.2, color=RED, ha="center", fontweight="bold")
domains = ["gzbd\n(boundary)", "entities\n(grouping)", "auxchain\n(auxiliary)",
           "fault-contact\n(activity)", "gzeeb\n(fault 3-axis)",
           "attitudes,\nfossils, folds", "inferred\n(cover audit)"]
dx0, dy = 4, 29.8
for i, d in enumerate(domains):
    bx = dx0 + (i % 4) * 8.9
    by = dy - (i // 4) * 7.0
    ax.add_patch(FancyBboxPatch((bx, by), 8.3, 5.2, boxstyle="round,pad=0.4",
                                fc="white", ec="none"))
    ax.text(bx + 4.15, by + 2.6, d, ha="center", va="center", fontsize=5.2,
            color="#272727")

# ---- three-level inference band ----------------------------------------------
box(49.5, 28.5, 12, 7.4, LGOLD, GOLD, "L2 codebook\nMLE + registry\n+ mapping table", fs=5.4)
box(64.5, 28.5, 12, 7.4, LGOLD, GOLD, "L3 inheritance\nall same-code\nsegments", fs=5.4)
box(79.5, 28.5, 12, 7.4, LGOLD, GOLD, "falsification\nregister\n(J = K + λF)", fs=5.4)
arrow(46.5, 31.9, 49.3, 31.9, color=GOLD)
arrow(61.7, 31.9, 64.3, 31.9, color=GOLD)
arrow(76.7, 31.9, 79.3, 31.9, color=GOLD)

# ---- materialization + semantic emission -------------------------------------
box(32, 13, 14, 6.5, "#EDEDED", GREY, "②b materialize\n(baseline → terminal L1)", fs=5.4)
box(55, 13, 20, 6.5, "#EDEDED", GREY, "GeoSciML emission\nsemantic slots only", fs=5.4)
arrow(38, 19.8, 38, 22.4, color=GREY)
arrow(52, 16.2, 54.8, 16.2, color=GREY)
box(88, 13, 10, 6.5, "#EDEDED", GREY, "gap report\n(adjudication\ncards)", fs=5.2)

# ---- guards -------------------------------------------------------------------
box(2, 5, 30, 5.5, "white", GREY, "guards: 11-file preflight · build freshness\n· mapping-table staleness", fs=5.2, ls=(0, (2, 1.4)))
box(34, 5, 64, 5.5, "white", GREY,
    "adjudication loop: editable mapping table → deterministic replay → revert = byte-identical", fs=5.2, ls=(0, (2, 1.4)))

fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig2_pipeline_architecture.svg",
            bbox_inches="tight")
fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig2_pipeline_architecture.pdf",
            bbox_inches="tight")
print("fig2 saved (v3)")
