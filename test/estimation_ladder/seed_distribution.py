#!/usr/bin/env python3
"""The distribution the selector draws from.

One dot per rtl_macro_placer -random_seed candidate, sorted by the
fast-GPL proxy score: the spread is the whole reason measured selection
exists.  The proxy's winner and the default draw (seed 0 -- what the
flow ships when nobody selects) are called out by name.  Reads a
macro_select evidence directory (<tag>.json per candidate).
"""

import argparse
import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE = "#2a78d6"
ORANGE = "#eb6834"
INK = "#1a1f26"
INK_SECONDARY = "#5a6472"
GRID = "#e8eaed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy-dir", required=True)
    parser.add_argument("--kpi", default="wq25")
    parser.add_argument("--design", default="swerv_wrapper (asap7)")
    parser.add_argument("--out", default="seed_distribution_swerv.png")
    args = parser.parse_args()

    candidates = {}
    for path in sorted(glob.glob(os.path.join(args.proxy_dir, "cand_*.json"))):
        with open(path) as f:
            leaf = json.load(f)
        candidates[leaf["seed"]] = leaf[args.kpi]
    if len(candidates) < 2:
        raise SystemExit(f"seed_distribution: {len(candidates)} candidates found")

    ordered = sorted(candidates.items(), key=lambda kv: kv[1])
    winner_seed = ordered[0][0]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.grid(True, axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(INK_SECONDARY)
    ax.tick_params(colors=INK_SECONDARY, labelsize=8)

    xs = list(range(len(ordered)))
    ys = [v for _, v in ordered]
    colors = [ORANGE if seed == winner_seed else BLUE for seed, _ in ordered]
    ax.scatter(xs, ys, s=52, c=colors, edgecolors="white", linewidths=0.8, zorder=3)

    for x, (seed, value) in zip(xs, ordered):
        if seed == winner_seed:
            ax.annotate(
                f"seed {seed} (winner)",
                (x, value),
                textcoords="offset points",
                xytext=(8, -2),
                fontsize=8.5,
                color=INK,
            )
        elif seed == 0:
            ax.annotate(
                "seed 0 (the default draw)",
                (x, value),
                textcoords="offset points",
                xytext=(-8, 4),
                ha="right",
                fontsize=8.5,
                color=INK,
            )

    spread = (ordered[-1][1] - ordered[0][1]) / ordered[-1][1] * 100.0
    ax.set_title(
        f"{args.design}: {len(ordered)} seed candidates span "
        f"{spread:.0f}% on the scoring proxy",
        fontsize=11,
        color=INK,
    )
    ax.set_xlabel(
        "candidates in proxy-score order (monotone by construction: "
        "this shows spread, not ranking quality)",
        fontsize=9,
        color=INK,
    )
    ax.set_ylabel("fast-GPL proxy score, sampled-path mean (ps)", fontsize=9, color=INK)
    ax.set_xticks([])

    fig.tight_layout()
    fig.savefig(args.out, dpi=160)
    print(f"seed_distribution: wrote {args.out}")


if __name__ == "__main__":
    main()
