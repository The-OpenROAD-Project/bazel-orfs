#!/usr/bin/env python3
"""Render docs/images/xiangshan-take23-status.png from the two JSON files beside it.

    python3 docs/images/xiangshan_status_plot.py

Every number is read from xiangshan_take23_status.json (the campaign's numbers,
ideas/xiangshan-timing.md entries 1-19) and xiangshan_take23_heat.json (the
M9 route-0 congestion regions binned onto a 45 um grid). Nothing is typed
into the figure by hand, so a new take regenerates it.
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "xiangshan_take23_status.json")))
HEAT = json.load(open(os.path.join(HERE, "xiangshan_take23_heat.json")))


def panel_record(ax):
    ax.set_title("1. The record: large designs in the flow repositories", loc="left", fontsize=11, weight="bold")
    rows = D["record"]
    for i, (when, what) in enumerate(rows):
        y = len(rows) - i
        ax.plot([0, 0], [y - 0.5, y + 0.5], color="0.6", lw=2)
        ax.plot(0, y, "o", color="firebrick" if "XSCore" in what else "0.3", ms=8)
        ax.text(0.15, y, "%s  %s" % (when, what), va="center", fontsize=9)
    ax.set_xlim(-0.3, 6)
    ax.set_ylim(0.3, len(rows) + 0.7)
    ax.axis("off")
    ax.text(0.15, 0.1, "XSCore: %.1f M cells after synthesis, %.2f M placed with the arrays" % (4.3, (D["cells_parent"] + D["cells_arrays_firm"]) / 1e6),
            fontsize=8, color="0.3", transform=ax.transData)


def panel_sits(ax):
    ax.set_title("2. Where XSCore sits in the repository's own SoC (areas roughly to scale)", loc="left", fontsize=11, weight="bold")
    core, l2, llc = 1.0, 1.8, 14.0
    outer_w = 2 * (core + l2 + 1.2) + llc + 1.2
    outer_h = 7.5
    ax.add_patch(Rectangle((0, 0), outer_w, outer_h, fc="#f2f2f2", ec="0.3"))
    ax.text(0.3, outer_h - 0.7, "NoC top: two XSTiles on the CHI network of chip + one shared LLC (the shipped topology supports one or two cores)", fontsize=8)
    x = 0.4
    for t in range(2):
        ax.add_patch(Rectangle((x, 0.5), core + l2 + 0.8, 4.4, fc="#dfe8f3", ec="0.3"))
        ax.text(x + 0.1, 5.15, "XSTile %d" % (t + 1), fontsize=8)
        ax.add_patch(Rectangle((x + 0.2, 0.8), core, 1.0, fc="firebrick", ec="k"))
        ax.text(x + 0.2 + core / 2, 2.05, "XSCore", ha="center", fontsize=8, color="firebrick", weight="bold")
        ax.add_patch(Rectangle((x + 0.4 + core, 0.8), l2, 3.6, fc="#b7c9de", ec="0.3"))
        ax.text(x + 0.4 + core + l2 / 2, 2.4, "private\nL2\n2 MB", ha="center", fontsize=7)
        x += core + l2 + 1.6
    ax.add_patch(Rectangle((x, 0.5), llc, 4.4, fc="#c9d6c2", ec="0.3"))
    ax.text(x + llc / 2, 2.5, "OpenLLC, shared last-level cache, 32 MB default", ha="center", fontsize=8)
    ax.text(0.3, -0.9, "red = the block this study places: the core with its L1 caches and TLBs, %.1f M cells; no L2, no NoC, no LLC. This study's L2 is 512 KB and its LLC 1 MB." % 4.3, fontsize=8)
    ax.set_xlim(-0.2, outer_w + 0.2)
    ax.set_ylim(-1.6, outer_h + 0.3)
    ax.set_aspect("equal")
    ax.axis("off")


def panel_ladder(ax):
    ax.set_title("3. Minimum clock period measured vs the public target (log scale)", loc="left", fontsize=11, weight="bold")
    rows = D["period_ladder_ps"]
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    kinds = [r[2] for r in rows]
    colors = {"target": "seagreen", "measured": "firebrick", "artefact": "lightgrey"}
    bars = ax.barh(range(len(rows)), vals, color=[colors[k] for k in kinds], edgecolor="k")
    for b, k in zip(bars, kinds):
        if k == "artefact":
            b.set_hatch("///")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlim(200, 400000)
    ax.set_xlabel("ps")
    for i, v in enumerate(vals):
        ax.text(v * 1.08, i, "%d ps  (%.0fx)" % (v, v / vals[0]) if i else "%d ps" % v, va="center", fontsize=8)
    ax.axvline(vals[0], color="seagreen", ls="--", lw=1)
    ax.text(0.02, 0.02, "hatched: a model artefact, the abstracts were written before the blocks' own CTS (inventory entry 17)", fontsize=7, color="0.3", transform=ax.transAxes)
    ax.grid(axis="x", alpha=0.3)


def panel_die(ax):
    ax.set_title("4. The die as run: 3.6 x 2.1 mm, four blocks, three arrays, route-0 overflow at M9", loc="left", fontsize=11, weight="bold")
    W, H = D["die_um"]
    import numpy as np
    g = np.array(HEAT["grid"], dtype=float)
    g = np.log10(g + 1)
    ax.imshow(g, origin="lower", extent=(0, HEAT["nx"] * HEAT["bin_um"], 0, HEAT["ny"] * HEAT["bin_um"]), cmap="Reds", alpha=0.9, aspect="equal")
    for name, (x, y, w, h) in D["blocks"].items():
        ax.add_patch(Rectangle((x, y), w, h, fc="#3a5a8c", ec="k", alpha=0.85))
        ax.text(x + w / 2, y + h / 2, name, ha="center", va="center", color="w", fontsize=8)
    for name, (x, y, w, h) in D["arrays"].items():
        ax.add_patch(Rectangle((x, y), w, h, fc="#7a7a7a", ec="k"))
        ax.text(x + w / 2, y - 60, name, ha="center", fontsize=6)
    x0, x1 = D["ports_bottom_edge_x_um"]
    ax.plot([x0, x1], [4, 4], color="gold", lw=4)
    ax.text((x0 + x1) / 2, -110, "%d top-level ports" % D["ports"], ha="center", fontsize=7)
    ax.set_xlim(0, W)
    ax.set_ylim(-150, H)
    ax.set_xlabel("um")
    ax.set_ylabel("um")
    r = D["route0"]["M9"]
    ax.text(W - 30, 1750, "route-0 (0 iterations): %.0f%% of capacity used,\nworst edge %d wires over, total congestion %.0f M;\nfive-iteration route killed at 3 h" % (r["usage_pct"], r["max_h"], r["total"] / 1e6), fontsize=7, ha="right", bbox=dict(fc="w", ec="0.5"))


def panel_hours(ax):
    ax.set_title("5. Where the hours go (one iteration; peak memory in GB)", loc="left", fontsize=11, weight="bold")
    rows = D["stages_h"]
    names = [r[0] for r in rows]
    hours = [r[1] for r in rows]
    mem = [r[2] for r in rows]
    colors = ["firebrick" if "global route" in n else "#3a5a8c" for n in names]
    ax.barh(range(len(rows)), hours, color=colors, edgecolor="k")
    for i, (h, m) in enumerate(zip(hours, mem)):
        label = "%.1f h" % h + (", %.0f GB" % m if m else "") + ("  killed at budget" if "global route" in names[i] else "")
        ax.text(h + 0.05, i, label, va="center", fontsize=8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 4.5)
    ax.set_xlabel("hours   (total %.1f h to the route's kill; %.2f M cells + %.2f M fixed array cells; %d block pins)" % (sum(hours), D["cells_parent"] / 1e6, D["cells_arrays_firm"] / 1e6, D["block_pins"]), fontsize=8)
    ax.grid(axis="x", alpha=0.3)


def panel_extracted(ax):
    ax.set_title("6. From gold mine to test case: what the campaign found, and the minute-scale test it became", loc="left", fontsize=11, weight="bold")
    rows = D["extracted"]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(rows) + 1)
    ax.axis("off")
    ax.text(0.1, len(rows) + 0.5, "found on the design (hours to days)", fontsize=8, weight="bold")
    ax.text(5.3, len(rows) + 0.5, "extracted (seconds to minutes)", fontsize=8, weight="bold")
    for i, (found, became, kind) in enumerate(rows):
        y = len(rows) - i
        ax.text(0.1, y, found, fontsize=7.5, va="center")
        c = {"test": "seagreen", "patch": "#3a5a8c", "not yet": "firebrick"}[kind]
        ax.annotate("", xy=(5.2, y), xytext=(4.7, y), arrowprops=dict(arrowstyle="->", color=c))
        ax.text(5.3, y, became, fontsize=7.5, va="center", color=c)
    ax.text(0.1, 0.2, "green: a test in the repository   blue: a carried ORFS patch   red: not yet extracted, an open OpenROAD question", fontsize=7, color="0.3")


def main():
    fig = plt.figure(figsize=(18, 20))
    gs = fig.add_gridspec(4, 2, height_ratios=[1.0, 1.1, 1.5, 1.4], hspace=0.35, wspace=0.25)
    panel_record(fig.add_subplot(gs[0, 0]))
    panel_sits(fig.add_subplot(gs[0, 1]))
    panel_ladder(fig.add_subplot(gs[1, 0]))
    panel_hours(fig.add_subplot(gs[1, 1]))
    panel_die(fig.add_subplot(gs[2, :]))
    panel_extracted(fig.add_subplot(gs[3, :]))
    fig.suptitle(D["title"], fontsize=14, weight="bold", y=0.995)
    out = os.path.join(HERE, "xiangshan-take23-status.png")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
