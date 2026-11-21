"""A macro's estimated boundary timing against its real, per port bus.

    compare_libs.py --cell C --period PS --estimated E.lib --real R.lib --out OUT.md

For every port bus of the cell (a bus, or a pin with its bit index
dropped), the worst arrival of its outputs after the clock (the largest
clock-to-output delay of a rising_edge or falling_edge arc) and the
tightest required time of its inputs (the period less the largest setup
constraint), in both liberty files, and the difference, real less
estimated. A negative difference on a required time, or a positive one on
an arrival, is a boundary the estimate was optimistic about. A view with
no arc for a bus says `-`: a ports-only view has none. The buses neither
view has an arc on, the clock and the supplies, are listed after the
table.

Each value is the largest number in the arc's tables, in picoseconds: the
worst corner of slew and load, not the parent's operating point.
"""

import argparse
import re
import sys

TOKEN_RE = re.compile(
    r'\s*(?:(?P<str>"(?:[^"\\]|\\.)*")|(?P<punct>[{}();:,])|(?P<word>[^\s{}();:,"]+))',
    re.S,
)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?")
ARRIVAL_TYPES = {"rising_edge", "falling_edge"}
SETUP_TYPES = {"setup_rising", "setup_falling"}
ARRIVAL_TABLES = {"cell_rise", "cell_fall"}
SETUP_TABLES = {"rise_constraint", "fall_constraint"}
UNITS = {"1ps": 1.0, "10ps": 10.0, "100ps": 100.0, "1ns": 1000.0, "1us": 1e6}


class Group:
    def __init__(self, kind, args):
        self.kind = kind
        self.args = args
        self.attrs = {}
        self.groups = []

    def find(self, kind):
        return [g for g in self.groups if g.kind == kind]


def _strip(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return text.replace("\\\n", " ")


def parse(text):
    """The liberty file's top group, a library."""
    tokens = []
    pos = 0
    text = _strip(text)
    n = len(text)
    while pos < n:
        m = TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                break
            raise ValueError("liberty: cannot read at offset %d" % pos)
        pos = m.end()
        tok = m.group("str") or m.group("punct") or m.group("word")
        if tok is not None:
            tokens.append(tok)
    root = Group("root", [])
    stack = [root]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "}":
            stack.pop()
            i += 1
            continue
        if tok == ";":
            i += 1
            continue
        name = tok
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if nxt == ":":
            value = []
            i += 2
            while i < len(tokens) and tokens[i] not in (";", "}"):
                value.append(tokens[i])
                i += 1
            stack[-1].attrs[name] = " ".join(value).strip('"')
            continue
        if nxt == "(":
            args = []
            i += 2
            depth = 1
            while depth:
                t = tokens[i]
                if t == "(":
                    depth += 1
                elif t == ")":
                    depth -= 1
                    if depth == 0:
                        break
                if t != ",":
                    args.append(t.strip('"'))
                i += 1
            i += 1
            if i < len(tokens) and tokens[i] == "{":
                g = Group(name, args)
                stack[-1].groups.append(g)
                stack.append(g)
                i += 1
            else:
                stack[-1].attrs.setdefault(name, args)
            continue
        i += 1
    libs = root.find("library")
    if not libs:
        raise ValueError("liberty: no library group")
    return libs[0]


def _bus(name):
    return re.sub(r"\[\d+\]$", "", name)


def _worst(group, tables):
    worst = None
    for t in group.groups:
        if t.kind not in tables:
            continue
        values = t.attrs.get("values")
        if values is None:
            continue
        for v in values:
            for num in NUMBER_RE.findall(v):
                x = float(num)
                worst = x if worst is None else max(worst, x)
    return worst


def _pins(cell):
    """(pin name, its group) for every pin, a bus's bits under the bus."""
    for g in cell.groups:
        if g.kind == "pin":
            for name in g.args:
                yield name, g
        elif g.kind == "bus":
            yield g.args[0], g
            for p in g.find("pin"):
                for name in p.args:
                    yield name, p


def boundary(path, cell_name):
    """{bus: {"direction", "arrival", "setup"}} in ps, from one liberty file."""
    with open(path) as f:
        lib = parse(f.read())
    scale = UNITS.get(lib.attrs.get("time_unit", "1ns").replace(" ", ""), None)
    if scale is None:
        raise ValueError("%s: unknown time_unit %s" % (path, lib.attrs["time_unit"]))
    cells = [c for c in lib.find("cell") if c.args and c.args[0] == cell_name]
    if not cells:
        raise ValueError("%s has no cell %s" % (path, cell_name))
    out = {}
    for name, g in _pins(cells[0]):
        bus = _bus(name)
        entry = out.setdefault(bus, {"direction": None, "arrival": None, "setup": None})
        if "direction" in g.attrs:
            entry["direction"] = g.attrs["direction"]
        for t in g.find("timing"):
            kind = t.attrs.get("timing_type", "combinational")
            if kind in ARRIVAL_TYPES:
                key, tables = "arrival", ARRIVAL_TABLES
            elif kind in SETUP_TYPES:
                key, tables = "setup", SETUP_TABLES
            else:
                continue
            w = _worst(t, tables)
            if w is None:
                continue
            w *= scale
            if entry[key] is None or w > entry[key]:
                entry[key] = w
    return out


def _fmt(x):
    return "-" if x is None else "%.1f" % x


def report(cell, period, estimated, real):
    rows = []
    unarced = []
    for bus in sorted(set(estimated) | set(real)):
        e = estimated.get(bus, {})
        r = real.get(bus, {})
        if not any(v.get(k) is not None for v in (e, r) for k in ("arrival", "setup")):
            unarced.append(bus)
            continue
        direction = r.get("direction") or e.get("direction") or "?"
        if direction == "input":
            ev = None if e.get("setup") is None else period - e["setup"]
            rv = None if r.get("setup") is None else period - r["setup"]
            what = "required"
        else:
            ev, rv = e.get("arrival"), r.get("arrival")
            what = "arrival"
        diff = None if ev is None or rv is None else rv - ev
        rows.append((bus, direction, what, ev, rv, diff))
    lines = [
        "# %s: estimated against real boundary timing" % cell,
        "",
        "Clock period %s ps. Required: the period less the worst setup; "
        "arrival: the worst clock-to-output delay; ps, worst table entry." % period,
        "",
        "| bus | direction | timing | estimated | real | real - estimated |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for bus, direction, what, ev, rv, diff in rows:
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (bus, direction, what, _fmt(ev), _fmt(rv), _fmt(diff))
        )
    if unarced:
        lines += ["", "No arc in either view: %s" % ", ".join(unarced)]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--period", required=True, type=float)
    parser.add_argument("--estimated", required=True)
    parser.add_argument("--real", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        text = report(
            args.cell,
            args.period,
            boundary(args.estimated, args.cell),
            boundary(args.real, args.cell),
        )
    except ValueError as e:
        print("compare_libs: %s" % e, file=sys.stderr)
        return 1
    with open(args.out, "w") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
