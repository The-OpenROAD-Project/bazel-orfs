"""Plot DRC violation locations on die layout.

Reads CSV output from drc_locations.tcl and plots each violation
as a colored dot on a die map. Color = violation type.

Usage:
    python3 scripts/plot_drc_map.py <drc_csv> [output.png] [--die WxH]

The CSV format (from drc_locations.tcl):
    type,xlo_um,ylo_um,xhi_um,yhi_um,layer
"""
import sys
import re

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
except ImportError:
    print("matplotlib required", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <drc_csv> [output.png]")
        sys.exit(1)

    csv_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "drc_map.png"

    # Parse CSV
    violations = []
    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            parts = line.split(",")
            if len(parts) >= 5:
                vtype = parts[0]
                xlo, ylo, xhi, yhi = [float(x) for x in parts[1:5]]
                layer = parts[5] if len(parts) > 5 else "unknown"
                cx = (xlo + xhi) / 2
                cy = (ylo + yhi) / 2
                violations.append((vtype, cx, cy, layer))

    if not violations:
        print("No violations found")
        sys.exit(0)

    # Group by type
    types = {}
    for vtype, cx, cy, layer in violations:
        types.setdefault(vtype, []).append((cx, cy, layer))

    # Color map for violation types
    colors = [
        "#ef4444", "#f97316", "#eab308", "#22c55e",
        "#3b82f6", "#8b5cf6", "#ec4899", "#06b6d4",
    ]

    fig, ax = plt.subplots(figsize=(10, 10))

    # Plot each type
    for i, (vtype, points) in enumerate(sorted(types.items())):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        color = colors[i % len(colors)]
        short_name = vtype[:30] + "..." if len(vtype) > 30 else vtype
        ax.scatter(xs, ys, c=color, s=15, alpha=0.6,
                   label=f"{short_name} ({len(points)})")

    ax.set_xlabel("X (µm)", fontsize=12)
    ax.set_ylabel("Y (µm)", fontsize=12)
    ax.set_title(
        f"DRC Violations — {len(violations)} total, {len(types)} types",
        fontsize=14, fontweight="bold",
    )
    ax.set_aspect("equal")
    ax.legend(fontsize=8, loc="upper right", ncol=1)
    ax.grid(alpha=0.2)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"Wrote {out_path} ({len(violations)} violations, {len(types)} types)")


if __name__ == "__main__":
    main()
