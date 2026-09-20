#!/usr/bin/env python3
"""Plan a parent floorplan from its macros' interfaces.

A macro chosen by its interface has few pins for its area, and they belong
on the one side that faces the logic they talk to. That side has to be long
enough for the pins at a routable pitch, which fixes the macro's aspect
ratio; the channel in front of it has to carry the wires and the cells the
parent puts there; and the parent's own logic needs a region of its own.
None of that is a placer's job to discover. This plans it:

  pin side     S = pins * pitch * margin / layers, split over two adjacent
               sides when one side would break the aspect cap
  outline      S by A / S, the pin side facing the logic region
  channel      W = max(channel_min, pins / track_density * lateral):
               wires that run along the channel before turning in, plus
               the cells the parent puts there (buffers, the clock tree)
  logic region a square of the parent's cell area over its density
  ring         macros around the region, pin sides inward, assigned to the
               region's four sides so their pin-side lengths balance; the
               region grows to the longest side's need
  die          the ring's bounding box plus the core margin
  timing       each macro's worst boundary slack minus the wire it now has
               to cross (channel plus half the region), from the platform's
               ps per um; a negative result means the cut is wrong for this
               geometry, not that the floorplan is

Input is one JSON (see the docstring of load_plan); output is one JSON with
every number and, per block, the outline and pin side its own flow needs,
and for the parent the macro positions, all R0: a block's pin side is chosen
in its own frame so that no flip is needed, which keeps every pin on the
parent's tracks (see macro_anneal.flip_legal for why flips are trouble).

Stdlib only; python 3.6.
"""

import argparse
import json
import math
import sys

SIDES = ("bottom", "right", "top", "left")
# Which side of the block, in its own frame, faces the region when the
# block sits on the given side of the region, placed R0.
FACING = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}


def load_plan(path):
    """The plan's input.

    {
      "tech": {"pin_pitch_um": 0.096, "pin_layers": 2,
               "track_density_per_um": 48.6, "wire_ps_per_um": 0.6,
               "site_um": 0.054, "row_um": 0.27},
      "parent": {"cell_area_um2": 220000, "density": 0.5,
                 "core_margin_um": 10},
      "margins": {"pin_side": 1.5, "channel_min_um": 40,
                  "lateral": 0.5, "aspect_cap": 3.0, "gap_um": 10.8},
      "macros": [{"name": "Frontend", "pins": 3294, "area_um2": 910000,
                  "slack_ps": 300}, ...]
    }
    """
    with open(path) as f:
        return json.load(f)


def shape(macro, tech, margins):
    """Pin side length, outline and channel for one macro, in um.

    The pins set a minimum for their side; the block is never deeper than
    it is wide for that alone (a square when the pins fit on its side with
    room to spare), and never deeper than the aspect cap allows. When even
    the cap cannot give the pins one side, they go on two adjacent sides.
    """
    pins = macro["pins"]
    area = macro["area_um2"]
    need = pins * tech["pin_pitch_um"] * margins["pin_side"] / tech["pin_layers"]
    square = math.sqrt(area)
    two_sides = False
    if need > square * math.sqrt(margins["aspect_cap"]):
        need = need / 2.0
        two_sides = True
    side = max(need, square)
    depth = area / side
    channel = max(
        margins["channel_min_um"],
        pins / tech["track_density_per_um"] * margins["lateral"],
    )
    return {
        "name": macro["name"],
        "pins": pins,
        "area_um2": area,
        "pin_side_um": round(side, 3),
        "depth_um": round(depth, 3),
        "two_sides": two_sides,
        "channel_um": round(channel, 3),
        "pins_per_um": round(pins / (side * (2 if two_sides else 1)), 3),
    }


