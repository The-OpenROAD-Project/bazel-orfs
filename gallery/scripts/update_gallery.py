"""Update the top-level README.md Projects table for a given project.

Usage:
    update_gallery.py <readme> <project> <metrics_json> [--reported-freq "2.7 GHz"]
        [--description "..."] [--pdk ASAP7] [--orfs-hash abc1234]
        [--project-version abc1234] [--last-updated 2026-03-18]
"""
import argparse
import json
import re
import sys
from pathlib import Path


def format_freq(ghz: float) -> str:
    return f"{ghz:.2f} GHz"


def update_project_row(readme_text: str, project: str, metrics: dict,
                       reported_freq: str, description: str, pdk: str,
                       orfs_hash: str, project_version: str,
                       last_updated: str) -> str:
    """Update or insert a project row in the Projects table."""
    freq = format_freq(metrics["frequency_ghz"]) if "frequency_ghz" in metrics else "TBD"
    cells = f'{metrics["cells"]:,}' if "cells" in metrics else "TBD"
    area = str(round(metrics["area_um2"])) if "area_um2" in metrics else "TBD"
    status = "Done"
    orfs_str = f"`{orfs_hash}`" if orfs_hash else "—"
    proj_str = f"`{project_version}`" if project_version else "—"

    new_row = (
        f"| [{project}]({project}/) | {description} | {pdk} | "
        f"{reported_freq} | {freq} | {cells} | {area} | "
        f"{orfs_str} | {proj_str} | {last_updated} | {status} |"
    )

    lines = readme_text.split("\n")
    result = []
    found = False
    for line in lines:
        if re.match(rf"\|\s*\[{re.escape(project)}\]", line):
            result.append(new_row)
            found = True
        else:
            result.append(line)

    if not found:
        for i, line in enumerate(result):
            if "| Project |" in line:
                j = i + 2
                while j < len(result) and result[j].startswith("|"):
                    j += 1
                result.insert(j, new_row)
                break

    return "\n".join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readme", help="Path to top-level README.md")
    parser.add_argument("project", help="Project name (e.g., vlsiffra)")
    parser.add_argument("metrics_json", help="Path to metrics JSON file")
    parser.add_argument("--reported-freq", default="—", help="Reported frequency")
    parser.add_argument("--description", default="", help="Project description")
    parser.add_argument("--pdk", default="ASAP7", help="PDK name")
    parser.add_argument("--orfs-hash", default="", help="Short ORFS git hash")
    parser.add_argument("--project-version", default="", help="Short project git hash")
    parser.add_argument("--last-updated", default="", help="Date string (YYYY-MM-DD)")
    args = parser.parse_args()

    readme_path = Path(args.readme)
    readme_text = readme_path.read_text()
    metrics = json.loads(Path(args.metrics_json).read_text())

    updated = update_project_row(
        readme_text, args.project, metrics,
        args.reported_freq, args.description, args.pdk, args.orfs_hash,
        args.project_version, args.last_updated,
    )
    readme_path.write_text(updated)
    print(f"Updated {args.project} row in {readme_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
