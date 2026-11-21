#!/usr/bin/env python3
"""Name where a global route is over capacity, the planner's way, and set
it beside the planner's verdict.

  judge.py <congestion.rpt> <macros.txt> <verdict.json> <out.json>
           [--cut cut.json] [--side-band-um B]

The congestion report is FastRoute's (probe_congestion.tcl: a box and a
layer per region over capacity); macros.txt the routed parent's die and
macro outlines. Each region is named as plan.py names a channel: the
macros (or the die edge) either side of it across its wires' direction,
by master, the macro of the cut the master is. Out: the overflow per
channel from the route, the channels and sides the verdict calls over
capacity, and the agreement: the channels both name, the ones only the
route shows (missed) and the ones only the verdict names (false alarms).

A region inside a macro within B of one of its sides is that side's
(the pins' escape and via stacks), deeper it is over the macro. Beside
the agreement, the calibration view: every channel's peak utilisation
in the plan against the route's overflow there, every side's track
spacing against the route's overflow in its band, Kendall's tau-b of
each, and the limit that separates the clean from the overflowing ones
where they separate (the design's channel_capacity gcell_limit and
pins_per_um facing_track_spacing, facing sides only).

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


def side_of(box, cx, cy, band):
    """The side of a macro box a point inside it is within `band` of."""
    _, _, a0, b0, a1, b1 = box
    d = {"W": cx - a0, "E": a1 - cx, "S": cy - b0, "N": b1 - cy}
    s = min(d, key=d.get)
    return s if d[s] <= band else None


def judge(regions, macros, verdict, names, band=10.0):
    route = {}
    for direction, layer, x0, y0, x1, y1, over in regions:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inside = [m for m in macros if m[2] < cx < m[4] and m[3] < cy < m[5]]
        if inside:
            m = names.get(inside[0][1], inside[0][1])
            s = side_of(inside[0], cx, cy, band)
            name = "%s side %s" % (m, s) if s else "over " + m
        else:
            name = channel(macros, direction, cx, cy, names)
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
    chans = {}
    for c in verdict.get("channels", []):
        r = chans.setdefault(c["channel"], {"utilisation": 0.0})
        r["utilisation"] = max(r["utilisation"], c["utilisation"])
    for n, r in chans.items():
        r["overflow"] = route.get(n, {}).get("overflow", 0)
    sides = {}
    for e in verdict.get("sides", []):
        n = "%s side %s" % (e["macro"], e["side"])
        sides[n] = {
            "bits": e["bits"],
            "track_spacing": e["track_spacing"].get(e["lowest"]),
            "lateral": bool(e["lateral"]),
            "overflow": route.get(n, {}).get("overflow", 0),
        }
    calib = {
        "side_band_um": band,
        "channels": rank(
            [(r["utilisation"], r["overflow"]) for r in chans.values()], True
        ),
        "facing_sides": rank(
            [
                (r["track_spacing"], r["overflow"])
                for r in sides.values()
                if not r["lateral"] and r["track_spacing"] is not None
            ],
            False,
        ),
    }
    return {
        "channels": dict(sorted(chans.items(), key=lambda kv: -kv[1]["utilisation"])),
        "sides": dict(sorted(sides.items())),
        "calibration": calib,
        "route": dict(sorted(route.items(), key=lambda kv: -kv[1]["overflow"])),
        "plan": plan,
        "agree": both,
        "missed": sorted(set(route) - set(plan)),
        "false_alarms": sorted(set(plan) - set(route)),
    }


def tau_b(pairs):
    n = len(pairs)
    if n < 3:
        return None
    c = d = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = pairs[i][0] - pairs[j][0]
            dy = pairs[i][1] - pairs[j][1]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif dx * dy > 0:
                c += 1
            else:
                d += 1
    den = ((c + d + tx) * (c + d + ty)) ** 0.5
    return round((c - d) / den, 4) if den else None


def rank(pairs, higher_is_worse):
    """Kendall's tau-b of a feature against the overflow (positive: the
    feature ranks it), and the limit between the clean and the
    overflowing, the geometric mean of the nearest two, when they
    separate."""
    t = tau_b(pairs)
    if t is not None and not higher_is_worse:
        t = -t
    ok = [x for x, o in pairs if o <= 0]
    bad = [x for x, o in pairs if o > 0]
    limit = None
    if ok and bad:
        lo, hi = (max(ok), min(bad)) if higher_is_worse else (max(bad), min(ok))
        if lo < hi and lo > 0:
            limit = round((lo * hi) ** 0.5, 4)
    return {
        "n": len(pairs),
        "clean": len(ok),
        "overflowing": len(bad),
        "tau_b": t,
        "limit": limit,
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
    ap.add_argument(
        "--side-band-um",
        type=float,
        default=10.0,
        help="a region inside a macro this near a side is the side's",
    )
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
    out = judge(regions, macros, verdict, names, a.side_band_um)
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
