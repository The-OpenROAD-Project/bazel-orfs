#!/usr/bin/env python3
"""The space half of the macro selection table, from the flat RTL.

    select_table.py --sv design.sv --module M [--module N ...]
                    [--area M=0.91e6 ...] [--children M=A,B,C ...]

For every named module: its interface width in bits (every input, output
and inout port of the module, bus widths summed; continuation-style
declarations, where a direction and width carry over the following
names, are read as Verilog does), and, when an area is known, the side
of the square that area makes and the pins per micron of that square's
perimeter. A parent listed with --children gets the sum of its children's
areas when it has none of its own, so a cut can be compared with the cut
one level down: a parent whose interface is a fraction of its children's
sum is where the architecture drew the narrow line.

This is the first table of the macro selection; the timing table comes
from a hierarchical synthesis and lives next to it. Stdlib only, python
3.6; the flat SV of a large core is read once, streaming.
"""

import argparse
import math
import re
import sys

_DECL = re.compile(
    r"(?:(input|output|inout)\s+)?(?:(?:wire|reg|logic)\s+)?"
    r"(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?([A-Za-z_]\w*)$"
)


def port_bits(sv_path, modules):
    """{module: (bits, ports)} for the modules named, from module headers."""
    want = set(modules)
    found = {}
    cur = None
    buf = []
    with open(sv_path, errors="replace") as f:
        for line in f:
            if cur is None:
                m = re.match(r"module\s+(\w+)\s*\(", line)
                if not (m and m.group(1) in want):
                    continue
                cur = m.group(1)
                buf = []
                line = line[m.end():]  # a header on the module line itself
                if not line.strip():
                    continue
            if ");" in line:
                buf.append(line.split(");")[0])
                found[cur] = _count(buf)
                cur = None
                buf = []
                if len(found) == len(want):
                    break
            else:
                buf.append(line)
    return found


def _count(lines):
    bits = 0
    ports = 0
    width = 1
    for l in [part for line in lines for part in line.split(",")]:
        s = l.strip().rstrip(",").strip()
        if not s or s.startswith("//"):
            continue
        m = _DECL.match(s)
        if not m:
            continue
        if m.group(1):
            width = 1
        if m.group(2):
            width = abs(int(m.group(2)) - int(m.group(3))) + 1
        bits += width
        ports += 1
    return bits, ports


def table(bits, areas, children):
    """Rows of (module, bits, ports, area_um2 or None, side_um, pins_per_um, note)."""

    def area_of(m, seen=()):
        if m in areas:
            return areas[m]
        if m in children and m not in seen:
            parts = [area_of(c, seen + (m,)) for c in children[m]]
            if all(p is not None for p in parts):
                return sum(parts)
        return None

    rows = []
    for m, (b, n) in bits.items():
        a = area_of(m)
        side = math.sqrt(a) if a else None
        note = "" if m in areas else ("children's area" if a else "no area")
        rows.append((m, b, n, a, side, (b / (4 * side)) if side else None, note))
    return rows


def format_table(rows):
    out = ["%-24s %7s %6s %9s %8s %8s %s" % ("module", "bits", "ports", "area mm2", "side um", "pins/um", "note")]
    for m, b, n, a, side, ppu, note in sorted(rows, key=lambda r: -r[1]):
        out.append(
            "%-24s %7d %6d %9s %8s %8s %s"
            % (m, b, n, "%.3f" % (a / 1e6) if a else "-", "%.0f" % side if side else "-", "%.2f" % ppu if ppu else "-", note)
        )
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sv", required=True)
    ap.add_argument("--module", action="append", default=[], help="module to tabulate; repeat")
    ap.add_argument("--area", action="append", default=[], help="M=area_um2 from a synthesised block; repeat")
    ap.add_argument("--children", action="append", default=[], help="M=A,B,C: the modules a cut one level down would harden; repeat")
    a = ap.parse_args(argv[1:])
    areas = {}
    for s in a.area:
        k, v = s.split("=", 1)
        areas[k] = float(v)
    children = {}
    for s in a.children:
        k, v = s.split("=", 1)
        children[k] = v.split(",")
    modules = list(a.module)
    for cs in children.values():
        modules += [c for c in cs if c not in modules]
    bits = port_bits(a.sv, modules)
    missing = [m for m in a.module if m not in bits]
    print(format_table(table(bits, areas, children)))
    if missing:
        print("select_table: not found in the RTL: " + ", ".join(missing), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
