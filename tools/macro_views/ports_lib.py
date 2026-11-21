"""A macro's liberty view from its Verilog port list alone: pins, no timing.

    ports_lib.py --module M --out M.lib [--lef M.lef] [--clock clock]... SOURCE...

The cell is named after the module and has one pin or bus per port, in the
port's direction and width; the clock ports are marked as clocks. It has
no timing arcs, so a parent timed with it sees no path into or out of the
macro: what crosses the boundary is unconstrained, and synthesis and the
parent's placement read the macro's pins without waiting for its flow.
The area is the LEF's SIZE when a LEF is given, else 0.

The module's header must be ANSI style (the port declarations in the
header), each port's packed dimensions integer constants: what firtool and
a hand-written header usually are. A SOURCE that is a directory stands for
its .v, .sv and .svh files.
"""

import argparse
import os
import re
import sys

IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_$]*|\\\S+"
MODULE_RE = re.compile(
    r"\b(?:macro)?module\s+(?:(?:static|automatic)\s+)?(" + IDENTIFIER + r")"
)
DIRECTION_RE = re.compile(r"^(input|output|inout)\b")
RANGE_RE = re.compile(r"\[\s*(-?\d+)\s*:\s*(-?\d+)\s*\]")
TYPE_WORDS = {"wire", "reg", "logic", "var", "tri", "signed", "unsigned"}
SIZE_RE = re.compile(r"\bSIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;")


class PortError(Exception):
    pass


class Port:
    def __init__(self, name, direction, msb=None, lsb=None):
        self.name = name
        self.direction = direction
        self.msb = msb
        self.lsb = lsb

    @property
    def width(self):
        if self.msb is None:
            return 1
        return abs(self.msb - self.lsb) + 1


def mask(text):
    """text with comments and string literals blanked out, same length."""
    out = list(text)
    i = 0
    n = len(text)

    def blank(start, end):
        for k in range(start, end):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        if c == "\\":
            while i < n and not text[i].isspace():
                i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise PortError("unterminated /* comment")
            blank(i, end + 2)
            i = end + 2
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                j += 1
            blank(i + 1, min(j, n))
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _bare(name):
    return name[1:] if name.startswith("\\") else name


