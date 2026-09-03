#!/usr/bin/env python3
"""Figures for ideas/eta.md.

Three questions, three pictures: what the grinds look like, why the
obvious curve fit fails on them, and whether any of it beats guessing.
"""

import argparse
import os
import collections
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import backtest  # noqa: E402
import forecast  # noqa: E402

CONV = "#1f77b4"
GAVE = "#d62728"


def _stamped(s):
    """Only stamped runs can be drawn against wall time."""
    return s.points and s.points[0].t is not None and s.points[-1].t is not None


def fig_grinds(series, path):
    """repair_timing: violating endpoints against wall time."""
    runs = [
        s
        for s in series
        if s.kind == "repair_setup" and len(s.points) >= 20 and _stamped(s)
    ]
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    runs = sorted(runs, key=lambda s: -(s.points[-1].t - s.points[0].t))
    for s in runs:
        t0 = s.points[0].t
        xs = [p.t - t0 for p in s.points if p.t is not None]
        ys = [max(p.metric, 1e-2) for p in s.points if p.t is not None]
        if not xs:
            continue
        colour = CONV if s.converged else GAVE
        ax.plot(
            xs, ys, color=colour, lw=1.7,
            ls="-" if s.converged else "--", alpha=0.85,
            label="{} {} ({:.0f}s, {})".format(
                s.design.split("/")[0],
                s.stage.replace("_", " "),
                xs[-1],
                "closed" if s.converged else "gave up",
            ),
        )
    ax.set_xlabel("seconds into the stage")
    ax.set_ylabel("endpoint TNS remaining (log scale)")
    ax.set_yscale("log")
    ax.set_title(
        "repair_timing: solid closed timing, dashed gave up\n"
        "the flat tails are the futility -- time bought nothing"
    )
    ax.set_xlim(left=0)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7.5, ncol=2, loc="lower left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    print("wrote", path)


def fig_gpl(series, path):
    """Global place overflow: the plateau that breaks a whole-history fit."""
    runs = [
        s
        for s in series
        if s.kind == "gpl" and len(s.points) >= 20 and _stamped(s)
    ]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for s in runs:
        t0 = s.points[0].t
        xs = [p.t - t0 for p in s.points if p.t is not None]
        ys = [p.metric for p in s.points if p.t is not None]
        if not xs:
            continue
        ax.plot(xs, ys, lw=1.5, alpha=0.85,
                label="{} {}".format(s.design.split("/")[0], s.stage))
    ax.axhline(0.1, color="#555", lw=1.0, ls=":")
    ax.annotate("target overflow 0.1", xy=(0.02, 0.12), xycoords=("axes fraction", "data"),
                fontsize=8, color="#555")
    ax.set_xlabel("seconds into global placement")
    ax.set_ylabel("overflow")
    ax.set_title("Global place decays late: a fit over the whole history reads the plateau")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7.5, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    print("wrote", path)


def fig_scores(series, path):
    """Does any of it beat guessing? Two panels, each against its base rate."""
    checkpoints = backtest.CHECKPOINTS_S
    hist = {}
    for s in series:
        if backtest.usable(s):
            hist.setdefault(backtest.key_of(s), []).append(s)
    rows = backtest.evaluate(series, hist)
    fut = backtest.futility(series)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4))

    xs = [c for c in checkpoints if ("naive", c) in rows and rows[("naive", c)]["dec"]]
    dec = [sum(rows[("naive", c)]["dec"]) / len(rows[("naive", c)]["dec"]) for c in xs]
    base = []
    for c in xs:
        b = rows[("naive", c)]["base"]
        share = sum(b) / len(b)
        base.append(max(share, 1 - share))
    idx = range(len(xs))
    ax1.bar([i - 0.19 for i in idx], dec, width=0.38, label="forecast", color=CONV)
    ax1.bar([i + 0.19 for i in idx], base, width=0.38, label="always say 'it fits'",
            color="#bbbbbb")
    ax1.set_xticks(list(idx))
    ax1.set_xticklabels(["{:.0f}s".format(c) for c in xs])
    ax1.set_ylim(0, 1.05)
    ax1.set_ylabel("budget decision accuracy")
    ax1.set_title("ETA: the forecast adds nothing")
    ax1.legend(fontsize=8, loc="lower right")
    ax1.grid(alpha=0.25, axis="y")

    xs2 = [c for c in checkpoints if ("naive", c) in fut]
    prec, prev = [], []
    for c in xs2:
        tp, fp, tn, fn_ = fut[("naive", c)]
        tot = tp + fp + tn + fn_
        prec.append(tp / (tp + fp) if (tp + fp) else 0)
        prev.append((tp + fn_) / tot if tot else 0)
    idx2 = range(len(xs2))
    ax2.bar([i - 0.19 for i in idx2], prec, width=0.38, label="rule precision", color=GAVE)
    ax2.bar([i + 0.19 for i in idx2], prev, width=0.38, label="always say 'futile'",
            color="#bbbbbb")
    ax2.set_xticks(list(idx2))
    ax2.set_xticklabels(["{:.0f}s".format(c) for c in xs2])
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel("precision of the futility call")
    ax2.set_title("Futility: the rule does beat guessing, early")
    ax2.legend(fontsize=8, loc="lower right")
    ax2.grid(alpha=0.25, axis="y")

    fig.tight_layout()
    fig.savefig(path, dpi=140)
    print("wrote", path)


def fig_waste(series, path):
    """How much of each grind bought the last 1% of its own progress."""
    rows = []
    for s in series:
        if not backtest.usable(s):
            continue
        pts = [p for p in s.points if p.t is not None and p.metric is not None]
        if len(pts) < 5:
            continue
        t0 = pts[0].t
        total = pts[-1].t - t0
        gain = pts[0].metric - pts[-1].metric
        if total <= 1 or gain <= 0:
            continue
        thresh = pts[0].metric - 0.99 * gain
        t99 = total
        for p in pts:
            if p.metric <= thresh:
                t99 = p.t - t0
                break
        rows.append((total - t99, t99, s))
    rows.sort(key=lambda r: -(r[0] / (r[0] + r[1])))
    rows = rows[:10]

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    labels = [
        "{} {}".format(r[2].design.split("/")[0], r[2].stage.replace("_", " "))
        for r in rows
    ]
    ys = range(len(rows))
    ax.barh(list(ys), [r[1] for r in rows], color="#4c9f70",
            label="reached 99% of its progress")
    ax.barh(list(ys), [r[0] for r in rows], left=[r[1] for r in rows],
            color=GAVE, label="spent on the last 1%")
    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("seconds")
    ax.set_title("Where the grind time goes (worst ten of 44 stamped grinds)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.25, axis="x")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    print("wrote", path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus")
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args(argv)
    series = backtest.load(args.corpus)
    fig_grinds(series, args.outdir + "/eta-grinds.png")
    fig_gpl(series, args.outdir + "/eta-gpl-shape.png")
    fig_scores(series, args.outdir + "/eta-scores.png")
    fig_waste(series, args.outdir + "/eta-waste.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
