#!/usr/bin/env python3
"""Collapse a walk's leaf JSON files into one CSV.

Deliberately path-free output. The leaves are written into scratch
directories whose absolute paths name a local user and machine, and this
repository is public: a collector that copied source paths into a column
would publish them the moment the CSV was committed. Only measured
values cross into the CSV.
"""

import argparse
import csv
import json
import pathlib
import sys

# Written by the walk; anything else in a leaf is ignored rather than
# silently widening the published surface.
FIELDS = [
    "design",
    "arm",
    "period_scale",
    "clock_period",
    "time_unit",
    "sequence",
    "setup_margin",
    "wns",
    "tns",
    "hold_wns",
    "inst_count",
    "buffer_count",
    "design_area",
    "elapsed_s",
]


def read_leaves(roots):
    rows = []
    for root in roots:
        for path in sorted(pathlib.Path(root).rglob("*.json")):
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                # A crashed leaf can leave a truncated file. Report it and
                # keep going: losing one leaf must not lose the walk.
                print(f"skipping unreadable leaf {path.name}: {exc}", file=sys.stderr)
                continue
            missing = [f for f in FIELDS if f not in data]
            if missing:
                print(
                    f"skipping incomplete leaf {path.name}: missing {missing}",
                    file=sys.stderr,
                )
                continue
            rows.append({f: data[f] for f in FIELDS})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", help="Directories of leaf JSON files")
    parser.add_argument("-o", "--out", required=True, help="CSV to write")
    args = parser.parse_args()

    rows = read_leaves(args.roots)
    if not rows:
        sys.exit("no leaves found")

    rows.sort(key=lambda r: (r["design"], r["period_scale"], r["sequence"], r["arm"]))
    with open(args.out, "w", newline="") as fd:
        writer = csv.DictWriter(fd, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} leaves to {args.out}")


if __name__ == "__main__":
    main()
