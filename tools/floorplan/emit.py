#!/usr/bin/env python3
"""What the flows read from a feasible plan's floorplan.json.

  emit.py block <floorplan.json> <macro> --args <a.json> --pins <p.tcl>
          [--guidance <g.tcl>]
  emit.py parent <floorplan.json> --args <a.json> --place <p.tcl>

A block gets its outline (DIE_AREA, CORE_AREA at its flow's own core
margin) as an extra-arguments JSON for its floorplan stage, and an
IO_CONSTRAINTS script putting each planned bus on its side and range
(set_io_pin_constraint per bus; the block's own pin placer places the
bits); with --guidance, set_macro_guidance_region per hard object around
its rough place, for a block flow that sources it. The parent gets its
die and core, and a MACRO_PLACEMENT_TCL placing each block where the
plan put it, found by master name. An infeasible plan's floorplan.json is
{}: every command refuses it, naming the verdict to read.

Stdlib only.
"""

import argparse
import json
import sys

SIDE = {"N": "top", "S": "bottom", "E": "right", "W": "left"}


def load(path):
    with open(path) as f:
        fp = json.load(f)
    if not fp:
        raise SystemExit(
            "emit: %s is empty: the plan is infeasible, its verdict.md says where it stopped"
            % path
        )
    return fp


def fmt(v):
    return "%.3f" % v


def block_args(fp, macro, margin):
    w, h = fp["macros"][macro]["shape"]
    return {
        "DIE_AREA": " ".join(fmt(v) for v in (0, 0, w, h)),
        "CORE_AREA": " ".join(fmt(v) for v in (margin, margin, w - margin, h - margin)),
    }


def block_pins(fp, macro):
    lines = [
        "# The plan's pin sides and ranges, per bus (tools/floorplan/emit.py).",
        "proc floorplan_pins { bus } {",
        "  set names {}",
        "  foreach bt [[ord::get_db_block] getBTerms] {",
        "    set n [$bt getName]",
        '    if { $n eq $bus || [string match "$bus\\\\\\[*\\\\\\]" $n] } { lappend names $n }',
        "  }",
        "  return $names",
        "}",
    ]
    pins = fp["macros"][macro]["pins"]
    for side in sorted(pins):
        for p in pins[side]:
            lo, hi = p["range"]
            lines.append(
                "set_io_pin_constraint -region %s:%s-%s -pin_names [floorplan_pins {%s}]"
                % (SIDE[side], fmt(lo), fmt(hi), p["bus"])
            )
    return "\n".join(lines) + "\n"


def block_guidance(fp, macro, margin_um):
    rows = fp.get("internal_placement", {}).get(macro, [])
    lines = ["# The plan's rough place of each hard object (tools/floorplan/emit.py)."]
    for o in rows:
        x, y = o["place"]
        w, h = o["shape"]
        lines.append(
            "set_macro_guidance_region -macro_name {%s} -region {%s %s %s %s}"
            % (
                o["inst"].replace("\\", ""),
                fmt(max(0, x - margin_um)),
                fmt(max(0, y - margin_um)),
                fmt(x + w + margin_um),
                fmt(y + h + margin_um),
            )
        )
    return "\n".join(lines) + "\n"


def parent_args(fp):
    die = fp["die"]
    core = fp["core"]
    return {
        "DIE_AREA": " ".join(fmt(v) for v in (0, 0, die[0], die[1])),
        "CORE_AREA": " ".join(fmt(v) for v in core),
    }


def parent_place(fp):
    lines = [
        "# The plan's place of each block (tools/floorplan/emit.py), by master.",
        "set block [ord::get_db_block]",
    ]
    for m in sorted(fp["macros"]):
        mac = fp["macros"][m]
        x, y = mac["place"]
        lines += [
            "foreach inst [$block getInsts] {",
            "  if { [[$inst getMaster] getName] eq {%s} } {" % mac["block"],
            "    place_macro -macro_name [$inst getName] -location {%s %s} -orientation %s -exact"
            % (fmt(x), fmt(y), mac.get("orient", "R0")),
            "  }",
            "}",
        ]
    return "\n".join(lines) + "\n"


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("block")
    b.add_argument("floorplan")
    b.add_argument("macro")
    b.add_argument("--args", required=True)
    b.add_argument("--pins", required=True)
    b.add_argument("--guidance")
    b.add_argument("--core-margin-um", type=float, default=1.0)
    b.add_argument("--guidance-margin-um", type=float, default=5.0)
    p = sub.add_parser("parent")
    p.add_argument("floorplan")
    p.add_argument("--args", required=True)
    p.add_argument("--place", required=True)
    a = ap.parse_args(argv)
    fp = load(a.floorplan)
    if a.cmd == "block":
        if a.macro not in fp["macros"]:
            raise SystemExit(
                "emit: %s is not a macro of the plan (%s)"
                % (a.macro, ", ".join(sorted(fp["macros"])))
            )
        write(
            a.args,
            json.dumps(
                block_args(fp, a.macro, a.core_margin_um), indent=1, sort_keys=True
            )
            + "\n",
        )
        write(a.pins, block_pins(fp, a.macro))
        if a.guidance:
            write(a.guidance, block_guidance(fp, a.macro, a.guidance_margin_um))
    else:
        write(a.args, json.dumps(parent_args(fp), indent=1, sort_keys=True) + "\n")
        write(a.place, parent_place(fp))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
