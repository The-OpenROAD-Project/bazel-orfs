#!/usr/bin/env python3
"""Draw the KPI: XiangShan's minimum clock period over time, against the target.

    python3 test/coremark_joule/designs/asap7/xiangshan/kpi.py

Reads kpi.json beside it and writes kpi.png. Add a row to the json when a
change moves the number, re-run this, commit both.

The red series is the design's minimum clock period, the KPI: the largest
of the parent's period and each block's, since the design is only as fast
as its slowest part. The parent and each block are drawn dashed beneath
it, each a period that has to be at or below the design's. The parent's
number is its reg2reg group with its clock tree; each block's is that
block alone at its own place stage, against an ideal clock. A run that
did not measure the blocks gives only a lower bound, drawn hollow.

The axis is logarithmic because the gap is three orders of magnitude and a
linear axis would draw every run as the same point. That is the honest
picture: a change worth a few hundred picoseconds is invisible here until
the modelling artefacts are gone.
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


# the blocks, in the order they are drawn, with a colour each
BLOCK_COLORS = {
    "MemBlock": "#2171b5",
    "Frontend": "#6baed6",
    "CoupledL2": "#d94801",
    "VecRegionModule": "#238b45",
    "Region_1": "#807dba",
    "FltRegionModule": "#807dba",
}
# a block the table does not name is still drawn, in grey
OTHER_COLOR = "#737373"
# the least vertical distance between two end labels, in points
LABEL_GAP_PT = 10


def spread(labels, ax, fig):
    """Vertical offsets, in points, that keep the end labels apart: each
    label sits at its point unless that is within LABEL_GAP_PT of the one
    above it, in which case it moves down just enough."""
    to_pt = 72.0 / fig.dpi
    ys = [ax.transData.transform((x, y))[1] * to_pt for x, y, *_ in labels]
    order = sorted(range(len(labels)), key=lambda i: -ys[i])
    placed, offsets = None, [0.0] * len(labels)
    for i in order:
        y = ys[i]
        if placed is not None and placed - y < LABEL_GAP_PT:
            y = placed - LABEL_GAP_PT
        offsets[i] = y - ys[i]
        placed = y
    return offsets


def main():
    with open(os.path.join(HERE, "kpi.json")) as f:
        d = json.load(f)
    runs = d["runs"]
    target = d["target_ps"]
    xs = list(range(len(runs)))
    parent = [r["parent_ps"] for r in runs]
    # the design is as fast as its slowest part: the parent or a block
    design = [max([r["parent_ps"]] + list(r.get("blocks", {}).values())) for r in runs]
    bounded = [not r.get("blocks") for r in runs]

    fig, ax = plt.subplots(figsize=(10, 5.2))

    # the parts, dashed: the parent, and each block against an ideal clock
    # at its own place stage
    names = list(BLOCK_COLORS) + sorted(
        {n for r in runs for n in r.get("blocks", {})} - set(BLOCK_COLORS)
    )
    labels = []  # (x, y, text, color, bold): the end of each series
    for name in names:
        pts = [
            (x, r["blocks"][name])
            for x, r in zip(xs, runs)
            if name in r.get("blocks", {})
        ]
        if not pts:
            continue
        color = BLOCK_COLORS.get(name, OTHER_COLOR)
        bx = [p[0] for p in pts]
        by = [p[1] for p in pts]
        ax.plot(bx, by, "s--", color=color, lw=1.2, ms=4, zorder=2)
        labels.append((bx[-1], by[-1], "%s  %s ps" % (name, f"{by[-1]:,}"), color, False))
    top = runs[-1].get("measured", "").split("_")[0] or "parent"
    ax.plot(xs, parent, "o--", color="0.3", lw=1.2, ms=4, zorder=2)
    labels.append((xs[-1], parent[-1], "%s parent  %s ps" % (top, f"{parent[-1]:,}"), "0.3", False))

    # the design, red: the KPI
    ax.plot(xs, design, "-", color="firebrick", lw=2.4, zorder=3)
    for x, y, b in zip(xs, design, bounded):
        ax.plot(x, y, "o", ms=8, zorder=4, color="firebrick",
                markerfacecolor="white" if b else "firebrick")
    labels.append((xs[-1], design[-1], "design  %s ps" % f"{design[-1]:,}", "firebrick", True))

    ax.set_yscale("log")
    lo = min([target] + [v for r in runs for v in r.get("blocks", {}).values()])
    ax.set_ylim(min(target, lo) * 0.45, max(design) * 2.2)
    ax.set_xlim(-0.55, len(runs) - 1 + 0.95)
    for (x, y, text, color, bold), dy in zip(labels, spread(labels, ax, fig)):
        ax.annotate(
            text,
            (x, y),
            textcoords="offset points",
            xytext=(9, dy - 3),
            fontsize=8.5 if bold else 8,
            color=color,
            weight="bold" if bold else "normal",
        )
    ax.axhline(target, color="seagreen", ls="--", lw=1.5)
    ax.text(
        -0.55,
        target * 1.12,
        "target %d ps" % target,
        color="seagreen",
        ha="left",
        fontsize=9,
    )

    for x, y, b in zip(xs, design, bounded):
        ax.annotate(
            ("\u2265 %s ps" if b else "%s ps") % f"{y:,}",
            (x, y),
            textcoords="offset points",
            xytext=(0, 11),
            ha="center",
            fontsize=8.5,
            weight="bold",
            color="firebrick",
        )

    ax.set_xticks(xs)
    ax.set_xticklabels([r["date"] for r in runs], fontsize=9)
    # what changed, as a caption: an annotation per point overlaps its
    # neighbours as soon as the runs are close together, and they are.
    ax.set_xlabel(
        "\n".join("%s  %s" % (r["date"], r["note"]) for r in runs),
        fontsize=7.5,
        color="0.35",
        loc="left",
        labelpad=10,
    )
    ax.set_ylabel("minimum clock period (ps, log)")
    ax.set_title(
        "XiangShan on asap7: the design's minimum clock period (red) and its parts",
        loc="left",
        fontsize=12,
        weight="bold",
    )
    ax.grid(axis="y", alpha=0.3, which="both")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    out = os.path.join(HERE, "kpi.png")
    fig.savefig(out, dpi=120, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
