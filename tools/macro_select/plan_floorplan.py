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
When the tech names the pin layers' origin lattice (asap7 with pins on M2
to M5: 0.144 by 2.16 um), every outline is rounded up to it and every
macro origin snapped to it, so the blocks' tracks are the parent's.

--emit DIR writes what the flows consume: per block <name>_pins.tcl (an
IO_CONSTRAINTS script putting every signal pin on the planned side; with
a pin-partner dump in the plan, the side is split into one segment per
partner, ordered by where the partner sits, so both ends of an
interface face each other: pin placement is a compromise between two
blocks and belongs to the parent's plan),
place_macros.tcl for the parent (place_macro -exact per block, found by
master name) and plan.bzl, a Starlark dict of DIE_AREA/CORE_AREA per
block and for the parent, with each block's pin side and keep list.

Stdlib only; python 3.6.
"""

import argparse
import json
import os
import re
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
               "site_um": 0.054, "row_um": 0.27,
               "lattice_x_um": 0.144, "lattice_y_um": 2.16,
               "pin_layers_v": [{"name": "M3", "pitch": 0.036, "offset": 0.009, "width": 0.018},
                                {"name": "M5", "pitch": 0.048, "offset": 0.012, "width": 0.024}],
               "pin_layers_h": [{"name": "M4", "pitch": 0.048, "offset": 0.012, "width": 0.024}]},
      "parent": {"cell_area_um2": 220000, "density": 0.5,
                 "core_margin_um": 10, "keep": ["Backend", "Frontend"]},
      "margins": {"pin_side": 1.5, "channel_min_um": 40,
                  "lateral": 0.5, "aspect_cap": 3.0, "gap_um": 10.8},
      "macros": [{"name": "Frontend", "pins": 3294, "area_um2": 910000,
                  "slack_ps": 300, "keep": ["Bpu", "Ftq"]}, ...],
      "pin_partners": "pin_partners.txt",
      "netlists": [{"module": "RobEntryFile",
                    "instance": "backend/inner_ctrlBlock/rob/robEntryFile",
                    "w_um": 318.4, "h_um": 192.5}, ...]
    }

    netlists (optional) are the generated arrays dropped FIRM into the
    parent (STRUCTURED_MEMORIES in mode netlist): the planner lays them
    in a row along the top of the logic region, left to right, a gap
    apart, and emits their corners as netlists.txt for
    STRUCTURED_PLACEMENT; an entry may fix its own x_um and y_um instead.

    pin_partners (optional) is probe_pin_partners.tcl's dump, one
    "pin <block> <pin> <partner>" line per block pin, partner a block
    name, "logic" (the parent's own cells), "port" (a top-level pin) or
    "unconnected". Pins to ports and unconnected pins go on the block's
    outer side, the one facing the die boundary, out of the region's way;
    everything else shares the pin side in partner segments.

    pin_layers_v (for pins on the top and bottom edges) and pin_layers_h
    (left and right) are the layers the plan places pins on, with their
    track pitch and offset in the block's frame and their wire width;
    with them the plan places every partner pin at an exact track
    coordinate (place_pin, FIRM, which the flow's pin placer then leaves
    alone) instead of handing the placer an interval. Without them the
    segments are emitted as interval constraints.
    lattice_*_um and the keep lists are optional; the parent's keep list is
    the modules its own synthesis keeps after the blocks are hardened
    (keep_under.py --outside). core_margin_um is also the block flows'
    core margin. A relative pin_partners path is relative to the plan's
    own directory, so a plan and its dump can be kept side by side.
    """
    with open(path) as f:
        plan = json.load(f)
    partners = plan.get("pin_partners")
    if partners and not os.path.isabs(partners):
        plan["pin_partners"] = os.path.join(os.path.dirname(os.path.abspath(path)), partners)
    return plan


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
    lx, ly = tech.get("lattice_x_um"), tech.get("lattice_y_um")
    if lx and ly:
        # the outline's width and height in the block's own frame: the pin
        # side is a horizontal edge (top or bottom) when the block sits
        # above or below the region, a vertical one otherwise; both are
        # rounded to the coarser period so either placement is legal
        period = max(lx, ly)
        side = math.ceil(side / period) * period
        depth = math.ceil(depth / period) * period
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


def _die_for(placed, region_area, extents, gap, margin, min_w=0.0, min_h=0.0):
    """Die width and height for one assignment of macros to sides.

    min_w and min_h are what the region must hold besides its cells: the
    placed netlists' row (netlist_row)."""
    need_w = max(_span(placed["bottom"], gap), _span(placed["top"], gap), min_w)
    need_h = max(_span(placed["left"], gap), _span(placed["right"], gap), min_h)
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


def assign_sides(shapes, region_area, gap, margin, min_w=0.0, min_h=0.0):
    """Macros to the region's sides so the die is smallest.

    Every assignment is tried for up to eight macros (65536 cases), the
    region rectangle sized to hold the cells and the pin sides along it;
    beyond eight, longest first onto the least loaded side. Returns
    ({side: [shapes]}, region_w, region_h).
    """
    if not shapes:
        w = max(math.sqrt(region_area), min_w)
        return {s: [] for s in SIDES}, w, max(region_area / w, min_h)
    best = None
    if len(shapes) <= 8:
        n = len(shapes)
        for code in range(4**n):
            placed = {s: [] for s in SIDES}
            c = code
            for sh in shapes:
                placed[SIDES[c % 4]].append(sh)
                c //= 4
            w, h, dw, dh = _die_for(placed, region_area, _extents(placed), gap, margin, min_w, min_h)
            if best is None or dw * dh < best[0]:
                best = (dw * dh, placed, w, h)
    else:
        placed = {s: [] for s in SIDES}
        for sh in sorted(shapes, key=lambda s: -s["pin_side_um"]):
            side = min(SIDES, key=lambda s: _span(placed[s], gap))
            placed[side].append(sh)
        w, h, dw, dh = _die_for(placed, region_area, _extents(placed), gap, margin, min_w, min_h)
        best = (dw * dh, placed, w, h)
    return best[1], best[2], best[3]


def layout(plan):
    tech = plan["tech"]
    margins = plan["margins"]
    parent = plan["parent"]
    gap = margins["gap_um"]
    shapes = [shape(m, tech, margins) for m in plan["macros"]]
    region_area = parent["cell_area_um2"] / parent["density"]
    min_w, min_h = netlist_row(plan)
    placed, region_w, region_h = assign_sides(
        shapes, region_area, gap, parent["core_margin_um"], min_w, min_h
    )
    extent = _extents(placed)
    margin = parent["core_margin_um"]
    # a strip of rows between a block row and the die edge: the parent's
    # port buffers need sites next to the ports on that edge, and the rows
    # of the blocks' band are removed (block_bands); without the strip the
    # legaliser's nearest-site search walks a millimetre per buffer
    # (XiangShan take 24: 4 309 buffers, initialSnap never finished)
    strip = plan["margins"].get("port_strip_um", PORT_STRIP_UM)
    for side in ("bottom", "top", "left", "right"):
        if placed[side]:
            extent[side] += strip
    # the flow snaps the core's corners onto the site and row grid, inward;
    # one lattice period of clearance keeps every macro inside it
    cx = margin + tech.get("lattice_x_um", tech.get("site_um", 0.0))
    cy = margin + tech.get("lattice_y_um", tech.get("row_um", 0.0))
    x0 = cx + extent["left"]
    y0 = cy + extent["bottom"]
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
            x, y = _snap(x, y, tech)
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
    die_w = x0 + region_w + extent["right"] + cx
    die_h = y0 + region_h + extent["top"] + cy
    for m in macros:  # a snapped origin may have moved a macro outward
        die_w = max(die_w, m["x_um"] + m["w_um"] + cx)
        die_h = max(die_h, m["y_um"] + m["h_um"] + cy)
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


def _snap(x, y, tech):
    """The origin up to the next lattice point, when the tech has one."""
    lx, ly = tech.get("lattice_x_um"), tech.get("lattice_y_um")
    if not (lx and ly):
        return x, y
    return math.ceil(x / lx - 1e-9) * lx, math.ceil(y / ly - 1e-9) * ly


def plan_macro(plan, name):
    for m in plan["macros"]:
        if m["name"] == name:
            return m
    return {}


def check(out, site_um=0.054, row_um=0.27):
    """No two macros overlap and none leaves the core the flow snaps to
    (corners moved inward onto the site and row grid)."""
    problems = []
    dx0, dy0, dx1, dy1 = out["die_um"]
    m = out["core_margin_um"]
    x0 = math.ceil((dx0 + m) / site_um - 1e-9) * site_um
    y0 = math.ceil((dy0 + m) / row_um - 1e-9) * row_um
    x1 = math.floor((dx1 - m) / site_um + 1e-9) * site_um
    y1 = math.floor((dy1 - m) / row_um + 1e-9) * row_um
    boxes = [
        (m["name"], m["x_um"], m["y_um"], m["x_um"] + m["w_um"], m["y_um"] + m["h_um"])
        for m in out["macros"]
    ]
    for n, a, b, c, d in boxes:
        if a < x0 - 1e-6 or b < y0 - 1e-6 or c > x1 + 1e-6 or d > y1 + 1e-6:
            problems.append("{} outside the snapped core".format(n))
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


def read_partners(path):
    """{block: {partner: [pin names]}} from probe_pin_partners.tcl's dump.

    When the dump names the pin at the other end (its fifth column), the
    two ends of a block-to-block interface are ordered as one sequence:
    the block whose name sorts first keeps its pins in name order, and
    the other's are ordered by the partner pin they connect to, so the
    parent's wires between the two runs do not cross. Older four-column
    dumps give name order on both ends.
    """
    out = {}
    other_end = {}
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 4 and p[0] == "pin" and p[2] not in ("VDD", "VSS"):
                out.setdefault(p[1], {}).setdefault(p[3], []).append(p[2])
                if len(p) >= 5 and p[4] != "-":
                    other_end[(p[1], p[2])] = p[4]
    for block, groups in out.items():
        for partner, pins in groups.items():
            if partner in out and partner != block:
                lead, follow = sorted([block, partner])
                if block == lead:
                    pins.sort()
                else:
                    lead_pins = sorted(out[partner].get(block, []))
                    rank = {name: i for i, name in enumerate(lead_pins)}
                    pins.sort(
                        key=lambda n: (
                            rank.get(other_end.get((block, n), ""), len(rank)),
                            n,
                        )
                    )
            else:
                pins.sort()
    return out


def _anchor(m, partner, by_name, out):
    """Where a partner sits, along the axis of m's pin side, in parent um."""
    horizontal = m["pin_side"] in ("top", "bottom")
    x0, y0, x1, y1 = out["region_um"]
    dx0, dy0, dx1, dy1 = out["die_um"]
    if partner in by_name:
        q = by_name[partner]
        cx, cy = q["x_um"] + q["w_um"] / 2.0, q["y_um"] + q["h_um"] / 2.0
    elif partner == "port":
        # the die edge nearest along the axis: ports sit on the boundary
        cx = dx0 if m["x_um"] + m["w_um"] / 2.0 < (dx0 + dx1) / 2.0 else dx1
        cy = dy0 if m["y_um"] + m["h_um"] / 2.0 < (dy0 + dy1) / 2.0 else dy1
    else:  # logic, unconnected: the region
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return cx if horizontal else cy


# the side of the block facing away from the region: where its pins to
# the parent's ports and its unconnected pins go
OUTER = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
OUTER_PARTNERS = ("port", "unconnected")


def fold_partners(groups, planned, me):
    """Partners that are not planned macros (the parent's own memory
    macros and generated arrays, the clock's macro pins) are the parent's
    logic for the pin side's purposes: one group, not a segment per SRAM."""
    out = {}
    for partner, pins in groups.items():
        key = partner
        if partner not in planned and partner not in OUTER_PARTNERS and partner != me:
            key = "logic"
        out.setdefault(key, []).extend(pins)
    for pins in out.values():
        pins.sort()
    return out


def split_groups(groups):
    """({partner: pins} for the pin side, {partner: pins} for the outer side)."""
    inner = {k: v for k, v in groups.items() if k not in OUTER_PARTNERS}
    outer = {k: v for k, v in groups.items() if k in OUTER_PARTNERS}
    return inner, outer


# The pin placer keeps pins this far from a block's corners; a segment
# that reaches into the corner has no slots there (PPL-0107 on Region_1,
# whose 24 self-connected pins were given the last 3 um of the side).
SEGMENT_EDGE_UM = 5.0

# rows kept between a block row and the die edge, for the port buffers
PORT_STRIP_UM = 20.0


def pin_segments(m, groups, out, edge_um=SEGMENT_EDGE_UM):
    """[(partner, lo_um, hi_um, pins)] along m's pin side in the block's
    own frame, partners ordered by where they sit, lengths by pin count,
    the whole run kept edge_um clear of both corners."""
    by_name = {q["name"]: q for q in out["macros"]}
    horizontal = m["pin_side"] in ("top", "bottom")
    length = m["w_um"] if horizontal else m["h_um"]
    usable = max(length - 2 * edge_um, 1.0)
    total = float(sum(len(v) for v in groups.values())) or 1.0
    ordered = sorted(groups.items(), key=lambda kv: _anchor(m, kv[0], by_name, out))
    segs = []
    pos = edge_um
    for partner, pins in ordered:
        seg = usable * len(pins) / total
        segs.append(
            (partner, round(pos, 3), round(min(pos + seg, length - edge_um), 3), pins)
        )
        pos += seg
    return segs


PINS_TCL = """# Generated by plan_floorplan.py: every signal pin of {name} on its {side}
# side, the side that faces the parent's logic region when the parent
# places the block R0 on the region's {region_side}.
set names {{}}
foreach bterm [[ord::get_db_block] getBTerms] {{
  if {{ [$bterm getSigType] ne "SIGNAL" && [$bterm getSigType] ne "CLOCK" }} {{ continue }}
  lappend names [$bterm getName]
}}
{constraint}
puts "{name}_pins.tcl: [llength $names] pins on {sides}"
"""

ONE_SIDE = "set_io_pin_constraint -region {side}:* -pin_names $names"

SEGMENTS_TCL = """# Generated by plan_floorplan.py: every signal pin of {name} on its {side}
# side, in one segment per partner block, ordered by where the partner
# sits in the parent's plan (pin_partners: probe_pin_partners.tcl).
set names {{}}
foreach bterm [[ord::get_db_block] getBTerms] {{
  if {{ [$bterm getSigType] ne "SIGNAL" && [$bterm getSigType] ne "CLOCK" }} {{ continue }}
  lappend names [$bterm getName]
}}
set placed {{}}
{segments}
# whatever the dump did not name stays on the same side
set rest {{}}
foreach n $names {{ if {{ [lsearch -exact $placed $n] < 0 }} {{ lappend rest $n }} }}
if {{ [llength $rest] > 0 }} {{ set_io_pin_constraint -region {side}:* -pin_names $rest }}
puts "{name}_pins.tcl: [llength $placed] pins in {count} partner segments ({side} side, ports and unconnected on the outer side), [llength $rest] free on the {side} side"
"""

SEGMENT_TCL = """# {partner}: {n} pins on {side} at {region} um
set seg [lmap n {{{pins}}} {{ expr {{ [lsearch -exact $names $n] >= 0 ? $n : [continue] }} }}]
if {{ [llength $seg] > 0 }} {{
  set_io_pin_constraint -region {side}:{region} -pin_names $seg
  set placed [concat $placed $seg]
}}"""
TWO_SIDES = """set half [expr {{ [llength $names] / 2 }}]
set_io_pin_constraint -region {side}:* -pin_names [lrange $names 0 [expr {{ $half - 1 }}]]
set_io_pin_constraint -region {other}:* -pin_names [lrange $names $half end]"""

# the second side of a two-sided block: adjacent, clockwise from the first
NEXT_SIDE = {"top": "right", "right": "bottom", "bottom": "left", "left": "top"}


def place_exact(m, segs, tech):
    """[(pin, layer, x_um, y_um, w_um, h_um)] for every pin of every
    segment of m, pins alternating over the edge's layers, each on its
    layer's track nearest the pin's share of the segment, never closer on
    one layer than two tracks. Refuses a segment its pins do not fit."""
    side = m["pin_side"]
    horizontal_edge = side in ("top", "bottom")
    layers = tech["pin_layers_v" if horizontal_edge else "pin_layers_h"]
    length = m["w_um"] if horizontal_edge else m["h_um"]
    pin_len = 0.36
    out = []
    for partner, lo, hi, pins in segs:
        if lo is None:  # a whole side
            lo, hi = SEGMENT_EDGE_UM, length - SEGMENT_EDGE_UM
        n = len(pins)
        if n == 0:
            continue
        # capacity: each layer takes every len(layers)-th pin at two tracks
        for k, lay in enumerate(layers):
            share = len(pins[k :: len(layers)])
            if share * 2 * lay["pitch"] > (hi - lo) + 1e-6:
                raise SystemExit(
                    "plan_floorplan: %s: %d pins of partner %s do not fit %.1f um on %s "
                    "(%d on %s need %.1f um at two tracks); a wider side or a different cut"
                    % (
                        m["name"],
                        n,
                        partner,
                        hi - lo,
                        side,
                        share,
                        lay["name"],
                        share * 2 * lay["pitch"],
                    )
                )
        last = {lay["name"]: -1e9 for lay in layers}
        for i, pin in enumerate(pins):
            lay = layers[i % len(layers)]
            want = lo + (i + 0.5) * (hi - lo) / n
            k = math.floor((want - lay["offset"]) / lay["pitch"] + 0.5)
            x = lay["offset"] + k * lay["pitch"]
            if x < last[lay["name"]] + 2 * lay["pitch"] - 1e-9:
                x = last[lay["name"]] + 2 * lay["pitch"]
            last[lay["name"]] = x
            w = 2 * lay["width"]
            if horizontal_edge:
                y = m["h_um"] - pin_len / 2.0 if side == "top" else pin_len / 2.0
                out.append(
                    (pin, lay["name"], round(x, 4), round(y, 4), round(w, 4), pin_len)
                )
            else:
                xx = m["w_um"] - pin_len / 2.0 if side == "right" else pin_len / 2.0
                out.append(
                    (pin, lay["name"], round(xx, 4), round(x, 4), pin_len, round(w, 4))
                )
    return out


EXACT_TCL = """# Generated by plan_floorplan.py: every partner pin of {name} at an exact
# track coordinate on its {side} side, in one run per partner block ordered
# by where the partner sits in the parent's plan (pin_partners:
# probe_pin_partners.tcl), alternating {layers}; FIRM, so place_pins
# leaves them and places only what the dump did not name, on the same side.
set names {{}}
foreach bterm [[ord::get_db_block] getBTerms] {{
  if {{ [$bterm getSigType] ne "SIGNAL" && [$bterm getSigType] ne "CLOCK" }} {{ continue }}
  lappend names [$bterm getName]
}}
set placed {{}}
foreach {{pin layer x y w h}} {{
{rows}
}} {{
  if {{ [lsearch -exact $names $pin] < 0 }} {{ continue }}
  place_pin -pin_name $pin -layer $layer -location [list $x $y] -pin_size [list $w $h] -force_to_die_boundary
  lappend placed $pin
}}
set rest {{}}
foreach n $names {{ if {{ [lsearch -exact $placed $n] < 0 }} {{ lappend rest $n }} }}
if {{ [llength $rest] > 0 }} {{ set_io_pin_constraint -region {side}:* -pin_names $rest }}
puts "{name}_pins.tcl: [llength $placed] pins placed by the plan on {sides}, [llength $rest] left to place_pins on {side}"
"""

PLACE_TCL = """# Generated by plan_floorplan.py: the planned floorplan, each block found
# by its master and placed R0 with -exact (mpl's snapper would move the
# origin off the pin lattice the plan put it on).
set block [ord::get_db_block]
foreach {{master x y}} {{
{rows}
}} {{
  set insts {{}}
  foreach inst [$block getInsts] {{
    if {{ [[$inst getMaster] getName] eq $master }} {{ lappend insts $inst }}
  }}
  if {{ [llength $insts] != 1 }} {{
    utl::error FLW 1 "plan: $master has [llength $insts] instances, the plan places one"
  }}
  place_macro -macro_name [[lindex $insts 0] getName] -location [list $x $y] -orientation R0 -exact
  [lindex $insts 0] setPlacementStatus FIRM
  puts "place_macros.tcl: $master at $x $y um, R0"
}}
# The band the blocks occupy is the blocks' and the wires': a soft
# placement blockage over it, from the lowest block bottom to the lowest
# block top of the row (mirrored for a top row). Global placement blocks
# the sites of every blockage, soft or not, so no parent cell is seeded in
# a pocket under a shorter block or in a channel between two, where its
# wires would have to leave through the channel (XiangShan take 23: 7
# percent of the route-0 overflow). The detailed placer skips soft
# blockages (dbToOpendp.cpp), so the rows stay legal underneath, and the
# few hundred buffers repair_design puts there afterwards -- it respects
# neither rows nor blockages -- have a site under them. A hard blockage,
# or removing the rows, strands those buffers instead: the negotiation
# legaliser's initialSnap then relocates each by an expanding ring search
# whose cost grows with the distance, and the stage does not return
# (inventory entry 21).
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set core [$block getCoreArea]
set bands 0
foreach {{lo hi}} {{
{bands}
}} {{
  set bl [odb::dbBlockage_create $block [$core xMin] [expr {{ int($lo * $dbu) }}] [$core xMax] [expr {{ int($hi * $dbu) }}]]
  $bl setSoft
  incr bands
}}
puts "place_macros.tcl: $bands soft placement blockage(s) over the blocks' bands; the rows stay"
# Macros the plan does not name (the parent's own generated register files
# and memories) go around the planned blocks, which are FIRM and stay put.
set rest {{}}
foreach inst [$block getInsts] {{
  if {{ [[$inst getMaster] isBlock] && ![$inst isFixed] }} {{ lappend rest [$inst getName] }}
}}
if {{ [llength $rest] > 0 }} {{
  puts "place_macros.tcl: [llength $rest] macros not in the plan; rtl_macro_placer places them around the planned blocks"
  rtl_macro_placer -halo_width 2 -halo_height 2
}}
"""


def netlist_row(plan):
    """(width, height) of the row place_netlists lays along the region's
    top: the region has to be at least that wide and that tall, whatever
    its cell area alone would make it. Netlists with a fixed corner are
    not in the row."""
    gap = plan["margins"]["gap_um"]
    row = [n for n in plan.get("netlists") or [] if not ("x_um" in n and "y_um" in n)]
    if not row:
        return 0.0, 0.0
    return (
        gap * (len(row) + 1) + sum(n["w_um"] for n in row),
        2 * gap + max(n["h_um"] for n in row),
    )


def place_netlists(out, plan):
    """[(module, instance, x_um, y_um, w_um, h_um)]: the parent's placed
    netlists in a row along the top of the logic region, left to right,
    gap_um apart, unless an entry fixes its corner. The region is where
    the parent's logic goes and the arrays are that logic's densest
    part; the top of it keeps them off the blocks' pin sides."""
    items = plan.get("netlists") or []
    if not items:
        return []
    gap = plan["margins"]["gap_um"]
    x0, y0, x1, y1 = out["region_um"]
    x = x0 + gap
    rows = []
    for n in items:
        w, h = n["w_um"], n["h_um"]
        if "x_um" in n and "y_um" in n:
            rows.append(
                (
                    n["module"],
                    n["instance"],
                    round(n["x_um"], 3),
                    round(n["y_um"], 3),
                    w,
                    h,
                )
            )
            continue
        if x + w > x1 - gap + 1e-6:
            raise SystemExit(
                "plan_floorplan: the netlists do not fit in one row along the region's top "
                "(%s at x %.0f um, region %.0f wide); give %s its own x_um and y_um"
                % (n["module"], x, x1 - x0, n["module"])
            )
        y = y1 - gap - h
        rows.append((n["module"], n["instance"], round(x, 3), round(y, 3), w, h))
        x += w + gap
    return rows


def block_bands(out):
    """The y bands (lo hi, um) a row of blocks owns: from the lowest bottom
    to the lowest top of a bottom row, from the highest bottom to the
    highest top of a top row. place_macros.tcl puts a soft placement
    blockage over each; the port strip between the band and the die edge
    stays clear of it, for the parent's port buffers."""
    bands = []
    bottom = [m for m in out["macros"] if m["region_side"] == "bottom"]
    if bottom:
        bands.append(
            "  %.3f %.3f"
            % (
                min(m["y_um"] for m in bottom),
                min(m["y_um"] + m["h_um"] for m in bottom),
            )
        )
    top = [m for m in out["macros"] if m["region_side"] == "top"]
    if top:
        bands.append(
            "  %.3f %.3f"
            % (max(m["y_um"] for m in top), max(m["y_um"] + m["h_um"] for m in top))
        )
    return bands


def _area(x0, y0, x1, y1):
    return "{:.3f} {:.3f} {:.3f} {:.3f}".format(x0, y0, x1, y1)


def emit(out, plan, directory):
    """Write the flows' files into directory; returns the paths written."""
    import os

    margin = out["core_margin_um"]
    written = []

    def write(name, text):
        path = os.path.join(directory, name)
        with open(path, "w") as f:
            f.write(text)
        written.append(path)

    partners = {}
    if plan.get("pin_partners"):
        partners = read_partners(plan["pin_partners"])
    by_name_all = {q["name"] for q in out["macros"]}
    bzl = {"parent": {}, "macros": {}}
    dx, dy = out["die_um"][2], out["die_um"][3]
    bzl["parent"]["DIE_AREA"] = _area(0, 0, dx, dy)
    bzl["parent"]["CORE_AREA"] = _area(margin, margin, dx - margin, dy - margin)
    if plan["parent"].get("keep"):
        bzl["parent"]["SYNTH_KEEP_MODULES"] = " ".join(plan["parent"]["keep"])
    rows = []
    for m in out["macros"]:
        side = m["pin_side"]
        sides = side
        constraint = ONE_SIDE.format(side=side)
        if m["two_sides"]:
            other = NEXT_SIDE[side]
            sides = side + " and " + other
            constraint = TWO_SIDES.format(side=side, other=other)
        if m["name"] in partners and not m["two_sides"]:
            inner, outer = split_groups(
                fold_partners(partners[m["name"]], by_name_all, m["name"])
            )
            segs = [(side,) + s_ for s_ in pin_segments(m, inner, out)]
            if outer:
                # ports and unconnected pins on the outer side, whole side
                segs += [
                    (OUTER[side], partner, None, None, pins)
                    for partner, pins in sorted(outer.items())
                ]
            tech = plan["tech"]
            if "pin_layers_v" in tech and "pin_layers_h" in tech:
                pin_rows = []
                sides_used = []
                for sd in (side, OUTER[side]):
                    on_side = [
                        (p_, lo, hi, pins)
                        for sd_, p_, lo, hi, pins in segs
                        if sd_ == sd
                    ]
                    if not on_side:
                        continue
                    sides_used.append(sd)
                    mm = dict(m, pin_side=sd)
                    for pin, layer, x, y, w, h in place_exact(mm, on_side, tech):
                        pin_rows.append(
                            "  {} {} {:.4f} {:.4f} {:.4f} {:.4f}".format(
                                pin, layer, x, y, w, h
                            )
                        )
                text = EXACT_TCL.format(
                    name=m["name"],
                    side=side,
                    sides=" and ".join(sides_used),
                    layers="/".join(
                        l_["name"]
                        for l_ in tech[
                            (
                                "pin_layers_v"
                                if side in ("top", "bottom")
                                else "pin_layers_h"
                            )
                        ]
                    ),
                    rows="\n".join(pin_rows),
                )
                m["pin_segments"] = [
                    {
                        "side": sd,
                        "partner": p_,
                        "lo_um": lo,
                        "hi_um": hi,
                        "pins": len(pins),
                    }
                    for sd, p_, lo, hi, pins in segs
                ]
                m["pins_placed_exact"] = len(pin_rows)
                write(m["name"] + "_pins.tcl", text)
                # the block's entry and its place_macros row follow below,
                # like every other block's: this branch only chose its pins file
                text = None
            else:
                text = SEGMENTS_TCL.format(
                    name=m["name"],
                    side=side,
                    count=len(segs),
                    segments="\n".join(
                        SEGMENT_TCL.format(
                            partner=partner,
                            n=len(pins),
                            side=sd,
                            region=(
                                "*" if lo is None else "{:.3f}-{:.3f}".format(lo, hi)
                            ),
                            pins=" ".join(pins),
                        )
                        for sd, partner, lo, hi, pins in segs
                    ),
                )
                m["pin_segments"] = [
                    {
                        "side": sd,
                        "partner": p_,
                        "lo_um": lo,
                        "hi_um": hi,
                        "pins": len(pins),
                    }
                    for sd, p_, lo, hi, pins in segs
                ]
        else:
            text = PINS_TCL.format(
                name=m["name"],
                side=side,
                sides=sides,
                region_side=m["region_side"],
                constraint=constraint,
            )
        if text is not None:
            write(m["name"] + "_pins.tcl", text)
        w, h = m["w_um"], m["h_um"]
        entry = {
            "DIE_AREA": _area(0, 0, w, h),
            "CORE_AREA": _area(margin, margin, w - margin, h - margin),
            "pin_side": side,
            "x_um": m["x_um"],
            "y_um": m["y_um"],
        }
        keep = plan_macro(plan, m["name"]).get("keep")
        if keep:
            entry["SYNTH_KEEP_MODULES"] = " ".join(keep)
        bzl["macros"][m["name"]] = entry
        rows.append("  {} {:.3f} {:.3f}".format(m["name"], m["x_um"], m["y_um"]))
    write(
        "place_macros.tcl",
        PLACE_TCL.format(rows="\n".join(rows), bands="\n".join(block_bands(out))),
    )
    netlists = place_netlists(out, plan)
    if netlists:
        write(
            "netlists.txt",
            "# Generated by plan_floorplan.py: STRUCTURED_PLACEMENT, the parent's\n"
            "# placed netlists' lower-left corners in um: <module> <instance> <x> <y>\n"
            + "".join(
                "{} {} {:.3f} {:.3f}\n".format(m_, i_, x, y)
                for m_, i_, x, y, w, h in netlists
            ),
        )
        bzl["parent"]["netlists"] = [
            {"module": m_, "instance": i_, "x_um": x, "y_um": y, "w_um": w, "h_um": h}
            for m_, i_, x, y, w, h in netlists
        ]
        out["netlists"] = bzl["parent"]["netlists"]
    # buildifier wants a trailing comma on the last element of a multi-line
    # dict or list (a lookahead, so a closer that ends one element and
    # precedes another closer gets its comma too), so the emitted file is the file the linter leaves alone
    # and the drift tests compare bytes.
    starlark = re.sub(
        r"([^\[{,\s])(?=\n\s*[\]}])",
        r"\1,",
        json.dumps(bzl, indent=4, sort_keys=True),
    )
    write(
        "plan.bzl",
        '"""Generated by plan_floorplan.py from the macro selection tables; do not edit."""\n\n'
        "PLAN = " + starlark + "\n",
    )
    return written


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("plan")
    ap.add_argument("--out", help="JSON of the result")
    ap.add_argument(
        "--emit",
        metavar="DIR",
        help="write the flows' files (pin constraints, macro placement, plan.bzl)",
    )
    a = ap.parse_args(argv[1:])
    plan = load_plan(a.plan)
    out = layout(plan)
    problems = check(out)
    print(summary(out))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1, sort_keys=True)
    if a.emit and not problems:
        for path in emit(out, plan, a.emit):
            print("wrote " + path)
    for p in problems:
        print("plan_floorplan: " + p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
