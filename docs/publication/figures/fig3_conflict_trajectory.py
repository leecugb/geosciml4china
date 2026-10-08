# -*- coding: utf-8 -*-
"""Fig. 3 | Conflict-register trajectory (git-verifiable staged series).

Yingjisha: 96 → 136 → 140 → 7 across four committed pipeline stages.
Kurgan: flat 22 — onboarded after framework finalization (no inherited debt).
Layout: clean line plot; values above markers with white padding; stage
explanations as two-line x tick labels (no floating annotation boxes).
"""
import matplotlib as mpl
import matplotlib.pyplot as plt

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 7,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "legend.frameon": False,
})

BLUE = "#0F4D92"
RED = "#B64342"

ys_ying = [96, 136, 140, 7]
xs = [0, 1, 2, 3]

fig, ax = plt.subplots(figsize=(4.4, 3.0))

ax.plot(xs, ys_ying, "-o", color=BLUE, lw=1.4, ms=4.5, zorder=3,
        label="Yingjisha (staged calibration)")
ax.plot([0, 3], [22, 22], "--", color=RED, lw=1.2, zorder=2,
        label="Kurgan (onboarded at final framework)")
ax.scatter([0], [22], color=RED, s=14, zorder=4)

# values above markers, white padding to clear the line
for x, y in zip(xs, ys_ying):
    ax.annotate(str(y), (x, y), xytext=(0, 7), textcoords="offset points",
                ha="center", va="bottom", fontsize=6.4, color="#272727",
                zorder=5, annotation_clip=False,
                bbox=dict(boxstyle="square,pad=0.12", fc="white", ec="none"))
ax.annotate("22", (0, 22), xytext=(0, 7), textcoords="offset points",
            ha="center", va="bottom", fontsize=6.4, color=RED, zorder=5,
            annotation_clip=False,
            bbox=dict(boxstyle="square,pad=0.12", fc="white", ec="none"))

ax.set_xticks(xs)
ax.set_xticklabels(
    ["S1\nboundary/nappe/\nhook evidence",
     "S2\nsemantic\ndecoupling",
     "S3\ndip-side channel\n+ unification",
     "S4\nthree-level\nlogic"],
    fontsize=5.4)
ax.set_xlabel("Committed pipeline stage (git-verifiable)")
ax.set_ylabel("Registered conflict banners (A23 baseline)")
ax.set_ylim(0, 175)
ax.legend(loc="upper right", fontsize=6, handlelength=1.6)

fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig3_conflict_trajectory.svg",
            bbox_inches="tight")
fig.savefig(r"D:\geosciml4china\docs\publication\figures\fig3_conflict_trajectory.pdf",
            bbox_inches="tight")
print("fig3 saved (v2)")
