#!/usr/bin/env python3
"""Draw the annotated top level of XSCore: what is wrong, and where it is.

    python3 test/coremark_joule/designs/asap7/xiangshan/xscore_problems.py

Writes xscore_problems.png beside it.

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
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

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

# the five, in the order they cost clock period. (x, y) is where the arrow
# lands on the die.
PROBLEMS = [
    (
        1,
        1120,
        900,
        "The clock never reaches the logic",
        "43,715 ps of the 45,985 is the clock arriving at MemBlock's\n"
        "pin. Its abstract was written at the block's place stage,\n"
        "before the block had a clock tree, so the pin presents the\n"
        "whole unbuffered clock net: 145,071 fF, charged by one BUFx24.\n"
        "Same defect in proportion on every block (60,906 / 32,823 /\n"
        "7,186 fF). Fix: abstract each block after its own CTS.",
    ),
    (
        2,
        1760,
        1125,
        "One escape band above the macro row",
        "The blocks fill the bottom 1,050 um edge to edge and nothing\n"
        "routes through them, so every block-to-parent wire escapes\n"
        "through the strip just above. 97% of the sampled route-0\n"
        "overflow is in two 90 um bins there. Fix: the floorplan owes\n"
        "the escape its own channel, not the leftovers.",
    ),
    (
        3,
        1500,
        20,
        "4,311 ports on one metre of edge",
        "Every top level port is on the bottom edge between x=1000 and\n"
        "x=2000, behind MemBlock. Nets that belong on the far side of\n"
        "the die cross it twice. Fix: the parent's pin plan is a\n"
        "top level compromise and has to be drawn as one.",
    ),
    (
        4,
        3010,
        1130,
        "A millimetre per block-to-block hop",
        "MemBlock's output to Region_1's input: 1,793 ps on one parent\n"
        "wire, with timing-driven placement off and post-CTS repair\n"
        "skipped. Second largest term after the clock, and the first\n"
        "one that is about the design rather than the modelling.",
    ),
    (
        5,
        1520,
        1975,
        "No block knows its own period",
        "The three generated register files drop FIRM into the parent's\n"
        "rows; the hardened blocks report no slack at all, because the\n"
        "flow runs with SKIP_REPORT_METRICS. One number describes 4.1 M\n"
        "instances. Fix: a period per block, measured the same way.",
    ),
]


def main():
    fig = plt.figure(figsize=(16.5, 8.0))
    ax = fig.add_axes([0.03, 0.10, 0.535, 0.82])
    tx = fig.add_axes([0.585, 0.09, 0.40, 0.83])
    tx.axis("off")

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
            fontsize=10.5,
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
            fontsize=8,
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
            fontsize=7.5,
            color="#00441b",
            zorder=3,
        )

    ax.plot(
        [PORT_X0, PORT_X1], [0, 0], color="#cc4c02", lw=6, solid_capstyle="butt", zorder=4
    )
    ax.text(
        (PORT_X0 + PORT_X1) / 2,
        -95,
        "%s ports, all on this 1,000 um of edge" % f"{PORT_N:,}",
        ha="center",
        fontsize=8.5,
        color="#cc4c02",
        weight="bold",
    )

    ax.set_xlim(-160, DIE_W + 280)
    ax.set_ylim(-230, DIE_H + 120)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(
        "XSCore on asap7, %d x %d um: 4,093,220 instances, 3,705,850 nets"
        % (DIE_W, DIE_H),
        loc="left",
        fontsize=12,
        weight="bold",
    )

    # the callouts: a numbered disc on the die, the same number in the list
    for n, x, y, head, body in PROBLEMS:
        ax.add_patch(plt.Circle((x, y), 78, fc="#d7301f", ec="white", lw=1.8, zorder=6))
        ax.text(
            x,
            y,
            str(n),
            ha="center",
            va="center",
            color="white",
            fontsize=12,
            weight="bold",
            zorder=7,
        )

    tx.set_xlim(0, 1)
    tx.set_ylim(0, 1)
    tx.text(
        0,
        1.0,
        "The five things between this and 800 ps",
        fontsize=13,
        weight="bold",
        va="top",
    )
    yy = 0.935
    for n, _, _, head, body in PROBLEMS:
        tx.add_patch(
            FancyBboxPatch(
                (0, yy - 0.163),
                1.0,
                0.158,
                boxstyle="round,pad=0.004,rounding_size=0.01",
                fc="#fbf4f2",
                ec="0.85",
                lw=0.8,
                transform=tx.transAxes,
            )
        )
        tx.add_patch(
            plt.Circle(
                (0.028, yy - 0.024),
                0.016,
                fc="#d7301f",
                ec="none",
                transform=tx.transAxes,
            )
        )
        tx.text(
            0.028,
            yy - 0.024,
            str(n),
            ha="center",
            va="center",
            color="white",
            fontsize=9.5,
            weight="bold",
        )
        tx.text(0.06, yy - 0.024, head, fontsize=11, weight="bold", va="center")
        tx.text(0.06, yy - 0.05, body, fontsize=8.6, va="top", color="0.2")
        yy -= 0.175

    fig.text(
        0.03,
        0.048,
        "Minimum clock period today: 45,985 ps (SDC 800 ps, worst reg2reg slack "
        "-45,185 ps). Target: 800 ps.",
        fontsize=10,
        weight="bold",
        color="#d7301f",
    )
    fig.text(
        0.03,
        0.016,
        "A qualitative diagram, generated from the routed ODB through the "
        "odb-debug MCP server: the geometry and the numbers are measured, the "
        "choice of five and their\nranking are a judgement about what needs "
        "fixing in XSCore. Red shading is route-0 overflow, sampled every "
        "eighth gcell on M2-M9 and binned 24 x 24.",
        fontsize=8.2,
        color="0.35",
    )

    out = os.path.join(HERE, "xscore_problems.png")
    fig.savefig(out, dpi=110)
    print(out)


if __name__ == "__main__":
    main()
