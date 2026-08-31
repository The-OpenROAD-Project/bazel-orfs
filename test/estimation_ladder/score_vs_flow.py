#!/usr/bin/env python3
"""The money figure: does a score predict what the flow delivers?

Two rows of scatter panels over the SAME candidates on the SAME design
(asap7 swerv_wrapper, the campaign's recognizable ORFS design), one
column per flow KPI measured at grt:

  row 1  x = RTL-MP's own objective at the candidate (raw penalty
         components recombined under one fixed normalization)
  row 2  x = the fast non-timing-driven global-placement proxy score

Only the x changes between rows, so "the objective cannot see what the
post-fog proxy sees" is visible as the same cloud of points organizing
itself -- or failing to.  Each panel is annotated with Spearman's rho
(rank correlation: candidate selection is a ranking problem) and a
bootstrap 95% CI; with ~24 candidates a point estimate alone would
overclaim.  Timing panels shade the +/- delta_tie band from the
design's own stage_variance walk: differences inside the band are
ties, and a score should not be rewarded for predicting noise.

Inputs (all produced by the campaign):
  --evaluate-dir   macro_score evaluate-mode leaves (<tag>.json): the
                   ground truth per candidate at grt
  --proxy-dir      macro_select evidence dir (<tag>.json): the proxy
                   score per candidate
  --objective-json {tag: score} from the generate-mode debug tables,
                   recombined by macro_score.py's fixed normalization
  --delta-tie-json stage_variance_<design>.json (optional until the
                   walk completes; panels then omit the tie band)
  --out            output PNG
"""

import argparse
import glob
import json
import math
import os
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Reference palette (dataviz skill): candidates in blue, the proxy's
# winner in orange, ink/greys for text and the tie band.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
INK = "#1a1f26"
INK_SECONDARY = "#5a6472"
BAND = "#d7dbe0"
GRID = "#e8eaed"

KPI_COLUMNS = [
    ("achieved", "achieved period (ps)", True),
    ("wq25", "general paths mean (ps)", True),
    ("macro_mean", "macro paths mean (ps)", True),
    ("stdcell_um2", "stdcell area (um2)", False),
]


def kpis_from_evaluate_leaf(leaf):
    """The KPI menu from a macro_score evaluate leaf."""
    paths = leaf["paths"]
    gen = [p["min_period"] for p in paths if not p["macro_path"]]
    mac = [p["min_period"] for p in paths if p["macro_path"]]
    return {
        "achieved": leaf["clock_period"] - leaf["wns"],
        "wq25": sum(gen) / len(gen) if gen else float("nan"),
        "macro_mean": sum(mac) / len(mac) if mac else float("nan"),
        "stdcell_um2": leaf["area"]["stdcell_um2"],
    }


