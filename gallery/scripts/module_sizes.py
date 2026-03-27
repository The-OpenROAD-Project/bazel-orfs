"""Analyze module sizes from ORFS synthesis output.

Parses synth_stat.txt to list each module's cell count and area,
sorted largest first. Useful for deciding which modules to build
as separate macros in hierarchical synthesis.

Usage:
    module_sizes.py <logs_dir>
    module_sizes.py <synth_stat_txt>
"""
import argparse
import re
import sys
from pathlib import Path


def parse_synth_stat(text: str) -> list[dict]:
    """Parse Yosys synthesis statistics text.

    Format:
        === module_name ===
           <count>  <area> cells
           ...
           Chip area for module '\\module_name': <area>
    """
    modules = []
    current = None

    for line in text.split("\n"):
        # Module header
        m = re.match(r"=== (\S+) ===", line)
        if m:
            current = {"name": m.group(1), "cells": 0, "area": 0.0}
            modules.append(current)
            continue

        if current is None:
            continue

        # Cell count line: "    <count>  <area> cells"
        m = re.match(r"\s+(\d+)\s+([\d.]+)\s+cells", line)
        if m:
            current["cells"] = int(m.group(1))
            current["area"] = float(m.group(2))
            continue

        # Chip area line
        m = re.match(r"\s+Chip area for module", line)
        if m:
            area_m = re.search(r"([\d.]+)$", line)
            if area_m:
                current["area"] = float(area_m.group(1))

    return modules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to logs dir or synth_stat.txt file")
    args = parser.parse_args()

    path = Path(args.path)
    if path.is_dir():
        # Try reports dir first, then look in the path itself
        candidates = [
            path / "synth_stat.txt",
            path.parent.parent / "reports" / path.parent.name / path.name / "synth_stat.txt",
        ]
        # Also search for it
        found = list(path.rglob("synth_stat.txt"))
        candidates.extend(found)

        stat_file = None
        for c in candidates:
            if c.exists():
                stat_file = c
                break

        if stat_file is None:
            # Try the reports sibling directory
            reports_dir = Path(str(path).replace("/logs/", "/reports/"))
            stat_file = reports_dir / "synth_stat.txt"

        if not stat_file.exists():
            print(f"ERROR: Could not find synth_stat.txt in {path}", file=sys.stderr)
            sys.exit(1)
    else:
        stat_file = path

    text = stat_file.read_text()
    modules = parse_synth_stat(text)

    if not modules:
        print("No modules found in synth_stat.txt", file=sys.stderr)
        sys.exit(1)

    # Sort by cells descending
    modules.sort(key=lambda m: m["cells"], reverse=True)

    # Print table
    print(f"{'Module':<40} {'Cells':>8} {'Area (μm²)':>12}")
    print("-" * 62)
    total_cells = 0
    for m in modules:
        print(f"{m['name']:<40} {m['cells']:>8,} {m['area']:>12.1f}")
        total_cells += m["cells"]
    print("-" * 62)
    print(f"{'TOTAL':<40} {total_cells:>8,}")

    if total_cells > 50000:
        print(f"\n⚠ {total_cells:,} cells — hierarchical synthesis recommended", file=sys.stderr)


if __name__ == "__main__":
    main()
