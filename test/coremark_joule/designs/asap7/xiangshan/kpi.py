#!/usr/bin/env python3
"""Draw the KPI: XSCore's minimum clock period over time, against the target.

    python3 test/coremark_joule/designs/asap7/xiangshan/kpi.py

Reads kpi.json beside it and writes kpi.png. Add a row to the json when a
change moves the number, re-run this, commit both.

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


def main():
    with open(os.path.join(HERE, "kpi.json")) as f:
        d = json.load(f)
    runs = d["runs"]
    target = d["target_ps"]
    xs = list(range(len(runs)))
    ys = [r["min_period_ps"] for r in runs]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(xs, ys, "o-", color="firebrick", lw=2, ms=7, zorder=3)
    ax.axhline(target, color="seagreen", ls="--", lw=1.5)
    ax.text(
        len(runs) - 0.5,
        target * 1.15,
        "target %d ps" % target,
        color="seagreen",
        ha="right",
        fontsize=9,
    )

    for x, r in zip(xs, runs):
        ax.annotate(
            "%d ps" % r["min_period_ps"],
            (x, r["min_period_ps"]),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
            fontsize=8,
        )

    ax.set_yscale("log")
    ax.set_ylim(target * 0.5, max(ys) * 2.5)
    ax.set_xlim(-0.6, len(runs) - 0.4)
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
        "XSCore on asap7: minimum clock period", loc="left", fontsize=12, weight="bold"
    )
    ax.grid(axis="y", alpha=0.3, which="both")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    out = os.path.join(HERE, "kpi.png")
    fig.savefig(out, dpi=120, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
