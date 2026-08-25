"""Decide whether a resident estimator is worth building, from data.

The fork/join batch walk logs every executed tree edge (its trie path,
stage, and seconds) into edges.jsonl. Run a study with --keep-waves DIR
and point this tool at DIR: it reports, per wave and in total,

  * realized saving  -- what the walk already saved against naive
    one-process-per-trial (sum of the leaves' path costs minus the sum
    of executed edges);
  * resident-root    -- what keeping one loaded process alive between
    waves would additionally have saved (load + floorplan of every wave
    after the first);
  * snapshot-cache   -- the upper bound on keeping every suspended
    branch-point snapshot alive across waves: the time spent
    re-computing an edge (same trie path, same stage) an earlier wave
    had already paid for.

Build the resident mode when resident-root/snapshot-cache numbers are
large against total study time; until then the complexity is not paid
for.
"""

import argparse
import glob
import json
import os
import sys


def read_edges(wave_dir):
    path = os.path.join(wave_dir, "edges.jsonl")
    edges = []
    if not os.path.exists(path):
        return edges
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                edges.append(json.loads(line))
    return edges


def leaf_runtimes(wave_dir):
    total = 0.0
    for leaf in glob.glob(os.path.join(wave_dir, "*.json")):
        if os.path.basename(leaf) == "edges.jsonl":
            continue
        with open(leaf) as f:
            data = json.load(f)
        if "runtime_s" in data:
            total += data["runtime_s"]
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("study_dir", help="directory holding wave_*/ results")
    args = ap.parse_args()

    waves = sorted(glob.glob(os.path.join(args.study_dir, "wave_*")))
    if not waves:
        sys.exit(f"no wave_* directories under {args.study_dir}")

    seen = set()
    total_edges = total_naive = resident_root = snapshot_cache = 0.0
    print(f"{'wave':<12}{'edges_s':>10}{'naive_s':>10}{'repeated_s':>12}")
    for i, wave_dir in enumerate(waves):
        edges = read_edges(wave_dir)
        edges_s = sum(e["seconds"] for e in edges)
        naive_s = leaf_runtimes(wave_dir)
        repeated = 0.0
        for e in edges:
            key = (e["path"], e["stage"])
            if e["stage"] in ("load", "floorplan"):
                if i > 0:
                    resident_root += e["seconds"]
            if key in seen:
                repeated += e["seconds"]
            else:
                seen.add(key)
        total_edges += edges_s
        total_naive += naive_s
        snapshot_cache += repeated
        print(
            f"{os.path.basename(wave_dir):<12}{edges_s:>10.1f}"
            f"{naive_s:>10.1f}{repeated:>12.1f}"
        )

    print()
    print(f"executed (fork/join):        {total_edges:>10.1f} s")
    print(f"naive one-per-trial cost:    {total_naive:>10.1f} s")
    print(f"realized saving:             {total_naive - total_edges:>10.1f} s")
    print(f"resident-root would save:    {resident_root:>10.1f} s")
    print(f"snapshot-cache upper bound:  {snapshot_cache:>10.1f} s")


if __name__ == "__main__":
    main()
