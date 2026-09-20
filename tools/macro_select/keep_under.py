#!/usr/bin/env python3
"""The keep list for a block's own synthesis, from the boundary probe.

    keep_under.py --boundaries boundaries.txt --master Frontend
                  [--min-cells 20000] [--min-pins 0]

boundaries.txt is probe_boundaries.tcl's dump of the hierarchical parent:
one line per module instance with its path, master, boundary pins and
cells. The masters instantiated under an instance of the given master,
with at least the given cells, are the modules the block's own synthesis
keeps (SYNTH_KEEP_MODULES), so the block partitions along the same
boundaries the parent's probe measured. Every instance of the master is
walked; a master appears once. Stdlib only, python 3.6.
"""

import argparse
import sys


def read(path):
    rows = []
    for line in open(path):
        p = line.split()
        if not p or p[0] != "module":
            continue
        d = dict(zip(p[2::2], p[3::2]))
        rows.append((p[1], d.get("master", ""), int(d.get("cells", 0)), int(d.get("in", 0)) + int(d.get("out", 0))))
    return rows


def keep_under(rows, master, min_cells=0, min_pins=0):
    roots = [path for path, m, _, _ in rows if m == master]
    keep = []
    for path, m, cells, pins in sorted(rows, key=lambda r: -r[2]):
        if m == master or m in keep:
            continue
        if cells < min_cells or pins < min_pins:
            continue
        if any(path.startswith(r + "/") for r in roots):
            keep.append(m)
    return keep


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boundaries", required=True)
    ap.add_argument("--master", required=True)
    ap.add_argument("--min-cells", type=int, default=20000)
    ap.add_argument("--min-pins", type=int, default=0)
    a = ap.parse_args(argv[1:])
    rows = read(a.boundaries)
    if not any(m == a.master for _, m, _, _ in rows):
        print("keep_under: no instance of " + a.master, file=sys.stderr)
        return 1
    print(" ".join(keep_under(rows, a.master, a.min_cells, a.min_pins)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
