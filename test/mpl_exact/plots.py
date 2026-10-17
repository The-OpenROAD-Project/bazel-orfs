"""Figures for the mpl exact-check study, from whatever results exist.

Metrics:
  time to answer (TTA)  mpl's wall time until it places or refuses
  verdict               an arm against base: faster at <= 0.9x, slower at
                        >= 1.1x, otherwise the same (single-digit percent
                        differences are not claimed)
  tail factor           per design, the worst TTA over the core sweep over
                        the TTA at the nominal core: 1.0 means a hard or
                        unplaceable point costs no more than an easy one

usage: plots.py --bench results.csv [--sweep results.csv] --out DIR
"""

import argparse
import collections
import csv
import math
import os
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter  # noqa: E402

PLAIN = FuncFormatter(lambda v, _: f"{v:g}")

# Reference palette, light mode (validated: four slots, adjacent pairs).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BAND = "#f0efec"
ARMS = [
    ("base", "#2a78d6"),
    ("fallback", "#eb6834"),
    ("first", "#1baf7a"),
    ("tiered", "#eda100"),
]
LABEL = {
    "base": "base (master)",
    "fallback": "exact check after annealing fails",
    "first": "exact check before every run",
    "tiered": "exact before tilings, bounds before placements",
}
# Outcome as a second channel, so identity never rests on colour alone.
MARKER = {"placed": "o", "proof": "^", "noproof": "X", "timeout": "s"}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK2,
        "axes.titlecolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.facecolor": SURFACE,
        "figure.facecolor": SURFACE,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def nominal_runtime(bench_csv, out):
    runs = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in csv.DictReader(open(bench_csv)):
        if r["seconds"]:
            runs[r["design"]][r["arm"]].append(float(r["seconds"]))
    rows = []
    for design, arms in runs.items():
        if arms.get("base") and arms.get("new"):
            rows.append(
                (
                    statistics.mean(arms["new"]) / statistics.mean(arms["base"]),
                    design,
                    statistics.mean(arms["base"]),
                )
            )
    if not rows:
        return None
    rows.sort()
    fig, ax = plt.subplots(figsize=(7.5, 0.32 * len(rows) + 1.6))
    ax.axvspan(0.9, 1.1, color=BAND, zorder=0, lw=0)
    ax.text(
        1.0, -0.9, "within 10%: same", ha="center", va="center", color=MUTED, fontsize=8
    )
    ys = range(len(rows))
    ax.scatter(
        [r[0] for r in rows],
        ys,
        s=48,
        color=ARMS[0][1],
        zorder=3,
        edgecolor=SURFACE,
        linewidth=2,
    )
    ax.set_yticks(list(ys))
    ax.set_yticklabels(
        [f"{r[1]}  ({r[2]:.1f} s)" for r in rows], fontsize=8, color=INK2
    )
    ax.axvline(1.0, color=AXIS, linewidth=1, zorder=1)
    ax.set_xlim(min(0.6, min(r[0] for r in rows) - 0.05), 1.25)
    ax.set_ylim(-1.4, len(rows) - 0.5)
    ax.set_xlabel("mpl time, with the change / master (pinned, idle, 3 runs)")
    faster = sum(r[0] <= 0.9 for r in rows)
    slower = sum(r[0] >= 1.1 for r in rows)
    saved = max(r[2] * (1 - r[0]) for r in rows)
    fig.suptitle(
        f"mpl on placeable ORFS designs: {faster} of {len(rows)} "
        f"faster by 10% or more, {slower} slower; the largest "
        f"saving is {saved:.1f} s",
        x=0.02,
        ha="left",
        fontsize=10.5,
        color=INK,
    )
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    path = os.path.join(out, "nominal_runtime.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def outcome(row):
    if row["placed"] == "1":
        return "placed"
    if row["error"] == "timeout":
        return "timeout"
    return "proof" if row.get("proof") == "1" else "noproof"


def sweep_runtime(sweep_csv, out):
    data = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in csv.DictReader(open(sweep_csv)):
        if r["seconds"]:
            data[r["design"]][r["arm"]][float(r["scale"])] = (
                float(r["seconds"]),
                outcome(r),
            )
    designs = sorted(data)
    if not designs:
        return []
    cols = 4
    rows = math.ceil(len(designs) / cols)
    fig, axes = plt.subplots(
        rows, cols, figsize=(3.2 * cols, 2.5 * rows), squeeze=False
    )
    for ax, design in zip(axes.flat, designs):
        for arm, color in ARMS:
            points = sorted(data[design].get(arm, {}).items(), reverse=True)
            if not points:
                continue
            xs = [p[0] for p in points]
            ys = [p[1][0] for p in points]
            ax.plot(xs, ys, color=color, linewidth=2, zorder=2)
            for x, (y, kind) in points:
                ax.scatter(
                    [x],
                    [y],
                    marker=MARKER[kind],
                    s=42,
                    color=color,
                    edgecolor=SURFACE,
                    linewidth=1.5,
                    zorder=3,
                )
        ax.set_title(design, fontsize=9, loc="left")
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(PLAIN)
        ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        ax.invert_xaxis()
        ax.tick_params(labelsize=7)
    for ax in list(axes.flat)[len(designs) :]:
        ax.set_visible(False)
    handles = [
        plt.Line2D([], [], color=c, linewidth=2, label=LABEL[a]) for a, c in ARMS
    ]
    handles += [
        plt.Line2D([], [], color=MUTED, marker=m, linestyle="", label=k)
        for k, m in (
            ("placed", "o"),
            ("refused with proof", "^"),
            ("refused, no proof", "X"),
            ("timeout", "s"),
        )
    ]
    fig.legend(handles=handles, loc="upper center", ncol=4, fontsize=8, frameon=False)
    fig.supxlabel(
        "core side, relative to the design's own (smaller to the " "right)",
        color=INK2,
        fontsize=9,
    )
    fig.supylabel("mpl time to answer, s (log)", color=INK2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    path = os.path.join(out, "sweep_time_to_answer.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)

    # Tail factor: worst over the sweep / nominal, per design and arm.
    factors = collections.defaultdict(list)
    for design in designs:
        for arm, _ in ARMS:
            points = data[design].get(arm, {})
            if 1.0 in points and len(points) > 1:
                factors[arm].append(max(t for t, _ in points.values()) / points[1.0][0])
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    ax.axvspan(0.9, 1.1, color=BAND, zorder=0, lw=0)
    for y, (arm, color) in enumerate(ARMS):
        values = factors.get(arm)
        if not values:
            continue
        ax.scatter(
            values,
            [y] * len(values),
            s=40,
            color=color,
            edgecolor=SURFACE,
            linewidth=2,
            zorder=3,
        )
        median = statistics.median(values)
        ax.plot([median, median], [y - 0.3, y + 0.3], color=INK, linewidth=2, zorder=4)
        ax.text(
            1.02,
            y,
            f"median {median:.2f}x, worst {max(values):.1f}x",
            va="center",
            fontsize=8,
            color=INK2,
            transform=ax.get_yaxis_transform(),
        )
    ax.set_yticks(range(len(ARMS)))
    ax.set_yticklabels([LABEL[a] for a, _ in ARMS], fontsize=8, color=INK2)
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([0.5, 1, 2, 5, 10, 20, 50, 100]))
    ax.xaxis.set_major_formatter(PLAIN)
    ax.xaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
    ax.set_xlabel(
        "tail factor: worst time to answer over the core sweep / "
        "time at the nominal core"
    )
    fig.suptitle(
        "Predictability: what a tight or unplaceable core costs over "
        "the design's own core",
        x=0.02,
        ha="left",
        fontsize=10.5,
        color=INK,
    )
    ax.grid(axis="y", visible=False)
    fig.tight_layout(rect=(0, 0, 0.82, 1))
    path2 = os.path.join(out, "tail_factor.png")
    fig.savefig(path2, dpi=150)
    plt.close(fig)
    return [path, path2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench")
    parser.add_argument("--sweep")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    made = []
    if args.bench and os.path.exists(args.bench):
        made.append(nominal_runtime(args.bench, args.out))
    if args.sweep and os.path.exists(args.sweep):
        made += sweep_runtime(args.sweep, args.out)
    for path in made:
        if path:
            print(path)
    if not any(made):
        print("Not yet measured: no results to plot.")


if __name__ == "__main__":
    main()
