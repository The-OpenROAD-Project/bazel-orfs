#!/usr/bin/env python3
"""Draw the annotated top level of XSCore: what is wrong, and where it is.

    python3 test/coremark_joule/designs/asap7/xiangshan/xscore_problems.py

Writes xscore_problems.png beside it. The figure carries illustration and
labels only; what each numbered marker means is in README.md next to it,
so the picture stays readable at any width and the words stay editable.

Every number and every rectangle below was asked of the baseline's routed
checkpoint through the odb-debug session (.claude/commands/odb-debug.md),
not read out of a log. The drawing is qualitative: the geometry is to
scale, the congestion overlay is a coarse sample, and the five callouts
are a judgement about which measured facts cost the most clock period.
Re-measure and edit the tables here when the baseline moves.
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

DIE_W, DIE_H = 3623.968, 2147.188

# hardened blocks: name, x, y, size, pins, clock pin capacitance in its liberty
BLOCKS = [
    ("Frontend", 10, 102, 955, 3290, 60906),
    ("MemBlock", 1025, 32, 996, 10494, 145071),
    ("VecRegionModule", 2081, 233, 808, 9252, 32823),
    ("Region_1", 2949, 391, 665, 5098, 7186),
]

# generated register files, placed FIRM into the parent's rows
ARRAYS = [
    ("RobEntryFile", 70, 1882, 318, 193),
    ("IntRegFile", 448, 1832, 406, 243),
    ("RenameBufferFile", 914, 1883, 307, 192),
]

# every top level port sits on one segment of the bottom edge
PORT_X0, PORT_X1, PORT_N = 1000.0, 2000.0, 4311

# route-0 overflow, sampled every 8th gcell on each layer and binned 24x24
# over the die. Rows are printed bottom-up, as the die is drawn.
NB = 24
OVERFLOW = [
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    [0] * 24,
    # fmt: off
    [26, 187, 438, 516, 592, 814, 797, 647, 330, 255, 1099, 396,
     88, 454, 305, 553, 345, 705, 228, 365, 678, 122, 0, 0],
    [0, 0, 0, 0, 0, 143, 1121, 745, 886, 416, 2364, 1030,
     819, 65, 1570, 1318, 716, 708, 413, 1358, 1733, 291, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 2, 24, 27, 589, 689,
     5, 13, 618, 92, 230, 39, 0, 12, 6, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 77,
     0, 0, 2, 19, 8, 6, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 350, 780, 419, 8,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 1, 395, 744, 948, 31,
     98, 393, 99, 0, 0, 191, 1567, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 764, 1500, 223, 16, 3, 33,
     66, 93, 441, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 649, 953, 27, 0, 0, 0,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    # fmt: on
    [0] * 24,
    [0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 9, 0, 0, 0, 0, 17, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 8, 0, 0, 0, 0, 25, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0] * 24,
]

# the five, in the order they cost clock period: only the number and
# where the marker lands on the die. What each one says is in README.md,
# so the figure carries illustration and labels, nothing else.
MARKERS = [
    (1, 1120, 900),
    (2, 1760, 1125),
    (3, 1500, 20),
    (4, 3010, 1130),
    (5, 1520, 1975),
]


def main():
    fig = plt.figure(figsize=(12.5, 8.0))
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.98])

    ax.add_patch(
        Rectangle((0, 0), DIE_W, DIE_H, fc="#f7f7f4", ec="0.25", lw=1.6, zorder=0)
    )

    # congestion, coarse. Only the overflowing bins get any ink.
    bw, bh = DIE_W / NB, DIE_H / NB
    top = max(max(r) for r in OVERFLOW)
    for j, row in enumerate(OVERFLOW):
        for i, v in enumerate(row):
            if v:
                ax.add_patch(
                    Rectangle(
                        (i * bw, j * bh),
                        bw,
                        bh,
                        fc="#d7301f",
                        alpha=0.12 + 0.55 * (v / top) ** 0.5,
                        ec="none",
                        zorder=1,
                    )
                )

    for name, x, y, s, pins, cap in BLOCKS:
        ax.add_patch(
            Rectangle((x, y), s, s, fc="#9ecae1", ec="#08519c", lw=1.4, zorder=2)
        )
        ax.text(
            x + s / 2,
            y + s / 2 + 55,
            name,
            ha="center",
            va="center",
            fontsize=11,
            weight="bold",
            color="#08306b",
            zorder=3,
        )
        ax.text(
            x + s / 2,
            y + s / 2 - 45,
            "%d x %d um\n%s pins,  clk pin %s fF" % (s, s, f"{pins:,}", f"{cap:,}"),
            ha="center",
            va="center",
            fontsize=8.5,
            color="#08306b",
            zorder=3,
        )

    for name, x, y, w, h in ARRAYS:
        ax.add_patch(
            Rectangle((x, y), w, h, fc="#c7e9c0", ec="#238b45", lw=1.2, zorder=2)
        )
        ax.text(
            x + w / 2,
            y + h / 2,
            name,
            ha="center",
            va="center",
            fontsize=8,
            color="#00441b",
            zorder=3,
        )

    ax.plot(
        [PORT_X0, PORT_X1],
        [0, 0],
        color="#cc4c02",
        lw=6,
        solid_capstyle="butt",
        zorder=4,
    )
    ax.text(
        (PORT_X0 + PORT_X1) / 2,
        -100,
        "%s ports, all on this 1,000 um of edge" % f"{PORT_N:,}",
        ha="center",
        fontsize=9,
        color="#cc4c02",
        weight="bold",
    )

    # the legend is a label on the picture, not prose about it
    ax.add_patch(
        Rectangle((2430, 2215), 95, 60, fc="#d7301f", alpha=0.5, ec="none", clip_on=False)
    )
    ax.text(
        2555,
        2245,
        "route-0 overflow",
        va="center",
        fontsize=9,
        color="#d7301f",
    )
    ax.text(
        0,
        2245,
        "XSCore on asap7:  %d x %d um,  4,093,220 instances,  3,705,850 nets"
        % (DIE_W, DIE_H),
        ha="left",
        va="center",
        fontsize=10.5,
        weight="bold",
        color="0.2",
    )

    for n, x, y in MARKERS:
        ax.add_patch(plt.Circle((x, y), 82, fc="#d7301f", ec="white", lw=1.8, zorder=6))
        ax.text(
            x,
            y,
            str(n),
            ha="center",
            va="center",
            color="white",
            fontsize=13,
            weight="bold",
            zorder=7,
        )

    ax.set_xlim(-160, DIE_W + 280)
    ax.set_ylim(-240, DIE_H + 200)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)

    out = os.path.join(HERE, "xscore_problems.png")
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
