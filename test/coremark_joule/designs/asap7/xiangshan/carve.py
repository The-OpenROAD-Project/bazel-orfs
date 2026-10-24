#!/usr/bin/env python3
"""The smallest macros that keep every critical path inside one: a carve.

    carve.py XSTile_crossings.tsv XSTile_module_area.tsv [--depth 4]
             [--above 2000] [--top 20]

Every endpoint above --above in the crossings (sta_flat.tcl's STA_CROSSINGS,
its M= field) names the modules its worst path's cells sit in. Folded to
--depth levels, those modules must share a macro, so the paths union them;
each component is the least a macro can hold. The rest of the design has no
path above the period across it and may go anywhere: the parent macro.

Printed: the components by area, with their paths and the excess above the
period they carry, and the module pairs that join the largest components,
fewest paths first, the places a surgery would cut.
"""

import argparse
import collections
import sys


def fold(module, depth):
    return "/".join(module.split("/")[:depth])


def read_paths(lines, above, depth):
    """[(period, frozenset of folded modules)] of the endpoints above."""
    out = []
    for line in lines:
        fields = line.rstrip("\n").split("\t")
        if not fields or not fields[0]:
            continue
        period = int(fields[0])
        if period <= above:
            continue
        mods = [f[2:] for f in fields if f.startswith("M=")]
        if not mods or not mods[0]:
            continue
        out.append((period, frozenset(fold(m, depth) for m in mods[0].split(","))))
    return out


def read_area(lines):
    """{module: (cells, um2)}"""
    out = {}
    for line in lines:
        m, cells, um2 = line.rstrip("\n").split("\t")
        out[m] = (int(cells), float(um2))
    return out


class Union:
    def __init__(self):
        self.up = {}

    def find(self, x):
        self.up.setdefault(x, x)
        while self.up[x] != x:
            self.up[x] = self.up[self.up[x]]
            x = self.up[x]
        return x

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.up[max(a, b)] = min(a, b)


def own(module, area, depth):
    """A module's (cells, um2) as a unit of the carve: at the fold depth its
    whole subtree; above it only the cells directly in it, its submodules
    being units of their own."""
    cells, um2 = area.get(module, (0, 0.0))
    if module.count("/") + 1 >= depth:
        return cells, um2
    for m, (c, a) in area.items():
        if m.startswith(module + "/") and m.count("/") == module.count("/") + 1:
            cells -= c
            um2 -= a
    return cells, um2


def carve(paths, area, above, depth):
    """The components, largest first: each a dict of its modules, area,
    paths and excess; and every module pair's (paths, excess)."""
    u = Union()
    pair = collections.defaultdict(lambda: [0, 0])
    for period, mods in paths:
        ms = sorted(mods)
        for m in ms:
            u.find(m)
        for a, b in zip(ms, ms[1:]):
            u.join(a, b)
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                pair[(a, b)][0] += 1
                pair[(a, b)][1] += period - above
    comps = collections.defaultdict(lambda: {"modules": set(), "paths": 0, "excess": 0})
    for m in u.up:
        comps[u.find(m)]["modules"].add(m)
    for period, mods in paths:
        c = comps[u.find(next(iter(mods)))]
        c["paths"] += 1
        c["excess"] += period - above
    out = []
    for c in comps.values():
        units = [own(m, area, depth) for m in c["modules"]]
        c["cells"] = sum(u[0] for u in units)
        c["um2"] = sum(u[1] for u in units)
        out.append(c)
    out.sort(key=lambda c: -c["um2"])
    return out, pair


def render(comps, pair, area_total, top):
    lines = ["| # | modules | cells | um2 | % of design | paths | excess, ps summed |",
             "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(comps[:top], 1):
        mods = ", ".join(f"`{m}`" for m in sorted(c["modules"])[:6])
        more = len(c["modules"]) - 6
        if more > 0:
            mods += f" … +{more}"
        lines.append(f"| {i} | {mods} | {c['cells']:,} | {c['um2']:,.0f} | "
                     f"{100 * c['um2'] / area_total:.1f} | {c['paths']:,} | {c['excess']:,} |")
    lines += ["", "| joins | paths | excess, ps summed |", "|---|---|---|"]
    big = set().union(*(c["modules"] for c in comps[:3])) if comps else set()
    joins = sorted(((k, v) for k, v in pair.items() if k[0] in big or k[1] in big),
                   key=lambda kv: (kv[1][0], kv[1][1]))
    for (a, b), (n, e) in joins[:top]:
        lines.append(f"| `{a}` + `{b}` | {n:,} | {e:,} |")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("crossings")
    ap.add_argument("module_area")
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--above", type=int, default=2000)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)
    with open(args.crossings) as f:
        paths = read_paths(f, args.above, args.depth)
    with open(args.module_area) as f:
        area = read_area(f)
    total = sum(v[1] for m, v in area.items() if "/" not in m)
    comps, pair = carve(paths, area, args.above, args.depth)
    print(f"{len(paths):,} endpoints above {args.above} ps; modules folded to "
          f"{args.depth} levels; design {total:,.0f} um2\n")
    print(render(comps, pair, total, args.top))


if __name__ == "__main__":
    main(sys.argv[1:])