def _die_for(placed, region_area, extents, gap, margin):
    """Die width and height for one assignment of macros to sides."""
    need_w = max(_span(placed["bottom"], gap), _span(placed["top"], gap))
    need_h = max(_span(placed["left"], gap), _span(placed["right"], gap))
    w = max(need_w, math.sqrt(region_area))
    h = max(need_h, region_area / w)
    w = max(need_w, region_area / h)
    die_w = w + extents["left"] + extents["right"] + 2 * margin
    die_h = h + extents["bottom"] + extents["top"] + 2 * margin
    return w, h, die_w, die_h


def _span(items, gap):
    return sum(s["pin_side_um"] for s in items) + gap * max(0, len(items) - 1)


def _extents(placed):
    return {
        s: max([m["channel_um"] + m["depth_um"] for m in placed[s]] or [0.0])
        for s in SIDES
    }


def assign_sides(shapes, region_area, gap, margin):
    """Macros to the region's sides so the die is smallest.

    Every assignment is tried for up to eight macros (65536 cases), the
    region rectangle sized to hold the cells and the pin sides along it;
    beyond eight, longest first onto the least loaded side. Returns
    ({side: [shapes]}, region_w, region_h).
    """
    if not shapes:
        w = math.sqrt(region_area)
        return {s: [] for s in SIDES}, w, w
    best = None
    if len(shapes) <= 8:
        n = len(shapes)
        for code in range(4**n):
            placed = {s: [] for s in SIDES}
            c = code
            for sh in shapes:
                placed[SIDES[c % 4]].append(sh)
                c //= 4
            w, h, dw, dh = _die_for(placed, region_area, _extents(placed), gap, margin)
            if best is None or dw * dh < best[0]:
                best = (dw * dh, placed, w, h)
    else:
        placed = {s: [] for s in SIDES}
        for sh in sorted(shapes, key=lambda s: -s["pin_side_um"]):
            side = min(SIDES, key=lambda s: _span(placed[s], gap))
            placed[side].append(sh)
        w, h, dw, dh = _die_for(placed, region_area, _extents(placed), gap, margin)
        best = (dw * dh, placed, w, h)
    return best[1], best[2], best[3]


def layout(plan):
    tech = plan["tech"]
    margins = plan["margins"]
    parent = plan["parent"]
    gap = margins["gap_um"]
    shapes = [shape(m, tech, margins) for m in plan["macros"]]
    region_area = parent["cell_area_um2"] / parent["density"]
    placed, region_w, region_h = assign_sides(
        shapes, region_area, gap, parent["core_margin_um"]
    )
    extent = _extents(placed)
    margin = parent["core_margin_um"]
    x0 = margin + extent["left"]
    y0 = margin + extent["bottom"]
    region_box = (x0, y0, x0 + region_w, y0 + region_h)
    macros = []
    for side in SIDES:
        items = placed[side]
        along = region_w if side in ("bottom", "top") else region_h
        start = (along - _span(items, gap)) / 2.0  # centred along the side
        for sh in items:
            s, d, w = sh["pin_side_um"], sh["depth_um"], sh["channel_um"]
            if side == "bottom":
                x, y, wdt, hgt = x0 + start, y0 - w - d, s, d
            elif side == "top":
                x, y, wdt, hgt = x0 + start, y0 + region_h + w, s, d
            elif side == "left":
                x, y, wdt, hgt = x0 - w - d, y0 + start, d, s
            else:
                x, y, wdt, hgt = x0 + region_w + w, y0 + start, d, s
            m = dict(sh)
            m.update(
                {
                    "region_side": side,
                    "pin_side": FACING[side],
                    "x_um": round(x, 3),
                    "y_um": round(y, 3),
                    "w_um": round(wdt, 3),
                    "h_um": round(hgt, 3),
                    "orient": "R0",
                }
            )
            # wire the crossing has to add: the channel and half the region
            wire = w + (region_w if side in ("left", "right") else region_h) / 2.0
            m["wire_um"] = round(wire, 1)
            m["wire_ps"] = round(wire * tech["wire_ps_per_um"], 1)
            if "slack_ps" in sh or "slack_ps" in plan_macro(plan, sh["name"]):
                slack = plan_macro(plan, sh["name"]).get("slack_ps")
                if slack is not None:
                    m["slack_after_wire_ps"] = round(slack - m["wire_ps"], 1)
                    m["timing_ok"] = m["slack_after_wire_ps"] >= 0
            macros.append(m)
            start += s + gap
    die_w = x0 + region_w + extent["right"] + margin
    die_h = y0 + region_h + extent["top"] + margin
    macro_area = sum(m["area_um2"] for m in macros)
    return {
        "region_um": [round(v, 3) for v in region_box],
        "die_um": [0.0, 0.0, round(die_w, 3), round(die_h, 3)],
        "core_margin_um": margin,
        "macros": macros,
        "macro_area_mm2": round(macro_area / 1e6, 4),
        "cell_area_mm2": round(parent["cell_area_um2"] / 1e6, 4),
        "die_area_mm2": round(die_w * die_h / 1e6, 4),
        "utilisation": round(
            (macro_area + parent["cell_area_um2"]) / (die_w * die_h), 3
        ),
        "timing_failures": [m["name"] for m in macros if m.get("timing_ok") is False],
    }


