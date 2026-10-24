#!/usr/bin/env python3
"""What a carve leaves crossing: each critical path's hops between its macros.

    carve_hops.py XSTile_crossings.tsv --carve "core/x=X core=GLUE ..."
                  [--cones XSTile_cones.tsv] [--wire 0.5]

A carve names the macro of each module, longest prefix first (the form
sta_flat.tcl's STA_CARVE takes). Each endpoint in the crossings
(sta_flat.tcl's STA_CROSSINGS) has its worst path as unit stretches, U=;
a stretch with no logic cell is wire and may sit anywhere, so a path is
inside a macro when every stretch with logic is. The rest cross: grouped
by their sequence of macros, a bundle, with the logic delay and cells each
macro holds of it. --cones adds the cone a push across each hop would move
(STA_CONES). The period each carve leaves: the worst path inside any one
macro, as built and with --wire of its wire (W=) taken off.
"""

import argparse
import collections
import sys


def parse_carve(spec):
    """[(prefix, macro)], longest prefix first."""
    pairs = [p.split("=", 1) for p in spec.split()]
    return sorted(((p, m) for p, m in pairs), key=lambda pm: -len(pm[0]))


def macro(unit, carve):
    for prefix, m in carve:
        if unit == prefix or unit.startswith(prefix + "/"):
            return m
    return "TOP"


def read_paths(lines):
    """[(period, wire, [(unit, ps, logic cells)], hold)]"""
    out = []
    for line in lines:
        fields = line.rstrip("\n").split("\t")
        if not fields or not fields[0]:
            continue
        kv = {f[0]: f[2:] for f in fields if len(f) > 1 and f[1] == "="}
        stretches = []
        for s in kv.get("U", "").split(","):
            if s:
                unit, ps, cells = s.rsplit(":", 2)
                stretches.append((unit, int(ps), int(cells)))
        out.append(
            (int(fields[0]), float(kv.get("W", 0)), stretches, float(kv.get("H", 0)))
        )
    return out


def macros_of(stretches, carve):
    """The path's macros in order, consecutive ones merged: [[macro, ps, cells]];
    stretches without logic are left out."""
    seq = []
    for unit, ps, cells in stretches:
        if cells == 0:
            continue
        m = macro(unit, carve)
        if seq and seq[-1][0] == m:
            seq[-1][1] += ps
            seq[-1][2] += cells
        else:
            seq.append([m, ps, cells])
    return seq


def score(paths, carve, wire=0.5):
    """(inside: {macro: [periods]}, floors: {macro: (worst, worst less wire)},
    bundles: {"A>B": [(period, seq)]})"""
    inside = collections.defaultdict(list)
    floors = {}
    bundles = collections.defaultdict(list)
    for period, w, stretches, _ in paths:
        seq = macros_of(stretches, carve)
        names = [s[0] for s in seq]
        if len(set(names)) <= 1:
            m = names[0] if names else "TOP"
            inside[m].append(period)
            built, less = floors.get(m, (0, 0))
            floors[m] = (max(built, period), max(less, period - wire * w))
        else:
            bundles[">".join(names)].append((period, seq))
    return inside, floors, bundles


def read_cones(lines):
    """{"A>B": (paths, drivers, cells, um2, flops, other startpoints)}"""
    out = {}
    for line in lines:
        f = line.rstrip("\n").split("\t")
        if len(f) == 7:
            out[f[0]] = (
                int(f[1]),
                int(f[2]),
                int(f[3]),
                float(f[4]),
                int(f[5]),
                int(f[6]),
            )
    return out


def render(inside, floors, bundles, cones, wire, out):
    total_in = sum(len(v) for v in inside.values())
    total_x = sum(len(v) for v in bundles.values())
    out.write("inside one macro: %d endpoints, crossing: %d\n" % (total_in, total_x))
    out.write(
        "\nfloor per macro (worst inside; with %.0f%% of its wire off)\n" % (100 * wire)
    )
    for m, (built, less) in sorted(floors.items(), key=lambda kv: -kv[1][0]):
        out.write(
            "  %-8s %5d paths  %5d ps  %5.0f ps\n" % (m, len(inside[m]), built, less)
        )
    out.write("\nbundles: paths, worst, mean logic ps/cells per macro\n")
    for key, v in sorted(bundles.items(), key=lambda kv: -len(kv[1])):
        agg = collections.OrderedDict()
        for _, seq in v:
            for m, ps, cells in seq:
                a = agg.setdefault(m, [0, 0])
                a[0] += ps
                a[1] += cells
        side = " ".join(
            "%s:%d/%d" % (m, a[0] // len(v), round(a[1] / len(v)))
            for m, a in agg.items()
        )
        out.write("  %5d %5d  %-28s %s\n" % (len(v), max(p for p, _ in v), key, side))
    if cones:
        out.write(
            "\nhop cones: paths, drivers, cells, um2, source flops, other starts\n"
        )
        for hop, c in sorted(cones.items(), key=lambda kv: -kv[1][0]):
            out.write("  %-12s %5d %5d %7d %9.1f %6d %6d\n" % ((hop,) + c))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("crossings")
    ap.add_argument("--carve", required=True)
    ap.add_argument("--cones")
    ap.add_argument("--wire", type=float, default=0.5)
    args = ap.parse_args(argv)
    with open(args.crossings) as f:
        paths = read_paths(f)
    cones = {}
    if args.cones:
        with open(args.cones) as f:
            cones = read_cones(f)
    carve = parse_carve(args.carve)
    render(*score(paths, carve, args.wire), cones, args.wire, sys.stdout)


if __name__ == "__main__":
    main()
