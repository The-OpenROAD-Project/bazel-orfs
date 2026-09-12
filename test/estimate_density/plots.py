"""Figures for the study, drawn from whatever results/ holds.

Two figures, one claim each:

  estimate_vs_threshold.png -- per design, the uniform density, the
      density the command estimates, and the ladder bracket the
      measurement puts the real threshold in. The claim is the distance
      between the middle bar and the bracket.

  first_overflow.png -- per design, the overflow gpl reports at its first
      iteration when the estimate drives the density, against the 0.1 the
      estimate was asked for. The claim is how far the command's own
      arithmetic lands from the tool's.

    python3 test/estimate_density/plots.py --out docs/studies/estimate-target-density
"""

import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report  # noqa: E402


def estimate_vs_threshold(rows, path):
    rows = [row for row in rows if row["estimated"] is not None]
    if not rows:
        return None
    names = [row["design"] for row in rows]
    positions = range(len(rows))
    figure, axes = plt.subplots(figsize=(9, 4.5))

    axes.bar(
        positions,
        [row["uniform"] or 0 for row in rows],
        width=0.6,
        label="uniform density (the command's floor)",
        color="#c8d8e8",
    )
    axes.plot(
        list(positions),
        [row["estimated"] for row in rows],
        "o",
        color="#b02020",
        label="estimate_target_density -overflow 0.1",
    )
    for index, row in enumerate(rows):
        if row["hit"] is None:
            continue
        low = row["miss"] if row["miss"] is not None else row["uniform"] or 0
        axes.plot([index, index], [low, row["hit"]], color="#207020", linewidth=6,
                  alpha=0.5)
    axes.plot([], [], color="#207020", linewidth=6, alpha=0.5,
              label="measured threshold bracket")

    axes.set_xticks(list(positions))
    axes.set_xticklabels(names, rotation=20, ha="right")
    axes.set_ylabel("target density")
    axes.set_ylim(0, 1.05)
    axes.set_title("What gpl estimates, and what global placement needs")
    axes.legend(loc="lower right", fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def first_overflow(rows, path):
    rows = [row for row in rows if row["est_first_overflow"] is not None]
    if not rows:
        return None
    names = [row["design"] for row in rows]
    positions = range(len(rows))
    figure, axes = plt.subplots(figsize=(9, 4))
    axes.bar(
        positions,
        [row["est_first_overflow"] for row in rows],
        width=0.6,
        color="#b02020",
        label="overflow at gpl's first iteration, estimate driving density",
    )
    axes.axhline(0.1, color="#202020", linestyle="--",
                 label="overflow the estimate was asked for")
    axes.set_xticks(list(positions))
    axes.set_xticklabels(names, rotation=20, ha="right")
    axes.set_ylabel("overflow")
    axes.set_title("The estimate's own claim, checked against gpl")
    axes.legend(loc="upper right", fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def density_vs_wirelength(designs, path):
    """Per design, what the whole density range does to wirelength.

    One line per design, normalised to its own minimum so eight designs
    of very different size share an axis, with the density the command
    estimated marked on each. A line that is flat says the knob does not
    matter much; where the marker sits says whether the estimate would
    have picked a good value if it did.
    """
    figure, axes = plt.subplots(figsize=(9, 5))
    drawn = 0
    for design in sorted(designs):
        ladder = [
            record
            for record in designs[design]
            if report.rung_index(record) is not None
            and report._metric(record, "route__wirelength__estimated")
            and report._density(record) is not None
        ]
        if len(ladder) < 2:
            continue
        ladder.sort(key=report._density)
        densities = [report._density(r) for r in ladder]
        wirelengths = [
            report._metric(r, "route__wirelength__estimated") for r in ladder
        ]
        floor = min(wirelengths)
        line, = axes.plot(
            densities,
            [100.0 * value / floor for value in wirelengths],
            marker="o",
            markersize=3,
            label=design,
        )
        arms = {report.arm(r): r for r in designs[design] if report.arm(r)}
        est = arms.get("est")
        if est is not None and report._density(est) is not None:
            axes.axvline(
                report._density(est),
                color=line.get_color(),
                linestyle=":",
                alpha=0.6,
            )
        drawn += 1
    if not drawn:
        plt.close(figure)
        return None
    axes.set_xlabel("target density")
    axes.set_ylabel("estimated wirelength, % of this design's minimum")
    axes.set_title(
        "The density knob across its whole range (dotted: what the command chose)"
    )
    axes.legend(fontsize=8, ncol=2)
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def estimate_tracks_density(designs, path):
    """The estimate against the density the placement in front of it used.

    Each point is one ladder rung: x is the density ORFS gave that rung's
    `global_placement -skip_io`, y is what the command then estimated. A
    cloud along y = x says the command is reading back the density of the
    placement it was handed rather than deriving one from the design.
    """
    figure, axes = plt.subplots(figsize=(6.5, 6))
    drawn = 0
    for design in sorted(designs):
        points = [
            (report._density(r), report._estimate(r))
            for r in designs[design]
            if report.rung_index(r) is not None
            and report._density(r) is not None
            and report._estimate(r) is not None
        ]
        if not points:
            continue
        points.sort()
        axes.plot(
            [x for x, _ in points],
            [y for _, y in points],
            marker="o",
            markersize=4,
            linestyle="none",
            label=design,
        )
        drawn += 1
    if not drawn:
        plt.close(figure)
        return None
    axes.plot([0.3, 1.0], [0.3, 1.0], color="#404040", linestyle="--",
              label="y = x (reading the density back)")
    axes.set_xlabel("density the incoming placement was made at")
    axes.set_ylabel("estimate_target_density -overflow 0.1")
    axes.set_title("What the estimate follows")
    axes.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=report.RESULTS_DIR)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    designs = report.by_design(report.load(args.results))
    written = [
        estimate_vs_threshold(
            report.table_estimate_vs_actual(designs),
            os.path.join(args.out, "estimate_vs_threshold.png"),
        ),
        first_overflow(
            report.table_arms(designs),
            os.path.join(args.out, "first_overflow.png"),
        ),
        estimate_tracks_density(
            designs,
            os.path.join(args.out, "estimate_tracks_density.png"),
        ),
        density_vs_wirelength(
            designs,
            os.path.join(args.out, "density_vs_wirelength.png"),
        ),
    ]
    for path in written:
        print(path if path else "skipped: not yet measured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
