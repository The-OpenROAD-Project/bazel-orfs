#!/usr/bin/env python3
"""A tile's pins by rule, from its ports: where every pin goes, before
anything is built.

  pin_plan.py --json DESIGN.json --module TILE --sides SIDES --w W --h H --out PLAN

SIDES is "west:a_in,clk east:a_out,clk_out north:... south:...": the
ports on each side, in order, bit 0 first. West and east are paired slot
by slot, and north and south: a pin and its partner sit at the same
offset along their edges, so abutted neighbours meet pin on pin. Each
side's slots are spread evenly along it, 1 um off the corners, and
snapped to asap7's tracks: north and south on M3 and M5 by turn, whose
tracks repeat every 0.144 um, the tiles' horizontal lattice; west and
east on M4, whose tracks repeat every 2.16 um, the vertical one. So a
tile placed on the lattice has its pins on the parent's tracks too.

The side "over" is the tile's top face: those pins are M8 rectangles
over its centre, one M8 track apart going up, for a net the level above
brings down from M9, a clock balanced at the top, say. A tile's M8 power
straps (test/abutment/pdn_macro.tcl) repeat every 2.16 um; the centre
of a tile whose height is a multiple of that lies between two pairs.

PLAN has one line per pin bit: name, side, layer, and the pin's
rectangle in the tile, x0 y0 x1 y1 in um. The tile places its pins from
it (test/abutment/pins_plan.tcl); a parent hardened as a macro places
each of its own opposite, mirrored across the shared edge
(io_notch.tcl). Neither waits for the other to be built.
"""

import argparse
import json
import sys

# asap7's make_tracks: offset, pitch and wire width, in um
TRACKS = {
    "M3": (0.009, 0.036, 0.018),
    "M4": (0.012, 0.048, 0.024),
    "M5": (0.012, 0.048, 0.024),
    "M8": (0.116, 0.080, 0.040),
}
LENGTH = 0.12
CORNER = 1.0
# an "over" pin's length along M8, room for vias from M9
OVER = 0.4


def snap(layer, v):
    off, pitch, _ = TRACKS[layer]
    return round(off + round((v - off) / pitch) * pitch, 3)


def bits(ports, names):
    out = []
    for name in names:
        if name not in ports:
            raise ValueError("no port %s" % name)
        n = len(ports[name]["bits"])
        out += [name] if n == 1 else ["%s[%d]" % (name, i) for i in range(n)]
    return out


def plan(ports, sides, w, h):
    lines = []
    for a, b, length, vertical in [
        ("west", "east", h, False),
        ("north", "south", w, True),
    ]:
        pa, pb = bits(ports, sides.get(a, [])), bits(ports, sides.get(b, []))
        n = max(len(pa), len(pb))
        if not n:
            continue
        step = (length - 2 * CORNER) / n
        used = {}
        for i in range(n):
            layer = ("M3", "M5")[i % 2] if vertical else "M4"
            at = snap(layer, CORNER + step * (i + 0.5))
            if (layer, at) in used:
                raise ValueError(
                    "%s/%s: slots %d and %d share a track; the side is too short"
                    % (a, b, used[(layer, at)], i)
                )
            used[(layer, at)] = i
            half = TRACKS[layer][2] / 2
            for side, pins in [(a, pa), (b, pb)]:
                if i >= len(pins):
                    continue
                if vertical:
                    y0, y1 = (0, LENGTH) if side == "south" else (h - LENGTH, h)
                    rect = (at - half, y0, at + half, y1)
                else:
                    x0, x1 = (0, LENGTH) if side == "west" else (w - LENGTH, w)
                    rect = (x0, at - half, x1, at + half)
                lines.append(line(pins[i], side, layer, rect))
    for i, pin in enumerate(bits(ports, sides.get("over", []))):
        at = snap("M8", h / 2) + 2 * TRACKS["M8"][1] * i
        half = TRACKS["M8"][2] / 2
        rect = (w / 2 - OVER / 2, at - half, w / 2 + OVER / 2, at + half)
        lines.append(line(pin, "over", "M8", rect))
    return lines


def line(pin, side, layer, rect):
    return "%s %s %s %s" % (pin, side, layer, " ".join("%.3f" % v for v in rect))


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--json", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--sides", required=True)
    p.add_argument("--w", type=float, required=True)
    p.add_argument("--h", type=float, required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    with open(a.json) as f:
        ports = json.load(f)["modules"][a.module]["ports"]
    sides = {}
    for s in a.sides.split():
        side, names = s.split(":")
        sides[side] = names.split(",")
    named = {n for ns in sides.values() for n in ns}
    missing = sorted(set(ports) - named)
    if missing:
        raise ValueError("ports on no side: %s" % " ".join(missing))
    with open(a.out, "w") as f:
        f.write("\n".join(plan(ports, sides, a.w, a.h)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
