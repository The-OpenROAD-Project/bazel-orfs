"""Draw the sweep: per design, every seed's reg2reg period as a dot per arm,
in percent of the first arm's mean (the first arm's spread shaded as the
noise band), and the one-flop-loop floor with the buffers on its loop.

    python3 tools/headroom/sweep/plot.py tmp/sweep/results.txt out.png
"""

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from report import mean, parse  # noqa: E402


def main():
    runs, _ = parse(sys.argv[1])
    designs = [d for d in runs if len(next(iter(runs[d].values()))) >= 1]
    fig, axes = plt.subplots(
        2, len(designs), figsize=(3.2 * len(designs), 6.4), squeeze=False
    )
    for col, d in enumerate(designs):
        arms = runs[d]
        order = list(arms)
        first = arms[order[0]]
        bp = mean([r["period"] for r in first])
        lo = 100 * (min(r["period"] for r in first) / bp - 1)
        hi = 100 * (max(r["period"] for r in first) / bp - 1)
        ax = axes[0][col]
        ax.axhspan(lo, hi, color="0.85", label="noise band")
        for x, arm in enumerate(order):
            ys = [100 * (r["period"] / bp - 1) for r in arms[arm]]
            ax.scatter([x] * len(ys), ys, s=30, zorder=3)
        ax.set_xticks(range(len(order)), order, rotation=30, fontsize=8)
        ax.set_title(d, fontsize=9)
        ax.axhline(0, color="0.5", lw=0.6)
        if col == 0:
            ax.set_ylabel("reg2reg period vs %s (%%)" % order[0])
        ax2 = axes[1][col]
        for x, arm in enumerate(order):
            fl = [r["floor"] for r in arms[arm]]
            lb = [r["loopbufs"] for r in arms[arm]]
            ax2.scatter([x] * len(fl), fl, s=30, zorder=3)
            for f, b in zip(fl, lb):
                ax2.annotate(
                    "%d" % b,
                    (x, f),
                    textcoords="offset points",
                    xytext=(6, -3),
                    fontsize=7,
                )
        ax2.set_xticks(range(len(order)), order, rotation=30, fontsize=8)
        if col == 0:
            ax2.set_ylabel("one-flop-loop floor\n(label: buffers on the loop)")
    fig.tight_layout()
    fig.savefig(sys.argv[2], dpi=110)


if __name__ == "__main__":
    main()
