#!/usr/bin/env python3
"""Draw the study's figures from the results directory.

Static PNGs for a pull request body, committed to the study branch and
referenced by pinned-SHA raw URL. Every figure states its claim in the
title and carries the design/stage in the file name so a re-run cannot
silently swap what a URL points at.

    bazelisk run //test/repair_timing_runtime:plots -- [--results DIR] [--out DIR]

Figures, when their data exists:

    census_seconds.png      setup+hold seconds per design and call site
    census_share.png        share of the substep wall inside repair_timing
    trajectory_<d>_<s>.png  WNS against elapsed seconds, with the last
                            improvement marked: the grind's dead share
    arms_<d>_<s>.png        each arm's repeats against the base, with the
                            resolution band
"""

import argparse
import os
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import report  # noqa: E402

# Categorical slots in fixed order (never cycled), one hue per call
# site, so a call site keeps its colour across every figure.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

KIND_ORDER = ["setup_hold", "repair_design", "floorplan_setup", "post_grt_wns"]
KIND_LABEL = dict(report.KINDS)


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def census_seconds(rows, path, floor_s=5.0):
    """Horizontal stacked bars: seconds in each repair call, per design+stage.

    Stages with less than `floor_s` in repair are left off: they close
    before repair has anything to do and would only crowd the axis.
    """
    totals = {}
    for r in rows:
        totals[(r["design"], r["stage"])] = totals.get((r["design"], r["stage"]), 0) + (r["seconds"] or 0)
    keys = sorted([k for k, v in totals.items() if v >= floor_s], key=lambda k: totals[k])
    if not keys:
        return False
    fig, ax = plt.subplots(figsize=(7, max(3, 0.28 * len(keys) + 1)), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    lefts = [0.0] * len(keys)
    for i, kind in enumerate(KIND_ORDER):
        vals = [sum(r["seconds"] or 0 for r in rows
                    if (r["design"], r["stage"]) == key and r["kind"] == kind) for key in keys]
        if not any(vals):
            continue
        ax.barh(range(len(keys)), vals, left=lefts, height=0.7, color=SERIES[i],
                label=KIND_LABEL[kind], linewidth=0.8, edgecolor=SURFACE)
        lefts = [l + v for l, v in zip(lefts, vals)]
    for i, total in enumerate(lefts):
        ax.text(total + 3, i, "{:.0f}".format(total), va="center", fontsize=7, color=INK)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels(["{} {}".format(d, s) for d, s in keys], fontsize=7)
    ax.set_xlabel("seconds in repair (one run, 24 pinned threads)", color=INK, fontsize=9)
    ax.set_title("Where repair's seconds are, per design and stage (>= {:.0f} s)".format(floor_s),
                 color=INK, fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def census_share(records, path, floor_s=5.0):
    """Share of the substep wall inside repair_timing, per design+stage."""
    rows = report.census_rows(records)
    per = {}
    for r in rows:
        key = (r["design"], r["stage"])
        entry = per.setdefault(key, {"wall": r["wall_s"] or 0, "repair": 0.0})
        if r["kind"] != "repair_design" and r["seconds"]:
            entry["repair"] += r["seconds"]
    keys = [k for k in per if per[k]["wall"] and per[k]["repair"] >= floor_s]
    if not keys:
        return False
    keys.sort(key=lambda k: per[k]["repair"] / per[k]["wall"])
    shares = [100.0 * per[k]["repair"] / per[k]["wall"] for k in keys]
    fig, ax = plt.subplots(figsize=(7, max(3, 0.28 * len(keys) + 1)), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.barh(range(len(keys)), shares, height=0.7, color=SERIES[0])
    for i, (s, k) in enumerate(zip(shares, keys)):
        ax.text(s + 1, i, "{:.0f}% of {:.0f} s".format(s, per[k]["wall"]), va="center",
                fontsize=7, color=INK)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels(["{} {}".format(d, s) for d, s in keys], fontsize=7)
    ax.set_xlabel("% of the substep's wall inside repair_timing", color=INK, fontsize=9)
    ax.set_xlim(0, 115)
    ax.set_title("How much of the stage is repair_timing", color=INK, fontsize=10, loc="left")
    style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def trajectory(record, step, call_index, path):
    """WNS over elapsed seconds for one call, last improvement marked."""
    rows = record["substeps"][step]["repair_rows"][call_index]
    summary = record["substeps"][step]["repair"][call_index]
    main = [r for r in rows if r["iter"] != "final" and r["marker"] == "*"]
    if len(main) < 2:
        return False
    stamped = all(r["t_s"] is not None for r in main)
    start = summary.get("start_s") or (main[0]["t_s"] if stamped else 0)
    xs = [(r["t_s"] - start) if stamped else r["iter"] for r in main]
    ys = [r["wns"] for r in main]
    fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.plot(xs, ys, color=SERIES[0], linewidth=2)
    last_iter = summary.get("last_improving_iter")
    t_last = summary.get("t_last_improvement_s")
    if last_iter is not None:
        x_mark = (t_last - start) if (stamped and t_last is not None) else last_iter
        ax.axvline(x_mark, color=SERIES[1], linewidth=1.2, linestyle="--")
        ax.text(x_mark, max(ys), " last gain", color=SERIES[1], fontsize=8, va="top")
    ax.set_xlabel("elapsed seconds in repair_timing" if stamped else "iteration",
                  color=INK, fontsize=9)
    ax.set_ylabel("WNS (ps)", color=INK, fontsize=9)
    dead = report.dead_share(summary)
    ax.set_title(
        "{} {}: {} passes, {} of the grind after the last gain".format(
            record["design"], step, summary.get("iterations"),
            "{:.0f}%".format(100 * dead) if dead is not None else "?"),
        color=INK, fontsize=10, loc="left")
    style(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def arms(records, design, stage, path):
    """Every arm's repeats as dots against the base median and its resolution."""
    samples = report.arm_samples(records, design, stage)
    control = report.control_arm(samples)
    if control is None or len(samples) < 2:
        return False
    base = [s for s, _, _ in samples[control]]
    base_med = statistics.median(base)
    res = report.resolution(report.two_sigma(base), len(base))
    names = sorted(samples, key=lambda a: (a != control, statistics.median(
        [s for s, _, _ in samples[a]])))
    fig, ax = plt.subplots(figsize=(max(5, 0.6 * len(names)), 3.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.axhspan(base_med - res, base_med + res, color=GRID, zorder=0)
    ax.axhline(base_med, color=MUTED, linewidth=0.8)
    for i, name in enumerate(names):
        secs = [s for s, _, _ in samples[name]]
        ax.scatter([i] * len(secs), secs, s=28, color=SERIES[0 if name == control else 1],
                   edgecolor=SURFACE, linewidth=1, zorder=3)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=8, rotation=20, ha="right")
    ax.set_ylabel("setup+hold seconds", color=INK, fontsize=9)
    ax.set_title("{} {}: arms against base (band = resolution)".format(design, stage),
                 color=INK, fontsize=10, loc="left")
    style(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def draw_all(records, out):
    os.makedirs(out, exist_ok=True)
    written = []
    rows = report.census_rows(records)
    if census_seconds(rows, os.path.join(out, "census_seconds.png")):
        written.append("census_seconds.png")
    if census_share(records, os.path.join(out, "census_share.png")):
        written.append("census_share.png")
    seen = set()
    for record in sorted(records, key=lambda r: (r["design"], r["stage"], r["repeat"])):
        if record["arm"] != "base" or (record["design"], record["stage"]) in seen:
            continue
        seen.add((record["design"], record["stage"]))
        for step, got in record["substeps"].items():
            for i, call in enumerate(got.get("repair", [])):
                if call["kind"] not in ("setup_hold", "floorplan_setup"):
                    continue
                name = "trajectory_{}_{}.png".format(record["design"], step)
                if trajectory(record, step, i, os.path.join(out, name)):
                    written.append(name)
    for design, stage in sorted({(r["design"], r["stage"]) for r in records}):
        name = "arms_{}_{}.png".format(design, stage)
        if arms(records, design, stage, os.path.join(out, name)):
            written.append(name)
    return written


def main():
    root = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=os.path.join(root, "tmp", "repair_timing_runtime", "results"))
    parser.add_argument("--out", default=os.path.join(root, "docs", "studies", "repair-timing-runtime"))
    args = parser.parse_args()
    for name in draw_all(report.load_results(args.results), args.out):
        sys.stdout.write("wrote {}\n".format(os.path.join(args.out, name)))


if __name__ == "__main__":
    main()
