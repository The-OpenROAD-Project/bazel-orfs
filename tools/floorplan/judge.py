#!/usr/bin/env python3
"""Name where a global route is over capacity, the planner's way, and set
it beside the planner's verdict.

  judge.py <congestion.rpt> <macros.txt> <verdict.json> <out.json>

The congestion report is FastRoute's (probe_congestion.tcl: a box and a
layer per region over capacity); macros.txt the routed parent's die and
macro outlines. Each region is named as plan.py names a channel: the
macros (or the die edge) either side of it across its wires' direction,
by master, the macro of the cut the master is. Out: the overflow per
channel from the route, the channels and sides the verdict calls over
capacity, and the agreement: the channels both name, the ones only the
route shows (missed) and the ones only the verdict names (false alarms).

Stdlib only.
"""

import argparse
import json
import re
import sys

BBOX = re.compile(
    r"bbox = \(\s*([-\d.]+),\s*([-\d.]+)\s*\) - \(\s*([-\d.]+),\s*([-\d.]+)\s*\)(?: on Layer (\S+))?"
)
TYPE = re.compile(r"violation type: (Horizontal|Vertical) congestion", re.I)
OVER = re.compile(r"congestion:\s*(-?\d+)")


def parse_report(lines):
    """[(direction h|v, layer, x0, y0, x1, y1, overflow)]"""
    out = []
    direction = None
    over = 1
    for line in lines:
        m = TYPE.search(line)
        if m:
            direction = "h" if m.group(1).lower().startswith("h") else "v"
            over = 1
            continue
        m = OVER.search(line)
        if m:
            over = int(m.group(1))
        m = BBOX.search(line)
        if m and direction:
            x0, y0, x1, y1 = (float(v) for v in m.group(1, 2, 3, 4))
            out.append((direction, m.group(5) or "", x0, y0, x1, y1, over))
    return out


def parse_macros(lines):
    die = None
    macros = []
    for line in lines:
        f = line.split()
        if not f:
            continue
        if f[0] == "die":
            die = (float(f[1]), float(f[2]))
        elif f[0] == "macro":
            macros.append(
                (f[1], f[2], float(f[3]), float(f[4]), float(f[5]), float(f[6]))
            )
    return die, macros


def channel(macros, direction, cx, cy, names):
    """The macros either side of a point across its wires' direction (ORFS
    frame: a horizontal wire's channel runs between a macro below and one
    above)."""
    if direction == "h":
        lo = [
            (cy - y1, n)
            for _, n, x0, y0, x1, y1 in macros
            if x0 <= cx <= x1 and y1 <= cy
        ]
        hi = [
            (y0 - cy, n)
            for _, n, x0, y0, x1, y1 in macros
            if x0 <= cx <= x1 and y0 >= cy
        ]
    else:
        lo = [
            (cx - x1, n)
            for _, n, x0, y0, x1, y1 in macros
            if y0 <= cy <= y1 and x1 <= cx
        ]
        hi = [
            (x0 - cx, n)
            for _, n, x0, y0, x1, y1 in macros
            if y0 <= cy <= y1 and x0 >= cx
        ]
    a = names.get(min(lo)[1], min(lo)[1]) if lo else "die"
    b = names.get(min(hi)[1], min(hi)[1]) if hi else "die"
    return "|".join(sorted([a, b]))


def judge(regions, macros, verdict, names):
    route = {}
    for direction, layer, x0, y0, x1, y1, over in regions:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inside = [n for _, n, a0, b0, a1, b1 in macros if a0 < cx < a1 and b0 < cy < b1]
        name = (
            "over " + names.get(inside[0], inside[0])
            if inside
            else channel(macros, direction, cx, cy, names)
        )
        r = route.setdefault(name, {"regions": 0, "overflow": 0, "layers": {}})
        r["regions"] += 1
        r["overflow"] += over
        r["layers"][layer] = r["layers"].get(layer, 0) + over
    plan = {}
    for f in verdict.get("findings", []):
        if f["status"] not in ("fail", "measured") or f["rung"] != "channel_capacity":
            continue
        name = f.get("channel") or "%s|%s" % (f.get("macro"), f.get("partner"))
        plan[name] = {"kind": f.get("kind"), "utilisation": f.get("utilisation")}
    both = sorted(set(route) & set(plan))
    return {
        "route": dict(sorted(route.items(), key=lambda kv: -kv[1]["overflow"])),
        "plan": plan,
        "agree": both,
        "missed": sorted(set(route) - set(plan)),
        "false_alarms": sorted(set(plan) - set(route)),
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("report")
    ap.add_argument("macros")
    ap.add_argument("verdict")
    ap.add_argument("out")
    ap.add_argument("--cut", help="cut.json: a master's macro name, when they differ")
    a = ap.parse_args(argv)
    with open(a.report) as f:
        regions = parse_report(f)
    with open(a.macros) as f:
        _, macros = parse_macros(f)
    with open(a.verdict) as f:
        verdict = json.load(f)
    names = {}
    if a.cut:
        with open(a.cut) as f:
            for m, spec in json.load(f)["macros"].items():
                names[spec["block"] if isinstance(spec, dict) else spec] = m
    out = judge(regions, macros, verdict, names)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(
        "agree %s; missed %s; false alarms %s"
        % (out["agree"], out["missed"], out["false_alarms"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
