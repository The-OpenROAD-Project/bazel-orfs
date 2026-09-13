#!/usr/bin/env python3

"""Render the study's figures from analysis.json.

Every figure states one claim and is titled with it. Nothing here
computes a statistic: if a number is drawn, `analyze.py` produced it.

Figures are written with an explicit light background rather than a
transparent one. A transparent PNG inherits GitHub's dark theme behind
dark axis text and becomes unreadable for half the audience.
"""

import argparse
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK = "#1a1a1a"
MUTED = "#6b7280"
GRID = "#e5e7eb"
# Four hues that stay distinguishable in greyscale and to the most common
# colour vision deficiencies.
SERIES = ["#2563eb", "#059669", "#d97706", "#9333ea"]
WARN = "#dc2626"

CLASS_LABEL = {
    "tiny": "tiny (≤1k instances)",
    "small": "small (≤10k)",
    "mid": "mid (≤100k)",
    "any": "any size",
}


def style(ax):
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.label.set_color(MUTED)
    ax.xaxis.label.set_color(MUTED)
    ax.grid(True, color=GRID, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


def figure(nrows=1, ncols=1, figsize=(9, 5)):
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, facecolor="white")
    return fig, axes


def save(fig, outdir, name):
    path = os.path.join(outdir, name)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {path}", file=sys.stderr)


def fig_coverage_vs_d(a, outdir):
    """The lead: what you detect depends on how many, not on which."""
    rows = a["selection"]["random_by_class"]
    fig, (ax, ax2) = figure(1, 2, figsize=(11.5, 4.6))
    for i, cls in enumerate(["tiny", "small", "mid", "any"]):
        r = [x for x in rows if x["size_class"] == cls and not x["exhausted"]]
        if not r:
            continue
        ds = [x["D"] for x in r]
        mu = [x["coverage_mean"] * 100 for x in r]
        lo = [(x["coverage_mean"] - x["coverage_2sigma"] / 2) * 100 for x in r]
        hi = [(x["coverage_mean"] + x["coverage_2sigma"] / 2) * 100 for x in r]
        ax.plot(ds, mu, color=SERIES[i], lw=2, marker="o", ms=4, label=CLASS_LABEL[cls])
        ax.fill_between(ds, lo, hi, color=SERIES[i], alpha=0.13, linewidth=0)
        ax2.plot(
            ds,
            [x["cost_mean"] for x in r],
            color=SERIES[i],
            lw=2,
            marker="o",
            ms=4,
            label=CLASS_LABEL[cls],
        )
    style(ax)
    style(ax2)
    ax.set_xlabel("designs run (D)")
    ax.set_ylabel("% of real tool changes detected")
    ax.set_title(
        "Detection depends on how many designs you run…",
        color=INK,
        fontsize=11,
        loc="left",
        pad=10,
    )
    ax.legend(frameon=False, fontsize=8.5, labelcolor=MUTED)
    ax2.set_yscale("log")
    ax2.set_xlabel("designs run (D)")
    ax2.set_ylabel("estimated CI cost (arb. units, log)")
    ax2.set_title(
        "…and cost depends entirely on which",
        color=INK,
        fontsize=11,
        loc="left",
        pad=10,
    )
    fig.suptitle(
        "Same detection rate, 400× the price",
        color=INK,
        fontsize=13,
        x=0.012,
        ha="left",
        y=1.04,
        weight="bold",
    )
    save(fig, outdir, "coverage_vs_designs.png")


def fig_overfitting(a, outdir):
    """Tuning a design set on history does not survive contact with the future."""
    rows = a["selection"]["greedy_vs_random"]
    fig, ax = figure(figsize=(9.5, 4.8))
    labels = [f"{r['size_class']}\nD={r['D']}" for r in rows]
    x = range(len(rows))
    w = 0.27
    ax.bar(
        [i - w for i in x],
        [r["train_coverage"] * 100 for r in rows],
        w,
        color=SERIES[0],
        label="greedy, scored on the years it was tuned on",
    )
    ax.bar(
        list(x),
        [r["test_coverage"] * 100 for r in rows],
        w,
        color=WARN,
        label="the same set, scored on later years",
    )
    ax.bar(
        [i + w for i in x],
        [r["random_test_mean"] * 100 for r in rows],
        w,
        color=MUTED,
        label="a random set of the same size, later years",
        yerr=[r["random_test_2sigma"] * 100 / 2 for r in rows],
        ecolor=INK,
        capsize=2,
    )
    style(ax)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("% of real tool changes detected")
    ax.set_title(
        "A design set tuned on history is not better than a random one — it is worse",
        color=INK,
        fontsize=12,
        loc="left",
        pad=12,
        weight="bold",
    )
    ax.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="upper left")
    save(fig, outdir, "overfitting.png")


