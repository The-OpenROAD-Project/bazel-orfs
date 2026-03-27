"""Generate a scaling comparison chart for Gemmini configurations.

Reads metrics from each gemmini variant's collected JSON files and
produces a multi-panel plot showing how cells, fmax, routing time,
and routing memory scale with mesh dimension.

Usage:
    bazelisk run //scripts:gemmini_scaling
"""
import json
import os
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib required: pip install matplotlib", file=sys.stderr)
    sys.exit(1)


CONFIGS = [
    ("2×2", "gemmini_2x2", 4),
    ("4×4", "gemmini_4x4", 16),
    ("16×16", "gemmini", 256),
]


def load_metrics(workspace, project):
    """Load GRT metrics and route log for a project."""
    grt = workspace / project / "metrics" / "5_1_grt.json"
    route_log = workspace / project / "logs" / "5_2_route.log"

    result = {}
    if grt.exists():
        d = json.loads(grt.read_text())
        result["cells"] = d.get(
            "globalroute__design__instance__count"
        )
        result["area"] = d.get(
            "globalroute__design__instance__area"
        )
        fmax = d.get("globalroute__timing__fmax__clock:clock")
        if fmax:
            result["fmax_mhz"] = fmax / 1e6

    if route_log.exists():
        text = route_log.read_text()
        for line in text.splitlines():
            if "Peak memory:" in line:
                import re
                m = re.search(r"Peak memory: (\d+)KB", line)
                if m:
                    result["route_memory_gb"] = (
                        int(m.group(1)) / 1024 / 1024
                    )
            if "Elapsed time:" in line and "route" in str(route_log):
                m = re.search(
                    r"Elapsed time: (?:(\d+):)?(\d+):(\d+\.\d+)",
                    line,
                )
                if m:
                    h = int(m.group(1) or 0)
                    mins = int(m.group(2))
                    secs = float(m.group(3))
                    result["route_time_min"] = (
                        h * 60 + mins + secs / 60
                    )

    return result


def main():
    workspace_env = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    workspace = Path(workspace_env) if workspace_env else Path.cwd()

    labels = []
    pes = []
    cells = []
    fmax = []
    route_time = []
    route_mem = []

    for label, project, pe_count in CONFIGS:
        m = load_metrics(workspace, project)
        if not m.get("cells"):
            print(f"Skipping {label}: no metrics", file=sys.stderr)
            continue
        labels.append(label)
        pes.append(pe_count)
        cells.append(m["cells"])
        fmax.append(m.get("fmax_mhz", 0))
        route_time.append(m.get("route_time_min", 0))
        route_mem.append(m.get("route_memory_gb", 0))

    if len(labels) < 2:
        print("Need at least 2 configs with metrics", file=sys.stderr)
        sys.exit(1)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    fig.suptitle(
        "Gemmini Scaling: 2×2 → 4×4 → 16×16",
        fontsize=14,
        fontweight="bold",
    )

    color = "#2563eb"

    # Cells vs PEs
    ax = axes[0][0]
    ax.bar(labels, cells, color=color)
    ax.set_ylabel("Cells (post-GRT)")
    ax.set_title("Cell Count")
    for i, v in enumerate(cells):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9)

    # fmax vs PEs
    ax = axes[0][1]
    ax.bar(labels, fmax, color="#059669")
    ax.set_ylabel("fmax (MHz)")
    ax.set_title("Achieved Frequency")
    ax.axhline(y=1000, color="red", linestyle="--", alpha=0.5,
               label="1 GHz target")
    ax.legend(fontsize=8)
    for i, v in enumerate(fmax):
        ax.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=9)

    # Route time vs PEs
    ax = axes[1][0]
    bars = ax.bar(labels, route_time, color="#d97706")
    ax.set_ylabel("Routing Time (min)")
    ax.set_title("Detail Routing Time")
    for i, v in enumerate(route_time):
        if v > 0:
            txt = f"{v:.0f}m" if v < 120 else f"{v/60:.1f}h"
            ax.text(i, v, txt, ha="center", va="bottom", fontsize=9)
        else:
            ax.text(i, 0, "OOM", ha="center", va="bottom",
                    fontsize=9, color="red")

    # Route memory vs PEs
    ax = axes[1][1]
    ax.bar(labels, route_mem, color="#dc2626")
    ax.set_ylabel("Peak Memory (GB)")
    ax.set_title("Detail Routing Memory")
    ax.axhline(y=30, color="red", linestyle="--", alpha=0.5,
               label="30 GB machine limit")
    ax.legend(fontsize=8)
    for i, v in enumerate(route_mem):
        ax.text(i, v, f"{v:.1f}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()

    out = workspace / "gemmini" / "scaling.png"
    plt.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
