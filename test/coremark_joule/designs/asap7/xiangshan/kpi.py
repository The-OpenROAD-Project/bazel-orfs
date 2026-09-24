#!/usr/bin/env python3
"""Draw the KPI: XSCore's minimum clock period over time, against the target.

    python3 test/coremark_joule/designs/asap7/xiangshan/kpi.py

Reads kpi.json beside it and writes kpi.png. Add a row to the json when a
change moves the number, re-run this, commit both.

Two series. The top level number is the parent with its clock tree, which
is the KPI. Each block's number is that block alone at its own place
stage, against an ideal clock: what the parent would approach if the
clock reached the logic, and the only per block period that exists while
the blocks are abstracted at place.

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
    "MemBlock": ("#2171b5", 0),
    "Frontend": ("#6baed6", 0),
    "VecRegionModule": ("#238b45", 7),
    "Region_1": ("#807dba", -11),
}


def main():
    with open(os.path.join(HERE, "kpi.json")) as f:
        d = json.load(f)
    runs = d["runs"]
    target = d["target_ps"]
    xs = list(range(len(runs)))
    ys = [r["min_period_ps"] for r in runs]

    fig, ax = plt.subplots(figsize=(10, 5.2))

    # the blocks, each against an ideal clock at its own place stage: what
    # the parent's number would approach if the clock reached the logic.
    for name, (color, dy) in BLOCK_COLORS.items():
        pts = [
            (x, r["blocks"][name])
            for x, r in zip(xs, runs)
            if name in r.get("blocks", {})
        ]
        if not pts:
            continue
        bx = [p[0] for p in pts]
        by = [p[1] for p in pts]
        ax.plot(bx, by, "s--", color=color, lw=1.4, ms=5, zorder=2)
        ax.annotate(
            "%s  %s ps" % (name, f"{by[-1]:,}"),
            (bx[-1], by[-1]),
            textcoords="offset points",
            xytext=(9, dy - 3),
            fontsize=8,
            color=color,
        )

    ax.plot(xs, ys, "o-", color="firebrick", lw=2.2, ms=7, zorder=3)
    ax.annotate(
        "XSCore, top level",
        (xs[-1], ys[-1]),
        textcoords="offset points",
        xytext=(9, -3),
        fontsize=8.5,
        color="firebrick",
        weight="bold",
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

    for x, r in zip(xs, runs):
        ax.annotate(
            "%s ps" % f"{r['min_period_ps']:,}",
            (x, r["min_period_ps"]),
            textcoords="offset points",
            xytext=(0, 11),
            ha="center",
            fontsize=8.5,
            weight="bold",
            color="firebrick",
        )

    ax.set_yscale("log")
    lo = min([target] + [v for r in runs for v in r.get("blocks", {}).values()])
    ax.set_ylim(min(target, lo) * 0.45, max(ys) * 2.2)
    ax.set_xlim(-0.55, len(runs) - 1 + 0.95)
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
        "XSCore on asap7: minimum clock period, top level and per block",
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
