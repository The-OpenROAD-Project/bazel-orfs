"""Three figures, one claim each.

Every chart here answers a question the tables also answer, in the form
that makes the size of the answer immediate:

1. `residuals.png` -- how far each design sits from what its size and
   platform predict, with the band a placement seed can move it drawn to
   scale. The claim is the ratio of the two.
2. `ensembles.png` -- the seeds themselves, per design, against the
   no-perturbation reference. The claim is that the spread is real,
   one-sided, and small.
3. `dose.png` -- spread against perturbation radius. The claim is
   whether the spread grows smoothly with the perturbation (chaos) or
   jumps (a cliff).

Conventions, applied deliberately rather than by default: one axis per
figure, no dual scales; a fixed categorical hue order taken from a
CVD-validated palette rather than matplotlib's cycle; thin marks, a
recessive grid, and direct labels instead of a legend wherever there are
few enough rows to label. Figures are written at a size that stays
legible inline in a pull request body.
"""

import argparse
import glob
import json
import math
import os
import statistics
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (after the backend is set)

import report  # noqa: E402
import trendline  # noqa: E402

# CVD-validated categorical order, light surface. Assigned in fixed
# order and never cycled: an eighth platform folds into "other" rather
# than inventing a hue.
SERIES = [
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#4a3aa7",
    "#8a8a86",
]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#dedddb"


def style(axis):
    """Recessive frame: no top/right spine, a light y grid, muted ink."""
    axis.set_facecolor(SURFACE)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)
    axis.tick_params(colors=MUTED, labelsize=9, length=3)
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)


def save(figure, path):
    figure.patch.set_facecolor(SURFACE)
    figure.tight_layout()
    figure.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(figure)
    print("wrote %s" % path)


def plot_residuals(snapshot, seed_sigma, path):
    """Corpus residuals, with the seed band drawn to scale."""
    rows, _ = report.corpus_rows(snapshot)
    fit = trendline.fit(rows)
    observed = sorted(
        (design for design in fit["designs"] if not design["censored"]),
        key=lambda design: design["residual"],
    )
    values = [design["residual"] for design in observed]
    labels = ["%s/%s" % (d["platform"], d["design"]) for d in observed]

    figure, axis = plt.subplots(figsize=(9, max(4.0, 0.19 * len(values))))
    style(axis)
    axis.grid(axis="y", linewidth=0)
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    positions = range(len(values))
    axis.hlines(positions, 0, values, color=GRID, linewidth=1.0)
    axis.plot(values, positions, "o", markersize=4.5, color=SERIES[0], zorder=3)
    if seed_sigma:
        axis.axvspan(
            -seed_sigma, seed_sigma, color=SERIES[1], alpha=0.18, linewidth=0, zorder=1
        )
        axis.text(
            seed_sigma,
            len(values) * 0.02,
            "  +/- one seed sigma (%.3f)" % seed_sigma,
            color=SERIES[1],
            fontsize=9,
            va="bottom",
        )
    axis.axvline(0, color=MUTED, linewidth=1.0)
    axis.set_yticks(list(positions))
    axis.set_yticklabels(labels, fontsize=6.5, color=MUTED)
    axis.set_xlabel(
        "residual: accepted fractional slack minus what size and platform predict"
        " (clock periods)",
        color=MUTED,
        fontsize=9,
    )
    axis.set_title(
        "Designs deviate from the trend by far more than a placement seed moves them",
        color=INK,
        fontsize=11,
        loc="left",
    )
    save(figure, path)


