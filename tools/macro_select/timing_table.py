#!/usr/bin/env python3
"""The time half of the macro selection table, from the two probes' dumps.

    timing_table.py --boundaries boundaries.txt --paths paths.txt
                    [--period-ps 800] [--top N]

boundaries.txt is probe_boundaries.tcl's output (one line per module
instance: boundary pins in and out, how many are registered right inside,
cells, flops, empty pipeline stages); paths.txt is probe_paths.tcl's (the
worst path ends with slack, length, endpoint and startpoint pins). Each
path is attributed to the deepest module instance containing its endpoint
and its startpoint; a path whose two ends sit in different modules crosses
a boundary. Per module: registered fraction of its boundary, worst
internal and worst crossing slack among the dumped paths, how many of the
dumped paths end in it, the median path length, and the empty-stage
fraction of its flops, the retiming idiom. Stdlib only, python 3.6.
"""

import argparse
import collections
import sys


def read_boundaries(path):
    mods = {}
    for line in open(path):
        p = line.split()
        if not p or p[0] != "module":
            continue
        d = dict(zip(p[2::2], p[3::2]))
        mods[p[1]] = {
            k: (int(v) if v.lstrip("-").isdigit() else v) for k, v in d.items()
        }
    return mods


def module_of(inst, mods_by_len):
    for m in mods_by_len:
        if inst.startswith(m + "/"):
            return m
    return "/"


def read_paths(path, mods):
    mods_by_len = sorted(mods, key=len, reverse=True)
    rows = []
    for line in open(path):
        p = line.split()
        if len(p) < 4:
            continue
        slack, pins, end, start = float(p[0]), int(p[1]), p[2], p[3]
        rows.append(
            (slack, pins, module_of(end, mods_by_len), module_of(start, mods_by_len))
        )
    return rows


def table(mods, paths, period):
    stats = collections.defaultdict(
        lambda: {"n": 0, "worst": None, "worst_cross": None, "cross": 0, "lens": []}
    )
    for slack, pins, em, sm in paths:
        st = stats[em]
        st["n"] += 1
        st["lens"].append(pins)
        if em != sm:
            st["cross"] += 1
            if st["worst_cross"] is None or slack < st["worst_cross"]:
                st["worst_cross"] = slack
        elif st["worst"] is None or slack < st["worst"]:
            st["worst"] = slack
    rows = []
    for m, d in mods.items():
        st = stats.get(
            m, {"n": 0, "worst": None, "worst_cross": None, "cross": 0, "lens": []}
        )
        pins_in, pins_out = d.get("in", 0), d.get("out", 0)
        reg = d.get("reg_in", 0) + d.get("reg_out", 0)
        total = pins_in + pins_out
        lens = sorted(st["lens"])
        rows.append(
            {
                "module": m,
                "master": d.get("master", ""),
                "pins": total,
                "registered": (reg / float(total)) if total else None,
                "cells": d.get("cells", 0),
                "flops": d.get("flops", 0),
                "empty_stages": (
                    (d.get("empty_stages", 0) / float(d["flops"]))
                    if d.get("flops")
                    else None
                ),
                "paths": st["n"],
                "crossing": st["cross"],
                "worst_ps": st["worst"],
                "worst_cross_ps": st["worst_cross"],
                "median_len": lens[len(lens) // 2] if lens else None,
            }
        )
    return rows


def fmt(v, spec="{:.2f}"):
    return "-" if v is None else spec.format(v)


def format_table(rows, top):
    def key(r):
        w = [v for v in (r["worst_ps"], r["worst_cross_ps"]) if v is not None]
        return min(w) if w else 1e9

    rows = sorted(rows, key=key)
    out = [
        "{:<52} {:>6} {:>5} {:>7} {:>6} {:>5} {:>8} {:>8} {:>5} {:>5}".format(
            "module",
            "pins",
            "reg",
            "cells",
            "flops",
            "empty",
            "worst",
            "x-worst",
            "paths",
            "xing",
        )
    ]
    for r in rows[:top]:
        out.append(
            "{:<52} {:>6} {:>5} {:>7} {:>6} {:>5} {:>8} {:>8} {:>5} {:>5}".format(
                r["module"][-52:],
                r["pins"],
                fmt(r["registered"]),
                r["cells"],
                r["flops"],
                fmt(r["empty_stages"]),
                fmt(r["worst_ps"], "{:.0f}"),
                fmt(r["worst_cross_ps"], "{:.0f}"),
                r["paths"],
                r["crossing"],
            )
        )
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--boundaries", required=True)
    ap.add_argument("--paths", required=True)
    ap.add_argument("--period-ps", type=float, default=800.0)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--json", help="write every row as JSON")
    a = ap.parse_args(argv[1:])
    mods = read_boundaries(a.boundaries)
    paths = read_paths(a.paths, mods)
    rows = table(mods, paths, a.period_ps)
    print(format_table(rows, a.top))
    if a.json:
        import json

        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
