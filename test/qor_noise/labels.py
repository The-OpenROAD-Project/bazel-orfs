#!/usr/bin/env python3

"""Recover the Old/New/Type tables that ORFS commit messages carry.

`genRuleFile.py` prints a table when it rewrites a rule, and ORFS
contributors paste it into the commit message:

    | Metric                       | Old    | New    | Type     |
    | ------                       | ---    | ---    | ----     |
    | finish__design__instance__area |  167958 | 238519 | Failing  |

The `Type` column is not decoration. It records *why* the threshold
moved, and therefore what kind of observation the new value is:

  * `Tighten`  -- the new padded rule is better than the old one. Fires on
                  any improvement at all, so these are running-record
                  observations, not samples.
  * `Failing`  -- the measurement violated the old threshold. Since the
                  threshold carries 15% of padding on area, only a large
                  regression can trigger this.
  * `Updating` -- rewritten unconditionally. These are the honest
                  samples: the value is what was measured, with no
                  selection applied.

Any estimate of noise that ignores this distinction is measuring the
maintainers' update policy rather than the tools.
"""

import argparse
import csv
import re
import subprocess
import sys

ROW_RE = re.compile(
    r"^\|\s*(?P<metric>[A-Za-z0-9_:*]+)\s*\|"
    r"\s*(?P<old>[-+0-9.eE]+|inf|-inf|N/A)\s*\|"
    r"\s*(?P<new>[-+0-9.eE]+|inf|-inf|N/A)\s*\|"
    r"\s*(?P<type>Tighten|Failing|Updating)\s*\|"
)

HEADER_RE = re.compile(
    r"^(?P<path>\S*designs/(?P<platform>[^/]+)/(?P<design>[^/]+)/rules-base\.json)"
)

SEP = "@@COMMIT@@"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    log = subprocess.run(
        [
            "git",
            "-C",
            args.repo,
            "log",
            # NOT --first-parent: ORFS merges pull requests, so the merge
            # commit carries the content change while the message with the
            # table lives on the side-branch commit that produced it.
            f"--format={SEP}%H %at%n%B",
            args.ref,
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        errors="replace",
    ).stdout

    n = 0
    commits = 0
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "platform",
                "design",
                "commit",
                "unix_time",
                "metric",
                "old",
                "new",
                "type",
            ]
        )
        for chunk in log.split(SEP):
            if not chunk.strip():
                continue
            head, _, body = chunk.partition("\n")
            try:
                commit, when = head.split()
            except ValueError:
                continue
            # A commit message can carry tables for several designs; the
            # design is named on the line introducing each table.
            platform = design = None
            wrote = False
            for line in body.splitlines():
                h = HEADER_RE.search(line)
                if h:
                    platform, design = h.group("platform"), h.group("design")
                # Some subjects name the design as "sky130hs/ibex:" instead
                # of a full path.
                elif re.match(r"^\s*([a-z0-9_-]+)/([A-Za-z0-9_-]+)\s*:", line):
                    m = re.match(r"^\s*([a-z0-9_-]+)/([A-Za-z0-9_-]+)\s*:", line)
                    platform, design = m.group(1), m.group(2)
                m = ROW_RE.match(line.strip())
                if not m or platform is None:
                    continue
                w.writerow(
                    [
                        platform,
                        design,
                        commit,
                        when,
                        m.group("metric"),
                        m.group("old"),
                        m.group("new"),
                        m.group("type"),
                    ]
                )
                n += 1
                wrote = True
            if wrote:
                commits += 1

    print(f"labelled rows={n} from commits={commits}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