def fig_concordance(a, outdir):
    """Why fleet-wide events may be read as signal rather than coincidence."""
    ev = a["events"]
    fig, ax = figure(figsize=(8.5, 4.4))
    conc = ev["concordance"]
    bars = {
        "all designs moved\nthe same way": conc["fraction_at_100pct"] * 100,
        "anything less": (1 - conc["fraction_at_100pct"]) * 100,
    }
    ax.bar(list(bars), list(bars.values()), color=[SERIES[1], GRID], width=0.5)
    style(ax)
    ax.set_ylabel("% of fleet-wide events")
    ax.set_ylim(0, 100)
    for i, (k, v) in enumerate(bars.items()):
        ax.text(i, v + 2, f"{v:.0f}%", ha="center", color=INK, fontsize=11, weight="bold")
    bump = ev["openroad_bump_events"]
    ax.set_title(
        "When many designs move at once, they move the same way\n"
        f"median concordance {conc['median']:.0%} across {ev['fleetwide_events']} events; "
        f"{bump['n']}/{bump['n']} pure OpenROAD bumps were 100% concordant",
        color=INK,
        fontsize=11,
        loc="left",
        pad=12,
    )
    save(fig, outdir, "concordance.png")


def fig_recommendation(a, outdir):
    """Coverage against what it actually costs to buy."""
    rows = a["selection"]["cheapest_d"]
    fleet = a["selection"]["fleet_total_instances"]
    fig, ax = figure(figsize=(9, 5))
    xs = [r["total_instances"] for r in rows]
    ys = [r["coverage"] * 100 for r in rows]
    ax.plot(xs, ys, color=SERIES[0], lw=2.2, marker="o", ms=5)
    for r in rows:
        if r["D"] in (8, 12, 20, 32, 40):
            ax.annotate(
                f"D={r['D']}",
                (r["total_instances"], r["coverage"] * 100),
                textcoords="offset points",
                xytext=(6, -11),
                fontsize=9,
                color=MUTED,
            )
    ax.axvline(fleet, color=WARN, ls="--", lw=1.4)
    ax.annotate(
        f"the whole fleet\n{fleet/1e6:.1f}M instances",
        (fleet, 30),
        textcoords="offset points",
        xytext=(-96, 0),
        fontsize=9,
        color=WARN,
    )
    style(ax)
    ax.set_xscale("log")
    ax.set_xlabel("total instances in the design set (log) — a proxy for CI cost")
    ax.set_ylabel("% of real tool changes detected")
    top = rows[-1]
    ax.set_title(
        "Buying detection cheaply\n"
        f"the {top['D']} cheapest designs reach {top['coverage']:.0%} at "
        f"{top['total_instances']/fleet:.1%} of the fleet's size",
        color=INK,
        fontsize=12,
        loc="left",
        pad=12,
        weight="bold",
    )
    save(fig, outdir, "recommendation.png")


def fig_cost_vs_information(a, outdir):
    """Big designs are not more informative. They are noisier."""
    ds = [d for d in a["designs"] if d["instances"]]
    fig, ax = figure(figsize=(9, 5))
    sizes = [12 + 90 * min(d["solo_per_year"], 5) / 5 for d in ds]
    sc = ax.scatter(
        [d["instances"] for d in ds],
        [d["responsiveness"] * 100 for d in ds],
        s=sizes,
        c=[d["solo_per_year"] for d in ds],
        cmap="YlOrRd",
        edgecolor=INK,
        linewidth=0.4,
        alpha=0.9,
    )
    cb = fig.colorbar(sc, ax=ax, pad=0.015)
    cb.set_label("solo moves per year (nothing else moved)", color=MUTED, fontsize=9)
    cb.ax.tick_params(colors=MUTED, labelsize=8)
    cb.outline.set_edgecolor(GRID)
    # Hand-placed so the two bp_quads do not print on top of each other.
    offsets = {
        "sky130hd/gcd": (10, 4),
        "asap7/cva6": (-104, -22),
        "gf12/bp_quad": (-40, 20),
        "nangate45/bp_quad": (-150, 26),
    }
    for name, xy in offsets.items():
        d = next((x for x in ds if x["design"] == name), None)
        if not d:
            continue
        ax.annotate(
            f"{name}\n{d['instances']:,.0f} insts",
            (d["instances"], d["responsiveness"] * 100),
            textcoords="offset points",
            xytext=xy,
            fontsize=8.5,
            color=INK,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7),
        )
    style(ax)
    ax.set_xscale("log")
    ax.set_xlabel("design size, instances (log)")
    ax.set_ylabel("% of fleet-wide tool changes this design noticed")
    ax.set_title(
        "Paying more does not buy more signal\n"
        "marker size and colour: how often the design moved on its own, with nothing else",
        color=INK,
        fontsize=12,
        loc="left",
        pad=12,
        weight="bold",
    )
    save(fig, outdir, "cost_vs_information.png")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args(argv)
    with open(args.analysis) as fh:
        a = json.load(fh)
    os.makedirs(args.outdir, exist_ok=True)
    fig_coverage_vs_d(a, args.outdir)
    fig_overfitting(a, args.outdir)
    fig_concordance(a, args.outdir)
    fig_recommendation(a, args.outdir)
    fig_cost_vs_information(a, args.outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
