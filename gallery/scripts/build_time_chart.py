"""Render a stacked bar chart of build stage times from build_times.yaml.

Reads build_times.yaml and produces a static image showing per-stage
elapsed times for each project, suitable for embedding in README.md.

Usage:
    bazelisk run //scripts:build_time_chart
    bazelisk run //scripts:build_time_chart -- --output docs/build_times.png
"""
import argparse
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import yaml


# Group raw ORFS stages into high-level flow phases
STAGE_GROUPS = [
    ("Synthesis", ["1_1_yosys_canonicalize", "1_2_yosys"]),
    ("Floorplan", ["2_1_floorplan", "2_2_floorplan_macro", "2_3_floorplan_tapcell", "2_4_floorplan_pdn"]),
    ("Placement", ["3_1_place_gp_skip_io", "3_2_place_iop", "3_3_place_gp", "3_4_place_resized", "3_5_place_dp"]),
    ("CTS", ["4_1_cts"]),
    ("Global Route", ["5_1_grt"]),
    ("Detail Route", ["5_2_route"]),
    ("Finish", ["5_3_fillcell", "6_1_merge", "6_report"]),
]

COLORS = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336", "#00BCD4", "#795548"]


def group_stages(stages: dict) -> list:
    """Sum elapsed times within each stage group."""
    grouped = []
    for group_name, stage_keys in STAGE_GROUPS:
        total = sum(
            stages.get(k, {}).get("elapsed_s", 0)
            for k in stage_keys
        )
        grouped.append((group_name, total))
    return grouped


def render_chart(data: dict, output_path: Path):
    """Render a horizontal stacked bar chart."""
    projects = list(data.keys())
    all_groups = [g[0] for g in STAGE_GROUPS]

    # Compute grouped times per project
    project_groups = {}
    for proj, info in data.items():
        stages = info.get("stages", {})
        project_groups[proj] = group_stages(stages)

    fig, ax = plt.subplots(figsize=(10, max(2, len(projects) * 0.8 + 1)))

    y_positions = range(len(projects))
    bar_height = 0.5

    for group_idx, group_name in enumerate(all_groups):
        lefts = []
        widths = []
        for proj in projects:
            groups = project_groups[proj]
            left = sum(g[1] for g in groups[:group_idx])
            width = groups[group_idx][1]
            lefts.append(left)
            widths.append(width)

        bars = ax.barh(
            y_positions, widths, left=lefts, height=bar_height,
            label=group_name, color=COLORS[group_idx % len(COLORS)],
            edgecolor="white", linewidth=0.5,
        )

        # Add time labels for segments > 5% of the project total
        for i, (w, l) in enumerate(zip(widths, lefts)):
            proj_total = sum(g[1] for g in project_groups[projects[i]])
            if proj_total > 0 and w / proj_total > 0.05 and w >= 10:
                mins = w / 60
                label = f"{mins:.0f}m" if mins >= 1 else f"{w}s"
                ax.text(
                    l + w / 2, i, label,
                    ha="center", va="center", fontsize=7,
                    color="white", fontweight="bold",
                )

    # Add total time labels at the end of each bar
    for i, proj in enumerate(projects):
        total = sum(g[1] for g in project_groups[proj])
        mins = total / 60
        label = f" {mins:.0f} min" if mins >= 1 else f" {total}s"
        note = data[proj].get("note", "")
        if note:
            label += " *"
        ax.text(total + 5, i, label, ha="left", va="center", fontsize=9)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(projects, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("Elapsed Time (minutes)", fontsize=10)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/60:.0f}"))
    ax.set_title("Build Times by Stage", fontsize=12, fontweight="bold")
    ax.legend(
        loc="upper right", fontsize=8, ncol=len(all_groups),
        bbox_to_anchor=(1.0, -0.12), frameon=False,
    )

    # Note for incomplete builds
    incomplete = [p for p in projects if data[p].get("note")]
    if incomplete:
        ax.annotate(
            "* incomplete build",
            xy=(0.99, 0.01), xycoords="axes fraction",
            ha="right", va="bottom", fontsize=7, fontstyle="italic", color="gray",
        )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output image path (default: docs/build_times.png)",
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="Input YAML path (default: build_times.yaml)",
    )
    args = parser.parse_args()

    workspace = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."))
    input_path = Path(args.input) if args.input else workspace / "build_times.yaml"
    output_path = Path(args.output) if args.output else workspace / "docs" / "build_times.png"

    if not input_path.exists():
        print(f"Error: {input_path} not found. Run //scripts:build_times first.", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        data = yaml.safe_load(f)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_chart(data, output_path)
    print(f"Wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