def rankdata(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = mean_rank
        i = j + 1
    return ranks


def spearman(x, y):
    rx, ry = rankdata(x), rankdata(y)
    n = len(rx)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def spearman_ci(x, y, n_boot=4000, seed=0):
    rng = random.Random(seed)
    n = len(x)
    rhos = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        rho = spearman([x[i] for i in idx], [y[i] for i in idx])
        if not math.isnan(rho):
            rhos.append(rho)
    rhos.sort()
    lo = rhos[int(0.025 * len(rhos))]
    hi = rhos[int(0.975 * len(rhos)) - 1]
    return lo, hi


def load_tag_jsons(directory):
    out = {}
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        tag = os.path.splitext(os.path.basename(path))[0]
        if tag in ("winner",):
            continue
        with open(path) as f:
            out[tag] = json.load(f)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate-dir", required=True)
    parser.add_argument("--proxy-dir", required=True)
    parser.add_argument("--objective-json", required=True)
    parser.add_argument("--delta-tie-json")
    parser.add_argument("--design", default="swerv_wrapper (asap7)")
    parser.add_argument("--out", default="score_vs_flow.png")
    args = parser.parse_args()

    evaluate = load_tag_jsons(args.evaluate_dir)
    proxy = load_tag_jsons(args.proxy_dir)
    with open(args.objective_json) as f:
        objective = json.load(f)

    delta_tie = {}
    if args.delta_tie_json and os.path.exists(args.delta_tie_json):
        with open(args.delta_tie_json) as f:
            delta_tie = json.load(f).get("delta_tie", {})

    tags = sorted(set(evaluate) & set(proxy) & set(objective))
    if len(tags) < 3:
        raise SystemExit(
            f"score_vs_flow: only {len(tags)} candidates present in all three "
            "inputs; need the evaluate walk, the proxy scores and the "
            "objective scores over the same population"
        )

    flow = {t: kpis_from_evaluate_leaf(evaluate[t]) for t in tags}
    rows = [
        ("RTL-MP objective (fixed normalization)", {t: objective[t] for t in tags}),
        ("fast-GPL proxy score (ps)", {t: proxy[t]["wq25"] for t in tags}),
    ]
    # The proxy's own pick, and the default draw, called out by name.
    winner = min(tags, key=lambda t: proxy[t]["wq25"])
    default = "cand_s0" if "cand_s0" in tags else None

    fig, axes = plt.subplots(
        2, len(KPI_COLUMNS), figsize=(3.4 * len(KPI_COLUMNS), 6.4), sharex="row"
    )
    fig.suptitle(
        f"Does the score predict the flow at grt? {args.design}, "
        f"{len(tags)} seed candidates",
        color=INK,
        fontsize=13,
    )

    for row, (xlabel, scores) in enumerate(rows):
        xs_all = [scores[t] for t in tags]
        for col, (kpi, kpi_label, is_timing) in enumerate(KPI_COLUMNS):
            ax = axes[row][col]
            ys_all = [flow[t][kpi] for t in tags]

            ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
            ax.set_axisbelow(True)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
            for spine in ("left", "bottom"):
                ax.spines[spine].set_color(INK_SECONDARY)
            ax.tick_params(colors=INK_SECONDARY, labelsize=8)

            if is_timing and delta_tie.get("achieved"):
                mid = sum(ys_all) / len(ys_all)
                tie = delta_tie["achieved"]
                ax.axhspan(
                    mid - tie, mid + tie, color=BAND, alpha=0.5, zorder=0, lw=0
                )

            ax.scatter(
                xs_all,
                ys_all,
                s=42,
                color=BLUE,
                edgecolors="white",
                linewidths=0.8,
                zorder=3,
            )
            for special, label in ((winner, "winner"), (default, "seed 0")):
                if special is None:
                    continue
                x, y = scores[special], flow[special][kpi]
                ax.scatter(
                    [x],
                    [y],
                    s=58,
                    color=ORANGE if special == winner else BLUE,
                    edgecolors=INK,
                    linewidths=1.0,
                    zorder=4,
                )
                ax.annotate(
                    label,
                    (x, y),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize=7.5,
                    color=INK_SECONDARY,
                )

            rho = spearman(xs_all, ys_all)
            lo, hi = spearman_ci(xs_all, ys_all)
            ax.text(
                0.03,
                0.97,
                f"ρ = {rho:+.2f}  [{lo:+.2f}, {hi:+.2f}]",
                transform=ax.transAxes,
                va="top",
                fontsize=9,
                color=INK,
            )

            if row == 0:
                ax.set_title(kpi_label, fontsize=10, color=INK)
            if row == len(rows) - 1:
                ax.set_xlabel(xlabel, fontsize=9, color=INK)
            if col == 0:
                ax.set_ylabel(
                    "flow at grt" if row == 0 else "flow at grt",
                    fontsize=9,
                    color=INK,
                )

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(args.out, dpi=160)
    print(f"score_vs_flow: wrote {args.out} ({len(tags)} candidates)")
    for row_label, scores in rows:
        line = [row_label]
        for kpi, _, _ in KPI_COLUMNS:
            xs = [scores[t] for t in tags]
            ys = [flow[t][kpi] for t in tags]
            line.append(f"{kpi}: {spearman(xs, ys):+.2f}")
        print("  " + "  ".join(line))


if __name__ == "__main__":
    main()
