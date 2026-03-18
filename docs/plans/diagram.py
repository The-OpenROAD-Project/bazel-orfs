#!/usr/bin/env python3
"""Generate SVG flow diagrams from YAML definitions.

Usage:
  python diagram.py diagram.yaml              # writes diagram.svg
  python diagram.py diagram.yaml -o out.svg   # custom output path
"""

import argparse
import sys

import yaml


def load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def render_svg(spec):
    nodes = spec["nodes"]
    edges = spec.get("edges", [])
    title = spec.get("title", "")
    cfg = spec.get("layout", {})

    node_w = cfg.get("node_width", 220)
    node_h = cfg.get("node_height", 44)
    gap_y = cfg.get("gap_y", 36)
    margin = cfg.get("margin", 40)
    font_size = cfg.get("font_size", 13)

    # Index nodes by id
    by_id = {}
    for n in nodes:
        by_id[n["id"]] = n

    # Assign positions: nodes are placed in columns/rows
    # Simple layout: each node gets (col, row) from YAML
    for n in nodes:
        col = n.get("col", 0)
        row = n.get("row", 0)
        n["_cx"] = margin + col * (node_w + gap_y) + node_w / 2
        n["_cy"] = margin + 30 + row * (node_h + gap_y) + node_h / 2
        n["_x"] = n["_cx"] - node_w / 2
        n["_y"] = n["_cy"] - node_h / 2

    # Compute canvas size
    max_x = max(n["_x"] + node_w for n in nodes) + margin
    max_y = max(n["_y"] + node_h for n in nodes) + margin
    width = max_x
    height = max_y

    lines = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {width} {height}"'
        f' font-family="system-ui, sans-serif"'
        f' font-size="{font_size}">'
    )
    lines.append(f'<rect width="{width}" height="{height}" fill="white"/>')

    # Arrow marker
    lines.append(
        '<defs>'
        '<marker id="arr" viewBox="0 0 10 10"'
        ' refX="10" refY="5" markerWidth="8" markerHeight="8"'
        ' orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#555"/>'
        '</marker>'
        '</defs>'
    )

    # Title
    if title:
        lines.append(
            f'<text x="{width / 2}" y="24"'
            f' text-anchor="middle" font-size="15"'
            f' font-weight="bold">{title}</text>'
        )

    # Edges (drawn before nodes so they appear behind)
    for e in edges:
        src = by_id[e["from"]]
        dst = by_id[e["to"]]
        color = e.get("color", "#555")
        dashed = e.get("dashed", False)
        label = e.get("label", "")

        sx, sy = src["_cx"], src["_cy"]
        dx, dy = dst["_cx"], dst["_cy"]

        # Attach to nearest edge of source/dest boxes
        sx, sy = _edge_attach(src, dst, node_w, node_h)
        dx, dy = _edge_attach(dst, src, node_w, node_h)

        dash_attr = ' stroke-dasharray="6,4"' if dashed else ""
        lines.append(
            f'<line x1="{sx}" y1="{sy}" x2="{dx}" y2="{dy}"'
            f' stroke="{color}" stroke-width="1.5"'
            f'{dash_attr}'
            f' marker-end="url(#arr)"/>'
        )
        if label:
            mx = (sx + dx) / 2
            my = (sy + dy) / 2
            lines.append(
                f'<text x="{mx + 6}" y="{my - 4}"'
                f' font-size="10" fill="{color}"'
                f' font-style="italic">{label}</text>'
            )

    # Nodes
    for n in nodes:
        x, y = n["_x"], n["_y"]
        fill = n.get("fill", "#f5f5f5")
        stroke = n.get("stroke", "#333")
        sw = n.get("stroke_width", 1.5)
        rx = n.get("rx", 6)
        text = n.get("label", n["id"])
        sub = n.get("sublabel", "")

        lines.append(
            f'<rect x="{x}" y="{y}"'
            f' width="{node_w}" height="{node_h}"'
            f' rx="{rx}" fill="{fill}"'
            f' stroke="{stroke}" stroke-width="{sw}"/>'
        )

        if sub:
            lines.append(
                f'<text x="{n["_cx"]}" y="{n["_cy"] - 4}"'
                f' text-anchor="middle"'
                f' font-weight="bold">{text}</text>'
            )
            lines.append(
                f'<text x="{n["_cx"]}" y="{n["_cy"] + 12}"'
                f' text-anchor="middle"'
                f' font-size="10" fill="#666">{sub}</text>'
            )
        else:
            lines.append(
                f'<text x="{n["_cx"]}" y="{n["_cy"] + 5}"'
                f' text-anchor="middle"'
                f' font-weight="bold">{text}</text>'
            )

    lines.append("</svg>")
    return "\n".join(lines)


def _edge_attach(src, dst, w, h):
    """Return point on src box edge closest to dst center."""
    sx, sy = src["_cx"], src["_cy"]
    dx, dy = dst["_cx"], dst["_cy"]

    # Determine primary direction
    adx = abs(dx - sx)
    ady = abs(dy - sy)

    if ady > adx:
        # Vertical edge
        if dy > sy:
            return sx, sy + h / 2  # bottom
        else:
            return sx, sy - h / 2  # top
    else:
        # Horizontal edge
        if dx > sx:
            return sx + w / 2, sy  # right
        else:
            return sx - w / 2, sy  # left


def main():
    parser = argparse.ArgumentParser(
        description="Generate SVG diagram from YAML"
    )
    parser.add_argument("input", help="YAML input file")
    parser.add_argument("-o", "--output", help="Output SVG path")
    args = parser.parse_args()

    spec = load(args.input)
    out_path = args.output
    if not out_path:
        out_path = args.input.rsplit(".", 1)[0] + ".svg"

    svg = render_svg(spec)
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
