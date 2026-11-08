"""Draws the diagrams in docs/cached-parallel-synthesis.md.

    bazelisk run //docs/images:parallel_synthesis_diagrams

writes the PNGs next to this file; pass a directory to write them there.
Look at each one before committing it: matplotlib does not complain when
a label overflows its box.
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.environ["BUILD_WORKSPACE_DIRECTORY"], "docs", "images")
)

INK = "#1f2328"
MUTED = "#57606a"
BLUE = "#ddf4ff"
BLUE_EDGE = "#0969da"
GREEN = "#dafbe1"
GREEN_EDGE = "#1a7f37"
GREY = "#f6f8fa"
GREY_EDGE = "#8c959f"
ORANGE = "#fff1e5"
ORANGE_EDGE = "#bc4c00"
RED = "#ffebe9"
RED_EDGE = "#cf222e"


def box(
    ax, x, y, w, h, text, fc=GREY, ec=GREY_EDGE, size=9, weight="normal", dashed=False
):
    ax.add_patch(
        FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            fc=fc,
            ec=ec,
            lw=1.3,
            ls="--" if dashed else "-",
        )
    )
    ax.text(
        x, y, text, ha="center", va="center", fontsize=size, color=INK, weight=weight
    )


def arrow(ax, x0, y0, x1, y1, color=MUTED):
    ax.annotate(
        "",
        xy=(x1, y1),
        xytext=(x0, y0),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.1, shrinkA=0, shrinkB=0),
    )


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    return fig, ax


def flow():
    """The action graph with a pinned SYNTH_KEEP_MODULES."""
    fig, ax = canvas(12, 6.4)
    box(ax, 5.2, 5.9, 3.2, 0.5, "Verilog / SystemVerilog sources")
    box(
        ax,
        5.2,
        4.9,
        3.8,
        0.65,
        "canonicalize (slang)\n1_1_yosys_canonicalize.rtlil",
        fc=BLUE,
        ec=BLUE_EDGE,
    )
    arrow(ax, 5.2, 5.65, 5.2, 5.23)
    ax.text(
        7.6,
        5.35,
        "cache barrier 1: src attributes\nstripped; a comment leaves this\nfile byte-identical",
        fontsize=8,
        color=BLUE_EDGE,
        va="center",
    )

    cols = [(1.35, "adder"), (3.95, "counter"), (5.6, None), (7.3, "m")]
    for x, m in cols:
        if m is None:
            ax.text(x, 3.45, "...", ha="center", va="center", fontsize=14, color=MUTED)
            ax.text(x, 2.15, "...", ha="center", va="center", fontsize=14, color=MUTED)
            continue
        box(
            ax,
            x,
            3.45,
            2.45,
            0.65,
            f"re-canonicalize {m}\npartition_{m}_canonical.rtlil",
            fc=GREEN,
            ec=GREEN_EDGE,
            size=7.5,
        )
        arrow(ax, 5.2, 4.57, x, 3.78)
        box(
            ax,
            x,
            2.15,
            2.45,
            0.65,
            f"synthesize {m}\npartition_{m}.v",
            fc=ORANGE,
            ec=ORANGE_EDGE,
            size=7.5,
        )
        arrow(ax, x, 3.12, x, 2.48)
        arrow(ax, x, 1.82, 5.2, 1.08)
    box(
        ax,
        10.6,
        2.15,
        2.3,
        0.75,
        "synthesize top\nkept modules blackboxed\npartition_top.v",
        fc=ORANGE,
        ec=ORANGE_EDGE,
        size=7.5,
    )
    arrow(ax, 7.1, 4.9, 10.6, 2.53)
    arrow(ax, 10.6, 1.77, 5.2, 1.08)
    ax.text(
        0.1,
        4.9,
        "cache barrier 2: one slice\nper kept module, the other\nkept modules blackboxed,\n$<n> names numbered locally",
        fontsize=8,
        color=GREEN_EDGE,
        va="center",
    )

    box(
        ax,
        5.2,
        0.75,
        3.8,
        0.65,
        "merge: cat, in module-name order\n1_2_yosys.v  →  1_synth.odb",
        fc=BLUE,
        ec=BLUE_EDGE,
    )
    fig.savefig(
        f"{OUT}/parallel-synthesis-flow.png", bbox_inches="tight", facecolor="white"
    )


def partitioning():
    """Discovered (static N executors) vs pinned (one action per module)."""
    fig, ax = canvas(12, 7.4)
    ax.set_ylim(0.9, 7.4)
    mods = ["A", "B", "C", "D", "E"]

    ax.text(
        3.0,
        7.15,
        "Discovered: SYNTH_HIERARCHICAL=1",
        ha="center",
        fontsize=11,
        weight="bold",
        color=INK,
    )
    ax.text(
        3.0,
        6.82,
        "the kept list is known only at execution time",
        ha="center",
        fontsize=8.5,
        color=MUTED,
    )
    box(
        ax,
        3.0,
        6.25,
        4.2,
        0.55,
        "keep: synth_keep.tcl → 1_1_yosys_keep.rtlil\nkept_modules.json = [A, B, C, D, E]",
        fc=BLUE,
        ec=BLUE_EDGE,
        size=7.5,
    )
    n = 4
    for i, x in enumerate([0.75, 2.25, 3.75, 5.25]):
        mine = [m for j, m in enumerate(mods) if j % n == i]
        label = "modules " + ", ".join(mine)
        box(
            ax,
            x,
            4.9,
            1.3,
            0.75,
            f"partition_{i}\n{label}",
            fc=ORANGE,
            ec=ORANGE_EDGE,
            size=8,
        )
        arrow(ax, 3.0, 5.97, x, 5.28)
    ax.text(
        3.0,
        4.25,
        f"SYNTH_NUM_PARTITIONS = {n} actions, fixed at analysis time\n"
        "(the config.mk DSL defaults it to 32; extra partitions are empty)\n"
        "module k goes to partition k mod N",
        ha="center",
        fontsize=8,
        color=INK,
        va="top",
    )
    ax.text(
        3.0,
        3.35,
        "every partition reads the whole 1_1_yosys_keep.rtlil",
        ha="center",
        fontsize=8,
        color=ORANGE_EDGE,
        va="top",
    )
    box(
        ax,
        3.0,
        2.15,
        4.9,
        1.0,
        "edit module B:\nkeep.rtlil changes, so every partition reruns.\n"
        "Add a kept module: the list shifts, and\nthe partitions' module sets change",
        fc=RED,
        ec=RED_EDGE,
        size=8,
    )

    ax.plot([6.15, 6.15], [1.5, 7.3], color=GREY_EDGE, lw=0.8, ls=":")

    ax.text(
        9.1,
        7.15,
        "Pinned: SYNTH_KEEP_MODULES",
        ha="center",
        fontsize=11,
        weight="bold",
        color=INK,
    )
    ax.text(
        9.1,
        6.82,
        "the kept list is known at analysis time",
        ha="center",
        fontsize=8.5,
        color=MUTED,
    )
    box(
        ax,
        9.1,
        6.25,
        4.2,
        0.55,
        "canonicalize → 1_1_yosys_canonicalize.rtlil\n(no keep step)",
        fc=BLUE,
        ec=BLUE_EDGE,
        size=7.5,
    )
    for x, m in zip([6.85, 7.97, 9.1, 10.23, 11.35], mods):
        box(ax, x, 5.2, 0.98, 0.5, f"slice {m}", fc=GREEN, ec=GREEN_EDGE, size=8)
        arrow(ax, 9.1, 5.97, x, 5.45)
        box(ax, x, 4.35, 0.98, 0.5, f"synth {m}", fc=ORANGE, ec=ORANGE_EDGE, size=8)
        arrow(ax, x, 4.95, x, 4.6)
    ax.text(
        9.1,
        3.85,
        "one slice and one synthesis action per module,\n"
        "named by the module; Bazel spreads them over\nlocal cores or remote executors",
        ha="center",
        fontsize=8,
        color=INK,
        va="top",
    )
    ax.text(
        9.1,
        3.0,
        "each partition reads only its own slice",
        ha="center",
        fontsize=8,
        color=GREEN_EDGE,
        va="top",
    )
    box(
        ax,
        9.1,
        2.15,
        4.9,
        1.0,
        "edit module B:\nslice B and synth B rerun, and the top.\n"
        "Slices A, C, D, E rerun byte-identical,\nso their synthesis is skipped",
        fc=GREEN,
        ec=GREEN_EDGE,
        size=8,
    )

    ax.text(
        6.0,
        1.15,
        "Both: the top module is its own action, and the outputs are concatenated into 1_2_yosys.v.",
        ha="center",
        fontsize=8.5,
        color=MUTED,
    )
    fig.savefig(
        f"{OUT}/parallel-synthesis-partitioning.png",
        bbox_inches="tight",
        facecolor="white",
    )


def remote():
    """A typical in-house setup: shared cache server + remote execution."""
    fig, ax = canvas(13, 6.6)
    ax.set_ylim(0.2, 6.6)
    # Clients.
    clients = [
        (1.5, 5.6, "developer A\nbazelisk build"),
        (1.5, 4.3, "developer B\nbazelisk build"),
        (1.5, 3.0, "CI"),
    ]
    for x, y, t in clients:
        box(ax, x, y, 2.2, 0.8, t, size=8.5)
    ax.text(
        1.5,
        2.15,
        "workstations and CI:\nanalysis, small uploads,\nresults downloaded",
        ha="center",
        va="top",
        fontsize=8,
        color=MUTED,
    )

    # Cache server.
    box(
        ax,
        6.0,
        5.0,
        3.2,
        1.3,
        "Bazel cache server, in-house\naction cache: action key → result\ncontent store: RTLIL, netlists, libs",
        fc=BLUE,
        ec=BLUE_EDGE,
        size=8.5,
    )
    # Orchestrator and workers.
    box(
        ax,
        6.0,
        2.6,
        3.2,
        0.9,
        "remote execution orchestrator\nschedules actions on workers",
        fc=GREY,
        ec=GREY_EDGE,
        size=8.5,
    )
    box(ax, 10.3, 2.6, 2.5, 3.0, "", fc="white", ec=ORANGE_EDGE, dashed=True)
    ax.text(
        10.3,
        3.9,
        "worker pool",
        ha="center",
        va="center",
        fontsize=8.5,
        color=ORANGE_EDGE,
        weight="bold",
    )
    for y, t in zip(
        [3.35, 2.65, 1.95, 1.4], ["synth adder", "synth counter", "synth top", "..."]
    ):
        if t == "...":
            ax.text(10.3, y, "...", ha="center", va="center", fontsize=12, color=MUTED)
        else:
            box(ax, 10.3, y, 2.0, 0.5, t, fc=ORANGE, ec=ORANGE_EDGE, size=8)
    arrow(ax, 7.6, 2.6, 9.05, 2.6)
    ax.annotate(
        "",
        xy=(7.6, 4.75),
        xytext=(10.3, 4.1),
        arrowprops=dict(
            arrowstyle="<|-|>",
            color=ORANGE_EDGE,
            lw=1.3,
            connectionstyle="angle,angleA=90,angleB=0",
            shrinkA=0,
            shrinkB=0,
        ),
    )

    # 1: lookup / hit.
    for x, y, _ in clients:
        arrow(ax, 2.6, y, 4.4, 5.0, color=BLUE_EDGE)
    ax.text(
        3.05,
        6.25,
        "1. look up each action's key:\na hit downloads the result,\nno synthesis runs anywhere",
        fontsize=8,
        color=BLUE_EDGE,
        va="center",
    )
    # 2: miss -> execute.
    arrow(ax, 2.6, 3.0, 4.4, 2.6)
    ax.text(
        2.75, 2.35, "2. a miss is sent\nto be executed", fontsize=8, color=INK, va="top"
    )
    ax.text(
        10.5,
        5.35,
        "3. workers read inputs from,\nand write results to, the\ncache: the next build hits",
        fontsize=8,
        color=ORANGE_EDGE,
        ha="left",
        va="center",
    )

    box(
        ax,
        6.0,
        0.6,
        8.6,
        0.5,
        "nothing beats a cached result: a hit costs a download, a miss costs a synthesis",
        fc=GREEN,
        ec=GREEN_EDGE,
        size=9,
        weight="bold",
    )
    fig.savefig(
        f"{OUT}/parallel-synthesis-remote.png", bbox_inches="tight", facecolor="white"
    )


def loop():
    """Turnaround is QoR: human, AI and build, rinse and repeat."""
    fig, ax = canvas(9, 5.6)
    box(
        ax,
        4.5,
        4.9,
        3.4,
        0.9,
        "Human\nsets the goal, judges each result",
        fc=BLUE,
        ec=BLUE_EDGE,
        size=10,
    )
    box(
        ax,
        7.2,
        1.0,
        3.0,
        1.1,
        "AI\nreads worst paths and logs,\nproposes the next change",
        fc=GREEN,
        ec=GREEN_EDGE,
        size=10,
    )
    box(
        ax,
        1.8,
        1.0,
        3.0,
        1.1,
        "Build\nBazel, cached per module:\nonly what changed rebuilds",
        fc=ORANGE,
        ec=ORANGE_EDGE,
        size=10,
    )
    curve = dict(arrowstyle="-|>", color=MUTED, lw=1.3, shrinkA=0, shrinkB=0)
    ax.annotate(
        "",
        xy=(7.4, 1.6),
        xytext=(6.25, 4.9),
        arrowprops=dict(curve, connectionstyle="arc3,rad=-0.35"),
    )
    ax.annotate(
        "",
        xy=(2.75, 4.9),
        xytext=(1.6, 1.6),
        arrowprops=dict(curve, connectionstyle="arc3,rad=-0.35"),
    )
    arrow(ax, 5.65, 1.0, 3.35, 1.0)
    ax.text(7.9, 3.4, "the goal,\nwhat to try", fontsize=9, color=MUTED, va="center")
    ax.text(
        1.1, 3.4, "WNS, area,\nlogs", fontsize=9, color=MUTED, va="center", ha="right"
    )
    ax.text(4.5, 1.2, "a change", fontsize=9, color=MUTED, ha="center")
    ax.text(
        4.5,
        3.2,
        "rinse and repeat",
        fontsize=12,
        color=INK,
        ha="center",
        weight="bold",
    )
    ax.text(
        4.5,
        2.55,
        "one turn is one try;\nthe build sets the turns per day.\n"
        "Every build but the tapeout one is a question.",
        fontsize=9,
        color=MUTED,
        ha="center",
        va="center",
    )
    fig.savefig(
        f"{OUT}/parallel-synthesis-loop.png", bbox_inches="tight", facecolor="white"
    )


# XiangShan's XSTile clock period after global route, KPI runs 1 to 21:
# the KPI table in test/coremark_joule/designs/asap7/xiangshan/README.md.
XSTILE_GRT_PS = [
    6186,
    6186,
    6186,
    4991,
    5681,
    5118,
    5402,
    3860,
    3330,
    3264,
    3256,
    3162,
    3386,
    3276,
    2406,
    9431,
    2504,
    2383,
    2250,
    2212,
    2206,
]


def cliffs():
    """Early the landscape is smooth; as the design tightens it has cliffs."""
    fig, (left, right) = plt.subplots(
        1, 2, figsize=(12, 4.4), dpi=150, gridspec_kw={"width_ratios": [1, 1.5]}
    )
    fig.patch.set_facecolor("white")

    xs = [i / 100 for i in range(101)]
    left.plot(xs, [(x - 0.62) ** 2 for x in xs], color=GREY_EDGE, lw=1.5)
    steps = [0.05 + i * 0.063 for i in range(10)]
    left.plot(
        steps, [(x - 0.62) ** 2 + 0.012 for x in steps], "o", color=GREEN_EDGE, ms=5
    )
    left.set_title(
        "early: smooth\nmany cheap tries, each predictable",
        fontsize=10,
        color=INK,
        loc="left",
    )
    left.set_xticks([])
    left.set_yticks([])
    left.set_xlabel("a setting or a change", fontsize=9, color=MUTED)
    left.set_ylabel("period", fontsize=9, color=MUTED)

    runs = list(range(1, len(XSTILE_GRT_PS) + 1))
    right.plot(runs, XSTILE_GRT_PS, "-o", color=BLUE_EDGE, ms=4, lw=1.3)
    right.set_title(
        "tight: cliffs\nXiangShan XSTile, period after global route, per KPI run",
        fontsize=10,
        color=INK,
        loc="left",
    )
    right.set_xticks([1, 5, 10, 15, 21])
    right.set_ylim(0, 10500)
    right.set_xlabel("KPI run, 2026-09-26 to 2026-10-31", fontsize=9, color=MUTED)
    right.set_ylabel("ps", fontsize=9, color=MUTED)
    right.annotate(
        "15: setup repair at global route\nwith the route's parasitics,\n3,276 to 2,406 ps",
        xy=(15, 2406),
        xytext=(9.2, 6200),
        fontsize=8,
        color=GREEN_EDGE,
        arrowprops=dict(arrowstyle="-|>", color=GREEN_EDGE, lw=0.9),
    )
    right.annotate(
        "16: hold repair blew up,\n9,431 ps",
        xy=(16, 9431),
        xytext=(17.2, 8200),
        fontsize=8,
        color=RED_EDGE,
        arrowprops=dict(arrowstyle="-|>", color=RED_EDGE, lw=0.9),
    )
    for ax in (left, right):
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=8)
    fig.tight_layout()
    fig.savefig(
        f"{OUT}/parallel-synthesis-cliffs.png", bbox_inches="tight", facecolor="white"
    )


def illustrative(ax, x, y):
    ax.text(
        x,
        y,
        "ILLUSTRATIVE: MADE-UP NUMBERS",
        fontsize=8,
        color=RED_EDGE,
        weight="bold",
        ha="right",
    )


def turn():
    """One turn of the loop on XSTile, to scale (KPI run 17)."""
    fig, ax = canvas(12, 2.6)
    # minutes; 1 unit = 30 min
    x, y, h = 0.3, 1.2, 0.7
    parts = [
        (10, BLUE, BLUE_EDGE, ""),
        (10, GREEN, GREEN_EDGE, ""),
        (234, ORANGE, ORANGE_EDGE, "place, 3.9 h"),
        (40, ORANGE, ORANGE_EDGE, "CTS 40 min"),
        (45, ORANGE, ORANGE_EDGE, "grt 45 min"),
    ]
    for minutes, fc, ec, label in parts:
        w = minutes / 30
        ax.add_patch(plt.Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1.1))
        if label:
            ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=9)
        x += w
    ax.text(
        0.3,
        2.25,
        "One turn of the loop on XiangShan's XSTile, to scale",
        fontsize=10,
        color=INK,
        weight="bold",
    )
    arrow(ax, 0.47, 1.15, 0.47, 0.72, color=BLUE_EDGE)
    ax.text(0.3, 0.5, "human ~10 min", fontsize=8, color=BLUE_EDGE)
    arrow(ax, 0.8, 1.15, 0.8, 0.85, color=GREEN_EDGE)
    ax.text(0.95, 0.88, "AI ~10 min", fontsize=8, color=GREEN_EDGE)
    ax.text(
        6.5,
        0.5,
        "the build: about 5.3 h of CPU-bound EDA",
        fontsize=9,
        color=MUTED,
        ha="center",
    )
    ax.text(
        11.7,
        0.05,
        "build: KPI run 17 (kpi.json); human and AI minutes illustrative",
        fontsize=7.5,
        color=MUTED,
        ha="right",
    )
    fig.savefig(
        f"{OUT}/parallel-synthesis-turn.png", bbox_inches="tight", facecolor="white"
    )


def gpl_split():
    """Global placement: speeding up one share of the time bounds the whole (Amdahl)."""
    fig, ax = canvas(12, 3.4)
    ax.text(
        0.2,
        3.1,
        "Global placement on a large design",
        fontsize=10,
        color=INK,
        weight="bold",
    )
    illustrative(ax, 11.8, 3.1)
    x0, width = 1.6, 10.0
    split = [
        (0.10, BLUE, BLUE_EDGE, "10 %"),
        (0.55, ORANGE, ORANGE_EDGE, "timing-driven: STA + repair, 55 %"),
        (0.20, ORANGE, ORANGE_EDGE, "routability, 20 %"),
        (0.15, GREY, GREY_EDGE, "I/O, init, 15 %"),
    ]

    def bar(y, speedup):
        x = x0
        for i, (share, fc, ec, label) in enumerate(split):
            w = width * share / (speedup if i == 0 else 1)
            ax.add_patch(plt.Rectangle((x, y), w, 0.6, fc=fc, ec=ec, lw=1.1))
            if w > 0.5:
                ax.text(
                    x + w / 2, y + 0.3, label, ha="center", va="center", fontsize=8.5
                )
            x += w
        return x

    ax.text(0.2, 2.25, "as is", fontsize=9, color=INK, va="center")
    bar(1.95, 1)
    ax.text(
        x0,
        1.7,
        "Nesterov density + wirelength: the data-parallel share",
        fontsize=8,
        color=BLUE_EDGE,
    )
    ax.text(0.2, 1.05, "share 40x", fontsize=9, color=INK, va="center")
    end = bar(0.75, 40)
    ax.plot([end, end], [0.65, 1.45], color=RED_EDGE, ls="--", lw=1)
    ax.text(
        end + 0.1, 1.05, "1.1x", fontsize=10, color=RED_EDGE, weight="bold", va="center"
    )
    ax.text(
        x0,
        0.3,
        "The data-parallel share 40 times faster makes the whole 1.1 times faster (Amdahl): the rest is unchanged.",
        fontsize=8,
        color=MUTED,
    )
    fig.savefig(
        f"{OUT}/parallel-synthesis-gpl.png", bbox_inches="tight", facecolor="white"
    )


flow()
partitioning()
remote()
loop()
cliffs()
turn()
gpl_split()