def plot_ensembles(samples, path):
    """Per-design seed spread, against the no-perturbation reference."""
    groups = report.by_design(samples)
    nulls = report.by_design(samples, arm="nullperturb")
    designs = sorted(groups)
    figure, axis = plt.subplots(figsize=(8, 1.6 + 0.55 * len(designs)))
    style(axis)
    axis.grid(axis="y", linewidth=0)
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    for index, design in enumerate(designs):
        values = [sample["min_period_wns"] for sample in groups[design]]
        period = groups[design][0]["clk_period"]
        centre = statistics.mean(values)
        relative = [100.0 * (value - centre) / period for value in values]
        axis.plot(
            relative,
            [index] * len(relative),
            "o",
            markersize=5,
            color=SERIES[index % len(SERIES)],
            alpha=0.75,
            markeredgecolor=SURFACE,
            markeredgewidth=0.8,
        )
        if design in nulls:
            null_value = statistics.mean(
                sample["min_period_wns"] for sample in nulls[design]
            )
            axis.plot(
                [100.0 * (null_value - centre) / period],
                [index],
                marker="|",
                markersize=16,
                color=INK,
                markeredgewidth=1.8,
            )
    axis.set_yticks(range(len(designs)))
    axis.set_yticklabels(
        [
            "%s\n%d seeds, %.0f ps clock"
            % (design, len(groups[design]), groups[design][0]["clk_period"])
            for design in designs
        ],
        fontsize=9,
        color=MUTED,
    )
    axis.set_xlabel(
        "min_period at global route, relative to the design's own mean"
        " (% of clock period)",
        color=MUTED,
        fontsize=9,
    )
    axis.set_ylim(-0.6, len(designs) - 0.4)
    axis.invert_yaxis()
    axis.set_title(
        "Only the placement seed changes\nthe vertical bar is the same"
        " design with the perturbation switched off",
        color=INK,
        fontsize=11,
        loc="left",
    )
    save(figure, path)


def plot_dose(samples, path):
    """Spread against perturbation radius."""
    arms = {}
    for sample in samples:
        if sample.get("min_period_wns") is None:
            continue
        arms.setdefault((sample["design"], sample["arm"]), []).append(
            sample["min_period_wns"]
        )
    points = {}
    for (design, arm), values in arms.items():
        if arm == "nullperturb":
            radius = 0.0
        elif arm.startswith("dist"):
            radius = float(arm[4:])
        elif arm == "base":
            # The default is min(0.5 um, row height); on asap7 that is
            # 500 nm, which is what the arm is plotted at.
            radius = 500.0
        else:
            continue
        if len(values) < 2 and radius != 0.0:
            continue
        points.setdefault(design, []).append(
            (radius, 2 * statistics.pstdev(values) if len(values) > 1 else 0.0, len(values))
        )
    # A design measured at a single radius is a point, not a
    # dose-response; showing it in a line chart's legend would suggest a
    # curve nobody has taken.
    points = {
        design: series
        for design, series in points.items()
        if len({radius for radius, _, _ in series}) >= 2
    }
    if not points:
        sys.exit("no design has been run at two perturbation radii yet")
    figure, axis = plt.subplots(figsize=(7, 4))
    style(axis)
    for index, design in enumerate(sorted(points)):
        series = sorted(points[design])
        axis.plot(
            [radius for radius, _, _ in series],
            [spread for _, spread, _ in series],
            marker="o",
            markersize=6,
            linewidth=2,
            color=SERIES[index % len(SERIES)],
            label=design,
        )
        for radius, spread, count in series:
            axis.annotate(
                "n=%d" % count,
                (radius, spread),
                textcoords="offset points",
                xytext=(6, 5),
                fontsize=8,
                color=MUTED,
            )
    axis.set_xlabel("perturbation radius -perturb_dist (nm)", color=MUTED, fontsize=9)
    axis.set_ylabel("2 sigma of min_period (ps)", color=MUTED, fontsize=9)
    axis.set_title(
        "How much of the spread the perturbation radius buys",
        color=INK,
        fontsize=11,
        loc="left",
    )
    if len(points) > 1:
        axis.legend(frameon=False, fontsize=9, labelcolor=MUTED)
    save(figure, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--corpus-json", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    samples = report.load_samples(args.results_dir)
    with open(args.corpus_json) as handle:
        snapshot = json.load(handle)
    os.makedirs(args.out_dir, exist_ok=True)

    _, spreads = report.section_ensembles(samples)
    pooled = (
        math.sqrt(
            statistics.mean([entry["fraction"] ** 2 for entry in spreads.values()])
        )
        if spreads
        else None
    )
    plot_residuals(snapshot, pooled, os.path.join(args.out_dir, "residuals.png"))
    plot_ensembles(samples, os.path.join(args.out_dir, "ensembles.png"))
    plot_dose(samples, os.path.join(args.out_dir, "dose.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