def plan_macro(plan, name):
    for m in plan["macros"]:
        if m["name"] == name:
            return m
    return {}


def check(out):
    """No two macros overlap and none leaves the die."""
    problems = []
    x0, y0, x1, y1 = out["die_um"]
    boxes = [
        (m["name"], m["x_um"], m["y_um"], m["x_um"] + m["w_um"], m["y_um"] + m["h_um"])
        for m in out["macros"]
    ]
    for n, a, b, c, d in boxes:
        if a < x0 or b < y0 or c > x1 or d > y1:
            problems.append("{} outside die".format(n))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            _, a, b, c, d = boxes[i]
            _, e, f, g, h = boxes[j]
            if a < g and e < c and b < h and f < d:
                problems.append("{} overlaps {}".format(boxes[i][0], boxes[j][0]))
    return problems


def summary(out):
    lines = [
        "die {:.0f} x {:.0f} um, region {:.0f} x {:.0f} um, utilisation {:.0%} (macros {:.2f} mm2, cells {:.2f} mm2)".format(
            out["die_um"][2],
            out["die_um"][3],
            out["region_um"][2] - out["region_um"][0],
            out["region_um"][3] - out["region_um"][1],
            out["utilisation"],
            out["macro_area_mm2"],
            out["cell_area_mm2"],
        ),
        "{:<20} {:>6} {:>8} {:>8} {:>7} {:>6} {:>8} {:>8} {}".format(
            "macro",
            "pins",
            "side um",
            "depth um",
            "chan um",
            "pin/um",
            "wire ps",
            "slack",
            "on",
        ),
    ]
    for m in out["macros"]:
        lines.append(
            "{:<20} {:>6} {:>8.0f} {:>8.0f} {:>7.0f} {:>6.2f} {:>8.0f} {:>8} {} {}{}".format(
                m["name"],
                m["pins"],
                m["pin_side_um"],
                m["depth_um"],
                m["channel_um"],
                m["pins_per_um"],
                m["wire_ps"],
                m.get("slack_after_wire_ps", "-"),
                m["region_side"],
                "pins " + m["pin_side"],
                " (two sides)" if m["two_sides"] else "",
            )
        )
    if out["timing_failures"]:
        lines.append(
            "timing: the cut is wrong for this geometry at "
            + ", ".join(out["timing_failures"])
        )
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("plan")
    ap.add_argument("--out", help="JSON of the result")
    a = ap.parse_args(argv[1:])
    plan = load_plan(a.plan)
    out = layout(plan)
    problems = check(out)
    print(summary(out))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1, sort_keys=True)
    for p in problems:
        print("plan_floorplan: " + p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
