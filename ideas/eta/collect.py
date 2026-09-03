#!/usr/bin/env python3
"""Harvest progress series out of built ORFS stage logs.

Walks the log directories bazel wrote, parses every stage log, and
emits one JSON object per series. The point of a collector rather than
reading logs directly: stage logs run to tens of thousands of lines and
live under bazel-out, so the only sane way to look at a corpus of them
is to reduce it first.

    bazelisk run //ideas/eta:collect -- --out ideas/eta/corpus.jsonl <logdir>...

With no directories given it searches the conventional bazel-bin
locations for ORFS designs and for this repo's own flows.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parse  # noqa: E402

# logs/<platform>/<design>/<variant>/<stage>.log
DEFAULT_ROOTS = [
    "bazel-bin/external/+orfs_repositories+orfs/flow/designs",
    "bazel-bin",
]


def find_logs(roots):
    """Every ORFS stage log under the given roots, deduplicated by path."""
    seen = {}
    for root in roots:
        p = Path(root)
        if not p.exists():
            continue
        for log in p.rglob("logs/*/*/*/*.log"):
            # bazel stages a second copy of every log under .runfiles;
            # the same run counted twice would fake up warm history.
            if ".runfiles" in log.parts or any(
                part.endswith(".runfiles") for part in log.parts
            ):
                continue
            # A stage that is still running writes <stage>.tmp.log and
            # renames on exit; a partial log is not corpus material.
            if log.name.endswith(".tmp.log"):
                continue
            seen[str(log.resolve())] = log
    return sorted(seen.values(), key=str)


def short_path(log):
    """A log identity with no machine in it.

    The corpus is committed as evidence, so it must not carry absolute
    paths, output-base hashes or the OS user name. Everything from the
    design directory down is enough to tell two runs apart, which is all
    any consumer needs it for.
    """
    parts = log.parts
    for i, part in enumerate(parts):
        if part == "designs" and i + 1 < len(parts):
            return "/".join(parts[i + 1:])
    return "/".join(parts[-6:])


def design_of(log):
    """(design, variant, stage) from .../logs/<pdk>/<design>/<variant>/<stage>.log"""
    parts = log.parts
    return parts[-3], parts[-2], log.stem


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("roots", nargs="*", default=None)
    ap.add_argument("--out", help="Write series JSONL here")
    args = ap.parse_args(argv)

    roots = args.roots or DEFAULT_ROOTS
    logs = find_logs(roots)

    series = []
    for log in logs:
        design, variant, stage = design_of(log)
        try:
            found = parse.parse_file(
                log, design="{}/{}".format(design, variant), stage=stage
            )
            for found_series in found:
                found_series.log = short_path(log)
        except OSError as exc:
            print("skip {}: {}".format(log, exc), file=sys.stderr)
            continue
        series.extend(found)

    grinds = [s for s in series if len(s.points) >= 5]
    print(
        "{} logs, {} series, {} with >=5 points".format(
            len(logs), len(series), len(grinds)
        )
    )

    # Longest grinds first: the ones worth forecasting are the ones that
    # printed the most, and the ones with wall-clock are the only ones
    # that can carry an ETA at all.
    for s in sorted(series, key=lambda s: -len(s.points))[:40]:
        stamped = sum(1 for p in s.points if p.t is not None)
        span = ""
        ts = [p.t for p in s.points if p.t is not None]
        if len(ts) >= 2:
            span = "{:.1f}s".format(ts[-1] - ts[0])
        print(
            "  {:22s} {:10s} {:14s} n={:<5d} stamped={:<5d} {:>8s} "
            "{} -> {} (target {}) {}".format(
                s.design,
                s.stage,
                s.kind,
                len(s.points),
                stamped,
                span,
                s.points[0].metric,
                s.points[-1].metric,
                s.target,
                "converged" if s.converged else "gave up",
            )
        )

    if args.out:
        with open(args.out, "w") as f:
            for s in series:
                f.write(s.to_json() + "\n")
        print("wrote {} series to {}".format(len(series), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
