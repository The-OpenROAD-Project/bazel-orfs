#!/usr/bin/env python3
"""The keep list for a block's own synthesis, from the boundary probe.

    keep_under.py --boundaries boundaries.txt --master Frontend
                  [--min-cells 20000] [--min-pins 0] [--modules names.txt]
    keep_under.py --boundaries boundaries.txt --outside Frontend,MemBlock
                  --keep-list parent_keep.txt

boundaries.txt is probe_boundaries.tcl's dump of the hierarchical parent:
one line per module instance with its path, master, boundary pins and
cells. The masters instantiated under an instance of the given master,
with at least the given cells, are the modules the block's own synthesis
keeps (SYNTH_KEEP_MODULES), so the block partitions along the same
boundaries the parent's probe measured. Every instance of the master is
walked; a master appears once. A hierarchical synthesis renames the
modules it uniquifies (PMPChecker_inner_PMPChecker_1), and a keep list
naming one fails the block's keep pass ("not present in checkpoint"), so
--modules, a file of the RTL's module names, drops every master the RTL
does not define.

--outside is the parent's side of the same cut: of the modules in
--keep-list (the parent's keep list before the blocks were hardened),
those with an instance that is not under any of the named blocks, since a
module the blocks swallowed whole no longer exists in the parent and a
keep list naming it fails the parent's synthesis. The blocks themselves
are appended. Stdlib only, python 3.6.
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
        rows.append(
            (
                p[1],
                d.get("master", ""),
                int(d.get("cells", 0)),
                int(d.get("in", 0)) + int(d.get("out", 0)),
            )
        )
    return rows


def keep_under(rows, master, min_cells=0, min_pins=0, modules=None):
    roots = [path for path, m, _, _ in rows if m == master]
    keep = []
    for path, m, cells, pins in sorted(rows, key=lambda r: -r[2]):
        if m == master or m in keep:
            continue
        if modules is not None and m not in modules:
            continue
        if cells < min_cells or pins < min_pins:
            continue
        if any(path.startswith(r + "/") for r in roots):
            keep.append(m)
    return keep


def keep_outside(rows, blocks, keep_list):
    roots = [path for path, m, _, _ in rows if m in blocks]
    inside = lambda path: any(path.startswith(r + "/") for r in roots)
    outside = set(m for path, m, _, _ in rows if not inside(path))
    return [m for m in keep_list if m in outside and m not in blocks] + list(blocks)


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--boundaries", required=True)
    ap.add_argument("--master", help="the block whose own keep list to derive")
    ap.add_argument(
        "--outside", help="A,B,C: the blocks; keep what stays in the parent"
    )
    ap.add_argument(
        "--keep-list", help="with --outside: the parent's keep list before the cut"
    )
    ap.add_argument("--min-cells", type=int, default=20000)
    ap.add_argument("--min-pins", type=int, default=0)
    ap.add_argument(
        "--modules", help="file of the RTL's module names; others are dropped"
    )
    a = ap.parse_args(argv[1:])
    rows = read(a.boundaries)
    if a.outside:
        blocks = a.outside.split(",")
        keep = open(a.keep_list).read().split() if a.keep_list else []
        print(" ".join(keep_outside(rows, blocks, keep)))
        return 0
    if not a.master:
        ap.error("--master or --outside is required")
    modules = set(open(a.modules).read().split()) if a.modules else None
    if not any(m == a.master for _, m, _, _ in rows):
        print("keep_under: no instance of " + a.master, file=sys.stderr)
        return 1
    print(" ".join(keep_under(rows, a.master, a.min_cells, a.min_pins, modules)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
