#!/usr/bin/env python3

"""Extract the history of every ORFS `rules-base.json` into a flat table.

The premise of this study is that OpenROAD-flow-scripts has been running
a noise experiment for years and committing the results. Each time a
design's QoR moved enough that CI complained -- or improved enough that
somebody re-ran `update_rules` -- a new threshold was written into that
design's `rules-base.json`. The file's git history is therefore a
sampled time series of the design's quality, one sample per revision.

This script recovers that series. It walks first-parent history so the
timeline is "what landed on master", in order, without counting a side
branch's commits twice, and it reads the blob at every revision rather
than parsing diffs -- a JSON diff is a poor way to learn a number.

Output is one CSV row per (design, metric, commit): the raw threshold as
committed. Nothing is de-padded, segmented or interpreted here; those
are separate steps with separate failure modes.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys

RULES_GLOB = "flow/designs/*/*/rules-base.json"

# flow/designs/<platform>/<design>/rules-base.json
PATH_RE = re.compile(r"^flow/designs/([^/]+)/([^/]+)/rules-base\.json$")

ZERO_SHA = "0" * 40


def git(repo, *args):
    """Run git in `repo` and return stdout as text."""
    return subprocess.run(
        ["git", "-C", repo, *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    ).stdout


def walk_history(repo, ref):
    """Yield (commit, unix_time, path, blob) for every rules-file revision.

    First-parent only: the question is what the mainline recorded, and
    when. A blob of all zeros means the file was deleted at that commit,
    which is a real event (a design leaving the fleet) and is reported as
    a blob of None rather than skipped.
    """
    out = git(
        repo,
        "log",
        "--first-parent",
        "--format=commit %H %at",
        "--raw",
        "--no-abbrev",
        "--no-renames",
        ref,
        "--",
        RULES_GLOB,
    )
    commit = None
    when = None
    for line in out.splitlines():
        if line.startswith("commit "):
            _, commit, when = line.split()
            continue
        if not line.startswith(":"):
            continue
        # :100644 100644 <old> <new> M\tpath
        meta, _, path = line.partition("\t")
        fields = meta.split()
        if len(fields) < 5:
            continue
        new_blob = fields[3]
        if not PATH_RE.match(path):
            continue
        yield commit, int(when), path, (None if new_blob == ZERO_SHA else new_blob)


def read_blobs(repo, blobs):
    """Bulk-read blobs with `git cat-file --batch`.

    7500-odd `git show` invocations is a minute of fork() for no reason;
    one batched pipe is a second.
    """
    wanted = sorted(set(b for b in blobs if b))
    if not wanted:
        return {}
    proc = subprocess.run(
        ["git", "-C", repo, "cat-file", "--batch"],
        input=("\n".join(wanted) + "\n").encode("ascii"),
        stdout=subprocess.PIPE,
        check=True,
        text=False,
    )
    data = proc.stdout
    out = {}
    pos = 0
    while pos < len(data):
        nl = data.index(b"\n", pos)
        header = data[pos:nl].decode("ascii", "replace").split()
        pos = nl + 1
        if len(header) < 3:
            break
        sha, _kind, size = header[0], header[1], int(header[2])
        out[sha] = data[pos : pos + size]
        pos += size + 1  # trailing newline
    return out


def parse_rules(raw):
    """Parse a rules-base.json blob into {metric: (value, compare, level)}.

    Malformed revisions exist in any long history; they are reported to
    the caller rather than crashing the walk.
    """
    doc = json.loads(raw.decode("utf-8", "replace"))
    if not isinstance(doc, dict):
        raise ValueError("top level is not an object")
    out = {}
    for metric, spec in doc.items():
        if not isinstance(spec, dict):
            continue
        out[metric] = (
            spec.get("value"),
            spec.get("compare"),
            spec.get("level", ""),
        )
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="ORFS checkout to read")
    ap.add_argument("--ref", default="HEAD", help="ref whose history to walk")
    ap.add_argument("--out", required=True, help="CSV to write")
    args = ap.parse_args(argv)

    revisions = list(walk_history(args.repo, args.ref))
    blobs = read_blobs(args.repo, [b for _, _, _, b in revisions])

    rows = 0
    bad = 0
    deleted = 0
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["platform", "design", "commit", "unix_time", "metric", "value", "compare", "level"]
        )
        for commit, when, path, blob in revisions:
            platform, design = PATH_RE.match(path).groups()
            if blob is None:
                deleted += 1
                continue
            try:
                rules = parse_rules(blobs[blob])
            except Exception as exc:  # a bad revision is data, not a crash
                bad += 1
                print(f"[WARN] {commit[:12]} {path}: {exc}", file=sys.stderr)
                continue
            for metric, (value, compare, level) in rules.items():
                w.writerow([platform, design, commit, when, metric, value, compare, level])
                rows += 1

    print(
        f"revisions={len(revisions)} rows={rows} unparseable={bad} deletions={deleted}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