def header(masked, module):
    """The text between the parentheses of module's port list, or None."""
    for m in MODULE_RE.finditer(masked):
        if _bare(m.group(1)) != module:
            continue
        i = m.end()
        n = len(masked)
        while i < n and masked[i].isspace():
            i += 1
        if masked.startswith("#", i):
            i = masked.index("(", i)
            depth = 0
            while True:
                if masked[i] == "(":
                    depth += 1
                elif masked[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            i += 1
            while i < n and masked[i].isspace():
                i += 1
        if masked.startswith(";", i):
            return ""
        if not masked.startswith("(", i):
            raise PortError("module %s: no port list after its name" % module)
        depth = 0
        start = i + 1
        while i < n:
            if masked[i] == "(":
                depth += 1
            elif masked[i] == ")":
                depth -= 1
                if depth == 0:
                    return masked[start:i]
            i += 1
        raise PortError("module %s: port list has no `)`" % module)
    return None


def _split(text):
    """text split at the commas outside brackets and braces."""
    parts = []
    depth = 0
    start = 0
    for i, c in enumerate(text):
        if c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def parse_ports(port_list, module):
    """The ports of an ANSI port list, in order."""
    ports = []
    direction = None
    msb = lsb = None
    for decl in _split(port_list):
        m = DIRECTION_RE.match(decl)
        if m:
            direction = m.group(1)
            rest = decl[m.end() :].strip()
            msb = lsb = None
            ranges = []
            while True:
                words = rest.split(None, 1)
                if words and words[0] in TYPE_WORDS:
                    rest = words[1] if len(words) > 1 else ""
                    continue
                r = RANGE_RE.match(rest)
                if r:
                    ranges.append((int(r.group(1)), int(r.group(2))))
                    rest = rest[r.end() :].strip()
                    continue
                if rest.startswith("["):
                    raise PortError(
                        "module %s: `%s`: a packed dimension that is not an "
                        "integer range" % (module, decl)
                    )
                break
            if len(ranges) > 1:
                width = 1
                for a, b in ranges:
                    width *= abs(a - b) + 1
                msb, lsb = width - 1, 0
            elif ranges:
                msb, lsb = ranges[0]
            name = rest
        elif direction is None:
            raise PortError(
                "module %s: `%s` is not an ANSI port declaration; ports_lib "
                "reads ANSI headers only" % (module, decl)
            )
        else:
            name = decl
        if not re.fullmatch(IDENTIFIER, name):
            raise PortError(
                "module %s: `%s`: an unpacked dimension or a default value "
                "on a port" % (module, decl)
            )
        ports.append(Port(_bare(name), direction, msb, lsb))
    return ports


def expand_sources(sources):
    files = []
    for source in sources:
        if os.path.isdir(source):
            found = []
            for root, _, names in os.walk(source):
                for name in names:
                    if name.endswith((".v", ".sv", ".svh")):
                        found.append(os.path.join(root, name))
            files.extend(sorted(found))
        else:
            files.append(source)
    return files


def find_ports(sources, module):
    for path in expand_sources(sources):
        with open(path, errors="replace") as f:
            port_list = header(mask(f.read()), module)
        if port_list is not None:
            return parse_ports(port_list, module)
    raise PortError("no source defines module %s" % module)


def lef_area(path):
    with open(path) as f:
        m = SIZE_RE.search(f.read())
    if not m:
        raise PortError("%s has no SIZE" % path)
    return float(m.group(1)) * float(m.group(2))


def _name(name):
    return '"%s"' % name if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else name


def emit_lib(module, ports, area, clocks):
    lines = []
    a = lines.append
    a("library (%s) {" % _name(module))
    a("  delay_model : table_lookup;")
    a('  time_unit : "1ps";')
    a('  voltage_unit : "1V";')
    a('  current_unit : "1mA";')
    a('  pulling_resistance_unit : "1kohm";')
    a('  leakage_power_unit : "1pW";')
    a("  capacitive_load_unit (1,ff);")
    a("  nom_process : 1;")
    a("  nom_temperature : 25;")
    a("  nom_voltage : 0.7;")
    widths = sorted({(p.msb, p.lsb) for p in ports if p.msb is not None})
    for msb, lsb in widths:
        a("  type (%s) {" % _bus_type(msb, lsb))
        a("    base_type : array;")
        a("    data_type : bit;")
        a("    bit_width : %d;" % (abs(msb - lsb) + 1))
        a("    bit_from : %d;" % msb)
        a("    bit_to : %d;" % lsb)
        a("    downto : %s;" % ("true" if msb >= lsb else "false"))
        a("  }")
    a("  cell (%s) {" % _name(module))
    a("    area : %.4f;" % area)
    a("    is_macro_cell : true;")
    for p in ports:
        if p.msb is None:
            a("    pin (%s) {" % _name(p.name))
        else:
            a("    bus (%s) {" % _name(p.name))
            a("      bus_type : %s;" % _bus_type(p.msb, p.lsb))
        a("      direction : %s;" % p.direction)
        if p.direction != "output":
            a("      capacitance : 0;")
        if p.name in clocks:
            a("      clock : true;")
        a("    }")
    a("  }")
    a("}")
    return "\n".join(lines) + "\n"


def _bus_type(msb, lsb):
    return "bus_%s_%s" % (str(msb).replace("-", "m"), str(lsb).replace("-", "m"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--lef", help="the macro's LEF; its SIZE is the area")
    parser.add_argument("--clock", action="append", default=[])
    parser.add_argument("sources", nargs="+")
    args = parser.parse_args(argv)
    try:
        ports = find_ports(args.sources, args.module)
        area = lef_area(args.lef) if args.lef else 0.0
    except PortError as e:
        print("ports_lib: %s" % e, file=sys.stderr)
        return 1
    names = {p.name for p in ports}
    missing = [c for c in args.clock if c not in names]
    if missing:
        print(
            "ports_lib: module %s has no clock port %s"
            % (args.module, ", ".join(missing)),
            file=sys.stderr,
        )
        return 1
    with open(args.out, "w") as f:
        f.write(emit_lib(args.module, ports, area, set(args.clock)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
