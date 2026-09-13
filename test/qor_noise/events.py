#!/usr/bin/env python3

"""Record the commits that re-target a design, so they can be cut out.

Not every step in a design's QoR history is a draw from the same urn. If
a commit changes the design's clock period, its utilisation, its floorplan
or its constraints, the design that follows is a different optimisation
problem than the one before, and the step across that boundary carries no
information about tool noise. ORFS commit subjects say so out loud --
"nangate45/bp_fe util 50 and clk_period 1.62".

This records, per design, every first-parent commit touching anything in
the design directory other than the rules and metadata files themselves:
config.mk, the SDC, floorplan scripts, the RTL. Those are the segment
boundaries. What is left between boundaries is a stretch over which the
problem was held fixed and only the tools moved.
"""

import argparse
import csv
import re
import subprocess
import sys

DESIGN_GLOB = "flow/designs/*/*/**"

PATH_RE = re.compile(r"^flow/designs/([^/]+)/([^/]+)/(.+)$")

# Files that record the outcome rather than the problem. A change to one
# of these is the observation, not a re-targeting.
OUTCOME_FILES = {
    "rules-base.json",
    "metadata-base-ok.json",
    "metadata-base-full.json",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    out = subprocess.run(
        [
            "git",
            "-C",
            args.repo,
            "log",
            "--first-parent",
            "--format=commit %H %at",
            "--name-only",
            "--no-renames",
            args.ref,
            "--",
            "flow/designs",
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        errors="replace",
    ).stdout

    commit = when = None
    seen = set()
    n = 0
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["platform", "design", "commit", "unix_time", "what"])
        for line in out.splitlines():
            if line.startswith("commit "):
                _, commit, when = line.split()
                continue
            m = PATH_RE.match(line.strip())
            if not m:
                continue
            platform, design, rest = m.groups()
            leaf = rest.rsplit("/", 1)[-1]
            if leaf in OUTCOME_FILES:
                continue
            key = (platform, design, commit)
            if key in seen:
                continue
            seen.add(key)
            w.writerow([platform, design, commit, when, rest])
            n += 1

    print(f"retargeting events={n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
