"""Stacked bar chart of Gemmini build times across configurations.

Reads from build_times.yaml and produces a stacked bar chart showing
how build time distributes across ORFS stages for each mesh size.

Usage:
    bazelisk run //scripts:gemmini_build_times
"""
import os
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import yaml
except ImportError:
    print("matplotlib and pyyaml required", file=sys.stderr)
    sys.exit(1)


CONFIGS = ["gemmini_2x2", "gemmini_4x4", "gemmini"]
LABELS = ["2×2\n(4 PEs)", "4×4\n(16 PEs)", "16×16\n(256 PEs)"]

# Group substeps into display stages
STAGE_GROUPS = [
    ("Synthesis", ["1_1_yosys_canonicalize", "1_2_yosys"]),
    ("Floorplan", ["2_1_floorplan", "2_2_floorplan_macro",
                   "2_3_floorplan_tapcell", "2_4_floorplan_pdn"]),
    ("Placement", ["3_1_place_gp_skip_io", "3_2_place_iop",
                   "3_3_place_gp", "3_4_place_resized", "3_5_place_dp"]),
    ("CTS", ["4_1_cts"]),
    ("GRT", ["5_1_grt"]),
    ("Route", ["5_2_route", "5_3_fillcell"]),
]

COLORS = {
    "Synthesis": "#93c5fd",
    "Floorplan": "#60a5fa",
    "Placement": "#3b82f6",
    "CTS": "#a78bfa",
    "GRT": "#f97316",
    "Route": "#ef4444",
}


def main():
    workspace_env = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    workspace = Path(workspace_env) if workspace_env else Path.cwd()

    bt_path = workspace / "build_times.yaml"
    with open(bt_path) as f:
        build_times = yaml.safe_load(f)

    fig, ax = plt.subplots(figsize=(8, 6))
    bar_width = 0.5

    for config_idx, (project, label) in enumerate(
        zip(CONFIGS, LABELS)
    ):
        if project not in build_times:
            continue
        stages = build_times[project].get("stages", {})

        bottom = 0
        for group_name, substeps in STAGE_GROUPS:
            total_s = 0
            for substep in substeps:
                entry = stages.get(substep, {})
                elapsed = entry if isinstance(entry, (int, float)) \
                    else entry.get("elapsed_s", 0)
                if isinstance(elapsed, (int, float)):
                    total_s += elapsed
            total_min = total_s / 60

            ax.bar(
                config_idx, total_min, bar_width,
                bottom=bottom,
                color=COLORS[group_name],
                edgecolor="white", linewidth=0.5,
                label=group_name if config_idx == 0 else "",
            )

            if total_min > 2:
                ax.text(
                    config_idx, bottom + total_min / 2,
                    f"{total_min:.0f}m",
                    ha="center", va="center", fontsize=9,
                    fontweight="bold", color="white",
                )

            bottom += total_min

        # Total on top
        if bottom > 0:
            txt = (f"{bottom:.0f} min" if bottom < 120
                   else f"{bottom / 60:.1f} hrs")
            ax.text(
                config_idx, bottom + 0.5, txt,
                ha="center", va="bottom", fontsize=10,
                fontweight="bold",
            )

    ax.set_xticks(range(len(CONFIGS)))
    ax.set_xticklabels(LABELS, fontsize=11)
    ax.set_ylabel("Build Time (minutes)", fontsize=12)
    ax.set_title(
        "Gemmini Build Time by Stage",
        fontsize=14, fontweight="bold",
    )

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(
        list(reversed(handles)), list(reversed(labels)),
        loc="upper left", fontsize=9,
    )

    ax.yaxis.set_major_locator(ticker.MultipleLocator(10))
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    out = workspace / "gemmini" / "build_times.png"
    plt.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
