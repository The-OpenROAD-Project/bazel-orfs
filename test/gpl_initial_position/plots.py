"""Figures, generated from the same samples the tables are.

Three, each carrying a claim the text also makes in numbers, so a reader
who trusts neither can check one against the other:

1. **The ensembles.** Every arm's samples on one axis per design,
   normalised to the baseline's mean, with the baseline's own spread
   drawn as a band. An arm inside the band did not resolve, and the
   picture says so before the table does.

2. **The initial-place trajectory.** HPWL against outer iteration, one
   line per arm. This is where "the start washes out" is either visible
   or not.

3. **Resolution against seeds.** What the campaign can distinguish at
   each `k`, from the measured spread, with the `k` actually run marked.
   It is the sizing argument as a picture, and it is what makes an
   upper bound quotable when nothing resolves.
"""

import argparse
import collections
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (backend must be set first)

import campaign  # noqa: E402
import report  # noqa: E402
import stats  # noqa: E402


def ensembles(samples, key, label, out_path):
    """Every arm's samples per design, normalised to the baseline.

    Args:
        samples: from report.load().
        key: the endpoint field.
        label: axis label.
        out_path: where to write the PNG.

    Returns:
        The path, or None when there is nothing to draw.
    """
    grouped = report.by_design_arm(samples, key)
    designs = sorted(
        design
        for design, arms in grouped.items()
        if len(arms.get(campaign.BASELINE_ARM, [])) >= 2
    )
    if not designs:
        return None

    arms = sorted({arm for design in designs for arm in grouped[design]})
    fig, axes = plt.subplots(
        len(designs), 1, figsize=(9, 2.4 * len(designs)), squeeze=False, sharex=True
    )
    for row, design in enumerate(designs):
        axis = axes[row][0]
        baseline = grouped[design][campaign.BASELINE_ARM]
        base_mean = stats.mean(baseline)
        base_sd = stats.stdev(baseline)
        axis.axhspan(
            -200 * base_sd / base_mean,
            200 * base_sd / base_mean,
            color="0.85",
            zorder=0,
            label="baseline 2σ" if row == 0 else None,
        )
        axis.axhline(0.0, color="0.4", linewidth=0.8, zorder=1)
        for column, arm in enumerate(arms):
            values = grouped[design].get(arm, [])
            if not values:
                continue
            offsets = [
                100.0 * (value - base_mean) / base_mean for value in values
            ]
            axis.scatter(
                [column] * len(offsets), offsets, s=14, alpha=0.75, zorder=3
            )
        axis.set_ylabel("%s\n%% vs baseline" % design, fontsize=8)
        axis.tick_params(labelsize=8)
    axes[-1][0].set_xticks(range(len(arms)))
    axes[-1][0].set_xticklabels(arms, rotation=30, ha="right", fontsize=8)
    fig.suptitle("%s: each arm against the baseline ensemble" % label, fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def trajectories(samples, out_path):
    """Initial-place HPWL against outer iteration, one line per arm.

    Args:
        samples: from report.load().
        out_path: where to write the PNG.

    Returns:
        The path, or None when no sample carried a trajectory.
    """
    lines = collections.defaultdict(dict)
    for record in samples:
        conv = record.get("initial_place")
        if not conv:
            continue
        design = "%s/%s" % (record["platform"], record["design"])
        # One representative seed per (design, arm): the trajectory is a
        # shape, not an ensemble, and overplotting every seed hides it.
        lines[design].setdefault(record["arm"], record)
    designs = sorted(d for d in lines if len(lines[d]) > 1)
    if not designs:
        return None

    fig, axes = plt.subplots(
        len(designs), 1, figsize=(8, 2.6 * len(designs)), squeeze=False
    )
    for row, design in enumerate(designs):
        axis = axes[row][0]
        for arm in sorted(lines[design]):
            conv = lines[design][arm]["initial_place"]
            axis.plot(
                [1, conv["last_iteration"]],
                [conv["hpwl_first"], conv["hpwl_last"]],
                marker="o",
                markersize=3,
                linewidth=1.2,
                label=arm,
            )
        axis.set_ylabel("%s\nHPWL" % design, fontsize=8)
        axis.tick_params(labelsize=8)
        if row == 0:
            axis.legend(fontsize=7, ncol=3)
    axes[-1][0].set_xlabel("initial-place outer iteration", fontsize=9)
    fig.suptitle("Does the starting point wash out?", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def resolution_curve(samples, key, label, out_path):
    """What the campaign can distinguish, as a function of seeds per arm.

    Args:
        samples: from report.load().
        key: the endpoint field.
        label: axis label.
        out_path: where to write the PNG.

    Returns:
        The path, or None when no baseline ensemble exists.
    """
    grouped = report.by_design_arm(samples, key)
    rows = []
    for design in sorted(grouped):
        baseline = grouped[design].get(campaign.BASELINE_ARM, [])
        if len(baseline) < 2:
            continue
        mean = stats.mean(baseline)
        if not mean:
            continue
        rows.append((design, 2 * stats.stdev(baseline) / mean * 100.0, len(baseline)))
    if not rows:
        return None

    ks = [2, 4, 8, 16, 32, 64]
    fig, axis = plt.subplots(figsize=(7, 4.2))
    for design, two_sigma_pct, n in rows:
        axis.plot(
            ks,
            [two_sigma_pct * math.sqrt(2.0 / k) for k in ks],
            marker="o",
            markersize=3,
            linewidth=1.2,
            label="%s (2σ %.2f%%, n=%d)" % (design, two_sigma_pct, n),
        )
    axis.set_xscale("log", base=2)
    axis.set_xticks(ks)
    axis.set_xticklabels([str(k) for k in ks])
    axis.set_xlabel("seeds per arm")
    axis.set_ylabel("resolvable difference, % of the mean")
    axis.set_title("%s: resolution against seeds per arm" % label, fontsize=11)
    axis.grid(alpha=0.3)
    axis.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args(argv)

    samples, _ = report.load(args.results)
    os.makedirs(args.outdir, exist_ok=True)

    written = []
    for path in [
        ensembles(
            samples,
            "gp_hpwl_final",
            "global-place HPWL",
            os.path.join(args.outdir, "ensembles_hpwl.png"),
        ),
        ensembles(
            samples,
            "min_period_wns",
            "min_period",
            os.path.join(args.outdir, "ensembles_min_period.png"),
        ),
        trajectories(samples, os.path.join(args.outdir, "trajectories.png")),
        resolution_curve(
            samples,
            "gp_hpwl_final",
            "global-place HPWL",
            os.path.join(args.outdir, "resolution.png"),
        ),
    ]:
        if path:
            written.append(path)

    for path in written:
        print("wrote %s" % path)
    if not written:
        print("nothing to plot yet -- run the campaign first")
    return 0


if __name__ == "__main__":
    sys.exit(main())
