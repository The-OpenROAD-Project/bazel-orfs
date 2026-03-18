#!/usr/bin/env python3
"""Generate a quadrant chart as SVG from YAML input.

Usage:
  python quadrant.py quadrant.yaml              # writes quadrant.svg
  python quadrant.py quadrant.yaml -o out.svg   # custom output path
"""

import argparse
import sys

import yaml


def load_chart(path):
    with open(path) as f:
        return yaml.safe_load(f)


def render_svg(spec, width=600, height=450):
    margin = {"top": 60, "right": 40, "bottom": 60, "left": 80}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    x_axis = spec["x"]
    y_axis = spec["y"]
    points = spec["points"]
    title = spec.get("title", "")

    lines = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {width} {height}"'
        f' font-family="system-ui, sans-serif"'
        f' font-size="13">'
    )

    # Background
    lines.append(
        f'<rect width="{width}" height="{height}"'
        f' fill="white"/>'
    )

    # Quadrant shading
    cx = margin["left"] + plot_w / 2
    cy = margin["top"] + plot_h / 2
    # Top-left = sweet spot (green tint)
    lines.append(
        f'<rect x="{margin["left"]}" y="{margin["top"]}"'
        f' width="{plot_w / 2}" height="{plot_h / 2}"'
        f' fill="#e8f5e9" opacity="0.5"/>'
    )
    # Top-right
    lines.append(
        f'<rect x="{cx}" y="{margin["top"]}"'
        f' width="{plot_w / 2}" height="{plot_h / 2}"'
        f' fill="#fff3e0" opacity="0.5"/>'
    )
    # Bottom-left
    lines.append(
        f'<rect x="{margin["left"]}" y="{cy}"'
        f' width="{plot_w / 2}" height="{plot_h / 2}"'
        f' fill="#fce4ec" opacity="0.5"/>'
    )
    # Bottom-right
    lines.append(
        f'<rect x="{cx}" y="{cy}"'
        f' width="{plot_w / 2}" height="{plot_h / 2}"'
        f' fill="#ffebee" opacity="0.5"/>'
    )

    # Axes
    ox = margin["left"]
    oy = margin["top"] + plot_h
    lines.append(
        f'<line x1="{ox}" y1="{oy}" x2="{ox + plot_w}"'
        f' y2="{oy}" stroke="#333" stroke-width="1.5"'
        f' marker-end="url(#arrow)"/>'
    )
    lines.append(
        f'<line x1="{ox}" y1="{oy}" x2="{ox}"'
        f' y2="{margin["top"]}" stroke="#333"'
        f' stroke-width="1.5"'
        f' marker-end="url(#arrow)"/>'
    )

    # Arrow marker
    lines.append(
        '<defs><marker id="arrow" viewBox="0 0 10 10"'
        ' refX="10" refY="5" markerWidth="8"'
        ' markerHeight="8" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#333"/>'
        "</marker></defs>"
    )

    # Axis labels
    lines.append(
        f'<text x="{ox + plot_w / 2}" y="{oy + 45}"'
        f' text-anchor="middle" font-size="14"'
        f' font-weight="bold">{x_axis["label"]}</text>'
    )
    lines.append(
        f'<text x="{ox - 15}" y="{margin["top"] + plot_h / 2}"'
        f' text-anchor="middle" font-size="14"'
        f' font-weight="bold"'
        f' transform="rotate(-90,{ox - 15},'
        f'{margin["top"] + plot_h / 2})">'
        f"{y_axis['label']}</text>"
    )

    # Axis low/high
    lines.append(
        f'<text x="{ox}" y="{oy + 25}"'
        f' text-anchor="middle" font-size="11"'
        f' fill="#666">{x_axis["low"]}</text>'
    )
    lines.append(
        f'<text x="{ox + plot_w}" y="{oy + 25}"'
        f' text-anchor="middle" font-size="11"'
        f' fill="#666">{x_axis["high"]}</text>'
    )
    lines.append(
        f'<text x="{ox - 8}" y="{oy + 4}"'
        f' text-anchor="end" font-size="11"'
        f' fill="#666">{y_axis["low"]}</text>'
    )
    lines.append(
        f'<text x="{ox - 8}" y="{margin["top"] + 4}"'
        f' text-anchor="end" font-size="11"'
        f' fill="#666">{y_axis["high"]}</text>'
    )

    # Title
    if title:
        lines.append(
            f'<text x="{width / 2}" y="28"'
            f' text-anchor="middle" font-size="16"'
            f' font-weight="bold">{title}</text>'
        )

    # Points
    default_color = "#546e7a"
    recommended_color = "#2e7d32"
    for pt in points:
        px = ox + pt["x"] * plot_w
        py = oy - pt["y"] * plot_h
        recommended = "recommended" in pt.get("note", "").lower()
        color = recommended_color if recommended else default_color
        r = 10 if recommended else 6

        # Highlight ring for recommended
        if recommended:
            lines.append(
                f'<circle cx="{px}" cy="{py}" r="{r + 6}"'
                f' fill="none" stroke="{color}"'
                f' stroke-width="2" stroke-dasharray="4,3"'
                f' opacity="0.5"/>'
            )

        # Dot
        lines.append(
            f'<circle cx="{px}" cy="{py}" r="{r}"'
            f' fill="{color}" stroke="white"'
            f' stroke-width="2"/>'
        )

        # Label
        label = pt["label"]
        note = pt.get("note", "")

        # Place label to the right, unless too close to right edge
        anchor = "start"
        lx = px + r + 8
        if px > ox + plot_w * 0.7:
            anchor = "end"
            lx = px - r - 8

        font_size = "14" if recommended else "13"
        lines.append(
            f'<text x="{lx}" y="{py - 2}"'
            f' text-anchor="{anchor}"'
            f' font-weight="bold" font-size="{font_size}"'
            f' fill="{color}">{label}</text>'
        )
        note_size = "12" if recommended else "11"
        note_color = "#333" if recommended else "#555"
        lines.append(
            f'<text x="{lx}" y="{py + 14}"'
            f' text-anchor="{anchor}"'
            f' font-size="{note_size}"'
            f' fill="{note_color}">{note}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate SVG quadrant chart from YAML"
    )
    parser.add_argument("input", help="YAML input file")
    parser.add_argument(
        "-o",
        "--output",
        help="Output SVG path (default: input stem + .svg)",
    )
    args = parser.parse_args()

    spec = load_chart(args.input)

    out_path = args.output
    if not out_path:
        out_path = args.input.rsplit(".", 1)[0] + ".svg"

    svg = render_svg(spec)
    with open(out_path, "w") as f:
        f.write(svg)

    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
