#!/usr/bin/env python3
"""Upper bound on a parent's period if its blocks' boundary flops moved out.

Joins the parent's worst paths (probe_peel_paths.tcl) with each block's
peelable flops (probe_peel.tcl, run with PEEL_TIMING=1). A path launched
by a block port that a peelable flop drives has two stages around that
flop: the block's own stage into it (da) and the parent's crossing out
of it (db, the path). A peeled flop placed by the parent can slide along
the crossing's repeaters and wire, moving up to `crossing` picoseconds
from db to da, so the path is at best

    x = clamp((db - da) / 2, 0, crossing)
    max(db - x, da + x)

Every other path keeps its delay. The bound is the largest over the
paths probed, and no lower than the last probed path's delay: paths
below the probe's count are not seen, so a bound equal to that floor
says to probe more paths.

This is an upper bound on the gain: it assumes the flop's clock arrives
when the block's did, the crossing's delay moves one for one, and
nothing else on either stage changes.

Usage: peel_bound.py PATHS.tsv BLOCK=BLOCK.tsv [BLOCK=BLOCK.tsv ...]
           [--pure-only] [--csv OUT.csv]
"""

import argparse
import csv
import sys


def read_tsv(path):
    with open(path) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def peelable_ports(rows, pure_only=False):
    """Output port -> (da_ps, extra_pins) for each flop that drives one."""
    ports = {}
    for r in rows:
        if not r["kind"].startswith("out_"):
            continue
        extra = int(r["extra_pins"])
        if pure_only and extra:
            continue
        da = float(r["da_ps"]) if r["da_ps"] else None
        for p in r["ports"].split(","):
            ports[p] = (da, extra)
    return ports


def path_bound(db, da, crossing):
    """The best a path launched by a peeled flop can do."""
    x = min(max((db - da) / 2.0, 0.0), crossing)
    return max(db - x, da + x)


def bound(paths, blocks, pure_only=False):
    """Per-path rows and the summary over the paths probed."""
    ports = {b: peelable_ports(rows, pure_only) for b, rows in blocks.items()}
    out = []
    for p in paths:
        db = float(p["path_ps"])
        new = db
        da = None
        peeled = False
        block = p["launch_block"]
        if block in ports and p["launch_port"] in ports[block]:
            da, _ = ports[block][p["launch_port"]]
            if da is not None and p["crossing_ps"]:
                new = path_bound(db, da, float(p["crossing_ps"]))
                peeled = True
        out.append(dict(p, da_ps=da, peeled=peeled, bound_ps=new))
    if not out:
        raise ValueError("no paths: run probe_peel_paths.tcl first")
    floor = min(float(r["path_ps"]) for r in out)
    worst = max(r["bound_ps"] for r in out)
    stays = [r for r in out if not r["peeled"]]
    summary = {
        "paths": len(out),
        "peeled": sum(r["peeled"] for r in out),
        "period_ps": max(float(r["path_ps"]) for r in out),
        "bound_ps": max(worst, floor),
        "floor_ps": floor,
        "first_unpeeled_ps": max(float(r["path_ps"]) for r in stays) if stays else None,
        "at_floor": worst <= floor,
    }
    return out, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths")
    ap.add_argument("blocks", nargs="+", help="BLOCK=probe_peel.tsv")
    ap.add_argument(
        "--pure-only",
        action="store_true",
        help="only flops that peel without a new core pin",
    )
    ap.add_argument("--csv", help="per-path rows")
    a = ap.parse_args(argv)
    blocks = {}
    for spec in a.blocks:
        name, _, path = spec.partition("=")
        if not path:
            ap.error("block argument is BLOCK=file.tsv: %s" % spec)
        blocks[name] = read_tsv(path)
    rows, s = bound(read_tsv(a.paths), blocks, a.pure_only)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(
        "paths probed      %d, launched by a peelable flop %d"
        % (s["paths"], s["peeled"])
    )
    print("period now        %.0f ps" % s["period_ps"])
    print("bound with peel   %.0f ps" % s["bound_ps"])
    if s["first_unpeeled_ps"] is not None:
        print("worst unpeelable  %.0f ps" % s["first_unpeeled_ps"])
    if s["at_floor"]:
        print(
            "the bound is the probe's floor (%.0f ps): probe more paths" % s["floor_ps"]
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
