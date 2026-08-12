"""Stage 7: conceptual figures for the report's methodology chapters.

These are our own drawings of frameworks described in the cited papers, not copies of the
original authors' artwork. No published figure is reproduced here, and the report captions
them "adapted from" accordingly.

  figs/07_dsr_crispdm.png  design-science activities against CRISP-DM phases
                           (Peffers et al., 2007; Wirth and Hipp, 2000)
  figs/07_leakage.png      how post-arrival information leaks into a feed-error model
                           (Kaufman et al., 2012)
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

import config

FIGS = config.FIGS
BLUE, TEAL, GREY, INK, RUST = "#2b6cb0", "#0d9488", "#94a3b8", "#0f172a", "#c05621"

print("Stage 7: framework figures")

def box(ax, x, y, w, h, text, fc, tc="white", fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
                                linewidth=0, facecolor=fc))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            color=tc, fontsize=fs, fontweight="bold", linespacing=1.35)

def arrow(ax, p, q, color=GREY, lw=1.3, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=11, color=color,
                                 linewidth=lw, linestyle=ls, shrinkA=1, shrinkB=1,
                                 connectionstyle=f"arc3,rad={rad}"))

# Design-science activities on top, the CRISP-DM phase each one corresponds to below.
fig, ax = plt.subplots(figsize=(9.6, 3.0)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
dsr = ["Problem\nidentification", "Objectives of\na solution", "Design and\ndevelopment",
       "Demonstration", "Evaluation", "Communication"]
crisp = ["Business\nunderstanding", "Data\nunderstanding", "Data prep. and\nmodelling",
         "Deployment", "Evaluation", "Deployment"]
X0, W, GAP = 0.0, 0.155, 0.014
Y1, Y2, H = 0.58, 0.18, 0.22
for i, (d, c) in enumerate(zip(dsr, crisp)):
    x = X0 + i * (W + GAP)
    box(ax, x, Y1, W, H, d, BLUE, fs=7.6)
    box(ax, x, Y2, W, H, c, TEAL, fs=7.6)
    if i < len(dsr) - 1:
        arrow(ax, (x + W, Y1 + H / 2), (x + W + GAP, Y1 + H / 2))
        arrow(ax, (x + W, Y2 + H / 2), (x + W + GAP, Y2 + H / 2))
ax.text(0.0, Y1 + H + 0.035, "Design-science activity (Peffers et al., 2007)", ha="left",
        va="bottom", fontsize=8.5, fontweight="bold", color=BLUE)
ax.text(0.0, Y2 + H + 0.035, "CRISP-DM phase (Wirth and Hipp, 2000)", ha="left",
        va="bottom", fontsize=8.5, fontweight="bold", color=TEAL)
arrow(ax, (1.0, 0.10), (0.0, 0.10), GREY, lw=1.2, rad=-0.10)
ax.text(0.5, 0.10, "evaluation feeds back into design", ha="center", va="center",
        fontsize=8, color=GREY, style="italic",
        bbox=dict(boxstyle="square,pad=0.35", facecolor="white", edgecolor="none"))
plt.savefig(FIGS / "07_dsr_crispdm.png", dpi=config.FIG_DPI, bbox_inches="tight"); plt.close()
print("  wrote 07_dsr_crispdm.png")

# A timeline with the model underneath it: everything left of the publication instant
# is admissible, anything to the right of it is leakage.
fig, ax = plt.subplots(figsize=(8.2, 3.4)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
TL = 0.66
ax.plot([0.06, 0.95], [TL, TL], color=INK, lw=1.3)
ax.text(0.955, TL, "time", ha="left", va="center", fontsize=8.5, color=GREY, style="italic")
marks = [(0.22, "prediction\npublished"), (0.58, "vehicle\narrives"), (0.84, "feed value\nrevised")]
for x, lab in marks:
    ax.plot([x], [TL], marker="o", color=INK, ms=6.5, zorder=3)
    ax.text(x, TL + 0.035, lab, ha="center", va="bottom", fontsize=8.5, color=INK, linespacing=1.3)
box(ax, 0.055, 0.06, 0.33, 0.20, "Feed-error model\n(feature set)", INK, fs=9)
arrow(ax, (0.22, TL - 0.03), (0.22, 0.275), TEAL, lw=1.8)
ax.text(0.235, 0.42, "admissible: known\nat publication", ha="left", va="center",
        fontsize=8.3, color=TEAL, fontweight="bold", linespacing=1.3)
arrow(ax, (0.58, TL - 0.03), (0.34, 0.275), RUST, lw=1.8, ls="--", rad=-0.30)
arrow(ax, (0.84, TL - 0.03), (0.38, 0.265), RUST, lw=1.8, ls="--", rad=-0.22)
ax.text(0.63, 0.17, "leakage: post-arrival or\nrevised values entering\nthe feature set",
        ha="left", va="center", fontsize=8.3, color=RUST, fontweight="bold", linespacing=1.35)
ax.text(0.5, 0.965, "Only information available before the publication instant may enter the model",
        ha="center", va="top", fontsize=9, color=INK, fontweight="bold")
plt.savefig(FIGS / "07_leakage.png", dpi=config.FIG_DPI, bbox_inches="tight"); plt.close()
print("  wrote 07_leakage.png")
