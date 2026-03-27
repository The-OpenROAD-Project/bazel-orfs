"""Update a project's README.md results table from metrics JSON.

Usage:
    update_readme.py <project_readme> <metrics_json> [--reported-freq "2.7 GHz"]
"""
import argparse
import json
import re
import sys
from pathlib import Path


def format_freq(ghz: float) -> str:
    return f"{ghz:.2f} GHz"


def update_results_table(readme_text: str, metrics: dict, reported_freq: str) -> str:
    """Replace TBD values in the Reported vs. Actual Results table."""
    replacements = {
        "Frequency": format_freq(metrics["frequency_ghz"]) if "frequency_ghz" in metrics else "TBD",
        "Cells": f'{metrics["cells"]:,}' if "cells" in metrics else "TBD",
        "Area": str(round(metrics["area_um2"])) if "area_um2" in metrics else "TBD",
        "WNS": str(round(metrics["wns_ps"])) if "wns_ps" in metrics else "TBD",
        "Power": str(metrics["power_mw"]) if "power_mw" in metrics else "TBD",
    }

    lines = readme_text.split("\n")
    result = []
    in_table = False
    for line in lines:
        if "| Metric" in line and "Reported" in line:
            in_table = True
            result.append(line)
            continue
        if in_table and line.startswith("|"):
            for key, value in replacements.items():
                if key.lower() in line.lower().split("|")[1].strip().lower():
                    parts = line.split("|")
                    if len(parts) >= 4:
                        parts[-2] = f" {value} "
                    line = "|".join(parts)
                    break
            result.append(line)
            if not line.strip().startswith("|"):
                in_table = False
        else:
            in_table = False
            result.append(line)

    return "\n".join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_readme", help="Path to project README.md")
    parser.add_argument("metrics_json", help="Path to metrics JSON file")
    parser.add_argument("--reported-freq", default=None, help="Reported frequency string")
    args = parser.parse_args()

    readme_path = Path(args.project_readme)
    readme_text = readme_path.read_text()
    metrics = json.loads(Path(args.metrics_json).read_text())

    updated = update_results_table(readme_text, metrics, args.reported_freq)
    readme_path.write_text(updated)
    print(f"Updated {readme_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
