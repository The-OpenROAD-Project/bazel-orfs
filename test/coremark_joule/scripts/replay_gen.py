#!/usr/bin/env python3
"""Generate the replay of one power shard: its netlist alone, driven from a capture.

    replay_gen.py --name replay_U --top U --netlist U.v --rtl ALL.sv
                  --capture-scope TOP.soc.rtl.u_u [--path SUB]
                  [--child PATH=SCOPE]... [--clock-port clock]...
                  --out-sv R.sv --out-cc R.cc --out-netlist N.v

A shard's SAIF is measured on the shard's own netlist, not on a model of
the whole design (which for XiangShan does not verilate in 32 GB). One
RTL simulation of the whole design records every unit's ports, the
capture (scripts/capture_wrap.py, a VCD of the wrappers' scopes); the
replay of unit U instantiates U's netlist alone, as `dut` in a top
module `<name>`, and drives it from the capture:

  - every input of U from its captured value;
  - each child of U simulated as a shard of its own (`--child`, its
    instance path below U: a block's register files, the parent's
    blocks, or any kept module cut out to keep a simulation small) is a
    stub with that child's ports whose outputs are driven from the
    child's own capture, through a top-level port the stub reads by its
    hierarchical name; the pins U drives into the child are read back
    out the same way and checked;

A simulation shard need not be a hardened unit (--path): any module
instance below U that is a module of its own in U's netlist (a kept
boundary) and in the RTL, with the same ports, is replayed alone the
same way, and the rest of U replayed with it cut out. Refused otherwise,
by name.
  - a true SRAM, or anything else U's netlist instantiates and does not
    define, is its RTL model (gate_stitch.py fills it in).

At each time the capture has, the harness (the generated C++) first sets
the clock pins and evaluates, so every flop samples the values from
before the edge, then sets the other inputs and evaluates, then compares
every output of U and every pin into a child against the capture and
fails on the first difference, naming the signal, the cycle and the
phase: a netlist that does not behave as its RTL is caught where it
first shows. From the window's start it writes the SAIF of `dut`'s scope.

The clock: a netlist clock pin the RTL lacks is tied to the RTL's one
clock (--clock-port names the SDC's clock ports); an RTL clock port the
netlist lacks is not driven; any other port difference is refused by
name, as is a child instantiated other than once in U's netlist.

Capture values are 2-state (Verilator); an x or z in a capture is taken
as 0 and counted.

Punched ports, and the two-level replay. A hierarchical global route
buffers a kept module's net outside it and feeds it back in: the
module's netlist then has input ports its RTL lacks (`net95851_395737`,
or a name like an RTL one), driven in the parent, from the module's own
outputs or from any other net there. The capture has no value for them.
So a kept module cut out of a unit is replayed in two levels:

  level 1  the unit (its remainder) with the module a stub: the stub's
           outputs from the capture, its RTL inputs checked against the
           capture, its punched inputs not checked but recorded, and an
           RTL input its netlist lacks (unused, constant) dropped with a
           report entry. Asked to (`--stubs-vcd=` to the harness), the
           harness writes every stub port at every time to a VCD of its
           own, the stub's scope TOP.<name>.dut.<path>, each punched port
           under an alias `pp_<i>` (an escaped netlist name is ambiguous
           with the hierarchy in a VCD), and replay_gen writes the map
           (--out-stubs, JSON: path -> scope, {netlist port: alias},
           dropped inputs).
  level 2  the module (--path) from that VCD (--stub-map): its RTL
           inputs and its punched ones from the stub's scope, its outputs
           checked against the stub's outputs there, which are the
           capture's. Its SAIF is the module's power-shard activity.

A netlist output its RTL lacks, or an RTL output its netlist lacks, is
refused at either level: the stub could not drive it, the module's
replay could not check it.

At either level, a checked bit the netlist fixes on its own is not
compared: one driven by a tie cell or a constant (a register synthesis
folded, which the RTL holds at whatever it last wrote), or one nothing
drives (a port the module reading it never uses). Every other checked bit
is compared from the first time on. The bits are decided from the
netlist when the replay is generated (ModuleNets), listed in the report
("not_compared") and by the harness at the end of its run. And level 1's
stub drives a bit its module's netlist ties or drives with a constant
with that constant, not the capture's value: the unit sees what the
gates do ("outputs_fixed" in the stubs' map).
"""

import argparse
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gate_stitch import port_decls  # noqa: E402

_DECL = re.compile(
    r"\b(input|output|inout)\b(?:\s+(?:wire|reg|logic|signed))*\s*"
    r"(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)"
)
_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_MODULE = re.compile(r"^\s*module\s+(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)", re.M)
_INSTANCE = re.compile(
    r"^\s*(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)\s+(?:#\(.*?\)\s*)?(\\\S+\s|[A-Za-z_][A-Za-z_0-9$\[\].]*)\s*\(",
    re.M | re.S,
)
_KEYWORDS = {"module", "input", "output", "inout", "wire", "reg", "assign", "endmodule"}


def module_text(text, name):
    m = re.search(
        r"^\s*module\s+" + re.escape(name) + r"\b.*?^\s*endmodule\b", text, re.M | re.S
    )
    if not m:
        raise ValueError("no module {}".format(name))
    return m.group(0)


def decls(text):
    """{port: (direction, width)} of one module's text (gate_stitch's,
    which reads firtool's continued declarations)."""
    return port_decls(text)


def modules(text):
    """{module: [(master, instance)]} of a netlist."""
    out = {}
    starts = [(m.start(), m.group(1)) for m in _MODULE.finditer(text)] + [
        (len(text), None)
    ]
    for (a, name), (b, _) in zip(starts, starts[1:]):
        out[name] = [
            (m.group(1), m.group(2).strip())
            for m in _INSTANCE.finditer(text, a, b)
            if m.group(1) not in _KEYWORDS
        ]
    return out


def instance_paths(text, top, master):
    """Every hierarchical path from `top` to an instance of `master`."""
    mods = modules(text)
    found = []

    def walk(module, path):
        for m, inst in mods.get(module, []):
            here = path + [inst]
            if m == master:
                found.append(here)
            elif m in mods:
                walk(m, here)

    walk(top, [])
    return found


def instance_pins(text, master):
    pins = set()
    for m in re.finditer(
        r"^\s*" + re.escape(master) + r"\s+\S+\s*\((.*?)\);", text, re.M | re.S
    ):
        pins |= set(re.findall(r"\.(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)\s*\(", m.group(1)))
    return pins


def _xmr(segment):
    return segment + " " if segment.startswith("\\") else segment


def _strip(segment):
    return segment.lstrip("\\").strip()


def module_at(text, top, path):
    """The module instantiated at `path` (instance names, `/`) below `top`
    in a netlist or RTL text, or None."""
    mods = modules(text)
    module = top
    for segment in [s for s in path.split("/") if s]:
        found = [m for m, inst in mods.get(module, []) if _strip(inst) == segment]
        if len(found) != 1:
            return None
        module = found[0]
    return module


def closure(text, top, drop=()):
    """The text of `top`'s module and every module below it that `text`
    defines, but for the modules in `drop` and what only they reach."""
    mods = modules(text)
    keep = []
    stack = [top]
    while stack:
        m = stack.pop()
        if m in keep or m in drop or m not in mods:
            continue
        keep.append(m)
        stack += [master for master, _ in mods[m]]
    return "\n".join(module_text(text, m) for m in keep) + "\n"


# Netlist bits whose value the netlist fixes on its own. A two-level
# replay does not compare such a bit with the capture: a tie cell or a
# constant drives a register synthesis folded, which the RTL holds at
# whatever it was last written (a TileLink buffer's unwritten entry reads
# 0, the netlist's mask is all ones); a net nothing drives is a port the
# module reading it never uses, which Verilator reads as 0 and the RTL
# drives with what it computes. Decided per bit from the netlist alone,
# before the run; every other bit is compared from the first time on.

_ID = r"(?:\\\S+|[A-Za-z_][A-Za-z_0-9$]*)"
_CONST = re.compile(r"^(\d*)'[sS]?([bBhHdDoO])([0-9a-fA-FxXzZ_?]+)$")
_REF = re.compile(r"^(" + _ID + r")\s*(?:\[\s*(-?\d+)\s*(?::\s*(-?\d+)\s*)?\])?$", re.S)
_RANGE_DECL = re.compile(
    r"^\s*(input|output|inout|wire|reg|tri|supply0|supply1)\b"
    r"(?:\s+(?:wire|reg|logic|signed))*\s*(?:\[\s*(-?\d+)\s*:\s*(-?\d+)\s*\])?(.*)$",
    re.S,
)
# a standard cell's input pins, by name; any other pin of a cell or
# macro the netlist does not define counts as a driver, so an unknown
# pin can only make a bit compared, never exempt
_CELL_INPUT = re.compile(r"[A-E]\d*|CI|CLK|D|SE|SI|S|ENA|SEN|SETN|RESETN|RESET|SET")
_TIE = {"TIEHI": ("H", "tie hi", 1), "TIELO": ("L", "tie lo", 0)}


def _split_commas(text):
    """`text` split at the commas outside braces, parentheses and escaped
    names."""
    out, depth, cur, i = [], 0, "", 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            m = re.match(r"\\\S+\s?", text[i:])
            cur += m.group(0)
            i += len(m.group(0))
            continue
        if c in "{(":
            depth += 1
        elif c in "})":
            depth -= 1
        if c == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return [s.strip() for s in out if s.strip()]


def expr_bits(expr, ranges):
    """The bits of a connection or assign expression, most significant
    first: (net, index) (index None for a scalar), or ("'", 0 or 1) for a
    constant bit. `ranges`: {net: (msb, lsb)} of the module's vectors."""
    e = expr.strip()
    if not e:
        return []
    if e.startswith("{") and e.endswith("}"):
        inner = e[1:-1].strip()
        rep = re.match(r"^(\d+)\s*(\{.*\})$", inner, re.S)
        if rep:
            return expr_bits(rep.group(2), ranges) * int(rep.group(1))
        out = []
        for part in _split_commas(inner):
            out += expr_bits(part, ranges)
        return out
    c = _CONST.match(re.sub(r"\s+", "", e))
    if c:
        base = {"b": 2, "h": 16, "d": 10, "o": 8}[c.group(2).lower()]
        digits = c.group(3).replace("_", "")
        value = int(re.sub(r"[xXzZ?]", "0", digits), base)
        width = int(c.group(1)) if c.group(1) else 32
        return [("'", (value >> i) & 1) for i in reversed(range(width))]
    r = _REF.match(e)
    if not r:
        raise ValueError(["an expression replay_gen cannot read per bit: " + e])
    name = r.group(1).rstrip()
    if r.group(2) is None:
        if name not in ranges:
            return [(name, None)]
        msb, lsb = ranges[name]
    else:
        msb = int(r.group(2))
        lsb = msb if r.group(3) is None else int(r.group(3))
    step = -1 if msb >= lsb else 1
    return [(name, i) for i in range(msb, lsb + step, step)]


def _statements(text):
    """A module's statements after its header, comments gone."""
    body = _COMMENT.sub("", text)
    body = body[body.index(";") + 1 :]
    body = body[: body.rindex("endmodule")]
    out, cur, i = [], "", 0
    while i < len(body):
        if body[i] == "\\":
            m = re.match(r"\\\S+\s?", body[i:])
            cur += m.group(0)
            i += len(m.group(0))
            continue
        if body[i] == ";":
            out.append(cur.strip())
            cur = ""
        else:
            cur += body[i]
        i += 1
    return [s for s in out if s]


def _connections(text):
    """{pin: expression} of an instance's `.pin(expr), ...`."""
    out = {}
    i = 0
    while True:
        m = re.compile(r"\.(" + _ID + r")\s*\(").search(text, i)
        if not m:
            return out
        depth, j = 1, m.end()
        while depth:
            if text[j] == "\\":
                j += len(re.match(r"\\\S+\s?", text[j:]).group(0))
                continue
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        out[m.group(1).rstrip()] = text[m.end() : j - 1]
        i = j


class ModuleNets:
    """A netlist module's statements read per bit: its vectors' ranges,
    its instances' connections, and what drives each bit."""

    def __init__(self, netlist_modules, name):
        text = netlist_modules[name]
        self.ranges = {}
        self.instances = {}  # instance: (master, {pin: expression})
        self.drivers = {}  # bit: [driver], a driver ("tie hi", 1) etc.
        inputs = []
        statements = _statements(text)
        for s in statements:
            d = _RANGE_DECL.match(s)
            if not d:
                continue
            for n in _split_commas(d.group(4)):
                n = n.split("=")[0].strip().rstrip()
                if d.group(2) is not None:
                    self.ranges[n] = (int(d.group(2)), int(d.group(3)))
                if d.group(1) in ("input", "inout"):
                    inputs.append(n)
        for p, (direction, width) in decls(text).items():
            if direction in ("input", "inout"):
                inputs.append(p)
            if width > 1 and p not in self.ranges:
                self.ranges[p] = (width - 1, 0)
        for n in inputs:
            for b in expr_bits(n, self.ranges):
                self._add(b, ("driven", None))
        for s in statements:
            if _RANGE_DECL.match(s):
                continue
            a = re.match(r"^assign\s+(.*?)\s*=\s*(.*)$", s, re.S)
            if a:
                lhs = expr_bits(a.group(1), self.ranges)
                rhs = expr_bits(a.group(2), self.ranges)
                rhs = [("'", 0)] * (len(lhs) - len(rhs)) + rhs[-len(lhs) :]
                for left, right in zip(lhs, rhs):
                    if right[0] == "'":
                        self._add(left, ("const", right[1]))
                    else:
                        self._add(left, ("alias", right))
                continue
            m = re.match(
                r"^(" + _ID + r")\s+(?:#\s*\(.*?\)\s*)?(" + _ID + r")\s*\((.*)\)$",
                s,
                re.S,
            )
            if not m:
                continue
            master, inst = m.group(1).rstrip(), m.group(2).rstrip()
            conns = _connections(m.group(3))
            self.instances[inst] = (master, conns)
            sub = decls(netlist_modules[master]) if master in netlist_modules else None
            tie = [v for k, v in _TIE.items() if master.startswith(k)]
            for pin, e in conns.items():
                if tie and pin == tie[0][0]:
                    driver = (tie[0][1], tie[0][2])
                elif sub is not None:
                    if sub.get(pin, ("input",))[0] == "input":
                        continue
                    driver = ("driven", None)
                elif _CELL_INPUT.fullmatch(pin):
                    continue
                else:
                    driver = ("driven", None)
                for b in expr_bits(e, self.ranges):
                    if b[0] != "'":
                        self._add(b, driver)

    def _add(self, bit, driver):
        self.drivers.setdefault(bit, []).append(driver)

    def fixed(self, bit, seen=()):
        """(reason, value) when the netlist alone fixes `bit`: tie hi, tie
        lo, const, or undriven (value None); else None."""
        if bit[0] == "'":
            return ("const", bit[1])
        drivers = self.drivers.get(bit, [])
        if not drivers:
            return ("undriven", None)
        if any(k == "driven" for k, _ in drivers) or len(drivers) > 1:
            return None
        kind, v = drivers[0]
        if kind == "alias":
            if v in seen:
                return None
            return self.fixed(v, seen + (bit,))
        return (kind, v)

    def port_bits(self, port, width):
        """A port's bits, least significant first."""
        return list(reversed(expr_bits(port, self.ranges)))[:width] if width else []


def _netlist_modules(text):
    return {m: module_text(text, m) for m in modules(text)}


def classify(netlist_ports, rtl_ports, is_clock):
    """(punched, dropped, refused) of a kept module's netlist ports
    against its RTL's, the clock aside: punched, netlist inputs the RTL
    lacks; dropped, RTL ports the netlist lacks (an input nothing reads,
    an output nothing loads or a constant: synthesis took it away, and
    nothing in the netlist connects it); refused, a netlist output the
    RTL lacks (a punched output: the logic outside reads a net only the
    cut computes, so its unit's replay cannot be driven without it)."""
    nl_only = sorted(p for p in set(netlist_ports) - set(rtl_ports) if not is_clock(p))
    rtl_only = sorted(p for p in set(rtl_ports) - set(netlist_ports) if not is_clock(p))
    punched = [p for p in nl_only if netlist_ports[p][0] == "input"]
    dropped = list(rtl_only)
    refused = [
        "netlist {} {} its RTL lacks".format(netlist_ports[p][0], p)
        for p in nl_only
        if netlist_ports[p][0] != "input"
    ]
    return punched, dropped, refused


def generate(
    name,
    top,
    netlist,
    rtl,
    capture_scope,
    children,
    clock_ports,
    path="",
    clock_nets=(),
    stub_map=None,
    record_stubs=False,
    count_outputs=False,
    compare_from_reset=False,
    reset_port="reset",
):
    """(replay top Verilog, harness C++, report, the dut's netlist).

    `record_stubs`: level 1 of a two-level replay, the harness that can
    record the stubs' ports (--stubs-vcd=); a stub with punched inputs
    needs it. Without it the harness is the one-level one, byte for byte,
    so a replay that records nothing keeps its cache key.

    `top` is the unit's module (in its netlist and its RTL alike); `path`
    a module instance below it, the simulation shard this replays (empty:
    the unit whole), which must be a module of its own in the netlist and
    in the RTL, with the same ports but at the clock: a kept module's
    clock arrives through the clock tree, one port per leaf net that
    reaches it (`clknet_*`, the `clock_nets` patterns), where the RTL has
    its one clock port; those are the one clock and are tied to it. `children` are (path below the
    shard, capture scope): instances cut out of it, each a stub driven
    from its own capture.

    `stub_map` is level 1's map of the stub this replays (`path`'s entry
    of --out-stubs): the capture is then level 1's stubs VCD, and the
    module's punched inputs are read from it under their aliases. The
    report's "stubs" is that map of this replay's own stubs.
    """
    clocks = set(clock_ports)

    def is_clock(p):
        return p in clocks or any(fnmatch.fnmatchcase(p, c) for c in clock_nets)

    refused = []
    rtl_top = top
    if path:
        gate = module_at(netlist, top, path)
        if gate not in modules(netlist):
            gate = None  # a cell or a macro there, not a module of its own
        # a module kept below one that was not is a dotted name in the
        # netlist, a level of hierarchy per dot in the RTL
        rtl_top = module_at(rtl, top, path.replace(".", "/"))
        if gate is None or rtl_top is None:
            raise ValueError(
                [
                    "{}/{}: not a module of its own in the {} (a kept boundary)".format(
                        top, path, "netlist" if gate is None else "RTL"
                    )
                ]
            )
        top = gate
    cut = {}
    for child, scope in children:
        master = module_at(netlist, top, child)
        rtl_master = module_at(rtl, rtl_top, child.replace(".", "/"))
        if master is None or rtl_master is None:
            refused.append(
                "{}/{}: no module instance there in the {}".format(
                    top, child, "netlist" if master is None else "RTL"
                )
            )
            continue
        cut[child] = (master, rtl_master, scope)
    if refused:
        raise ValueError(refused)
    dut_netlist = closure(netlist, top, {m for m, _, _ in cut.values() if m != top})
    unit = decls(module_text(netlist, top))
    captured = decls(module_text(rtl, rtl_top))
    aliases = {}
    dropped_here = []
    if path and stub_map is not None:
        # level 2: the punched inputs from level 1's record of them
        punched, dropped_here, bad = classify(unit, captured, is_clock)
        refused += ["{}: {}".format(top, b) for b in bad]
        unknown = [p for p in punched if p not in stub_map["punched"]]
        if unknown:
            refused.append(
                "{}: punched inputs level 1 did not record: {}".format(
                    top, ", ".join(unknown)
                )
            )
        if stub_map["scope"] != capture_scope:
            refused.append(
                "{}: level 1 recorded its stub at {}, not {}".format(
                    top, stub_map["scope"], capture_scope
                )
            )
        aliases = {p: stub_map["punched"][p] for p in punched if p not in unknown}
    else:
        odd = sorted(p for p in set(unit) ^ set(captured) if not is_clock(p))
        if odd:
            refused.append(
                "{}: ports of its netlist and its RTL differ, not at the clock: {}".format(
                    top, ", ".join(odd)
                )
            )
    rtl_clock = sorted(set(captured) & clocks)
    tied = sorted(p for p in set(unit) - set(captured) if is_clock(p))
    if tied and len(rtl_clock) != 1:
        refused.append("{}: no one RTL clock port to tie {} to".format(top, tied))

    # (port of the replay top, direction, width, capture name, role); the
    # top's ports are numbered, p<i>: Verilator mangles a `__` in a C++
    # name, and a unit's port names are whatever its RTL's are
    sigs = []
    conns = []
    two_level = record_stubs or stub_map is not None
    reset_row = None
    # checked signals the netlist may fix: (index in sigs, module, the
    # instance whose pin it is or None for the module's own port, port,
    # width)
    checked = []
    # the checked pins the unit drives into a stub: a diagnostic in a
    # two-level replay, not one of its proof obligations
    stub_inputs = set()
    nl_mods = _netlist_modules(netlist) if two_level else {}
    nets = {}

    def module_nets(m):
        if m not in nets:
            nets[m] = ModuleNets(nl_mods, m)
        return nets[m]

    def port():
        return "p{}".format(len(sigs))

    for p, (d, w) in sorted(unit.items()):
        if p in tied:
            continue
        q = port()
        cap = capture_scope + "." + aliases.get(p, p)
        if d == "input":
            role = "clock" if p in clocks else "in"
            sigs.append((q, "input", w, cap, role))
            if p == reset_port and role == "in":
                reset_row = len(sigs) - 1
        else:
            sigs.append((q, "output", w, cap, "out"))
            # a dut output, checked: its bits in the dut's module
            checked.append((len(sigs) - 1, top, None, p, w))
        conns.append(".{}({})".format(_xmr(p), q))
    if tied and rtl_clock:
        clock = [
            q for q, _, _, cap, _ in sigs if cap == capture_scope + "." + rtl_clock[0]
        ]
        if not clock:
            # the RTL's clock is no port of the netlist: driven from the
            # capture all the same, for the tied ports
            clock = [port()]
            sigs.append(
                (clock[0], "input", 1, capture_scope + "." + rtl_clock[0], "clock")
            )
        for p in tied:
            conns.append(".{}({})".format(_xmr(p), clock[0]))

    stubs = []
    checks = []
    # (VCD scope, VCD name, index in sigs): every stub port, for level 2
    trace = []
    stub_maps = {}
    top_clock = [i for i, s in enumerate(sigs) if s[4] == "clock"]
    for child_path, (master, rtl_master, scope) in sorted(cut.items()):
        paths = instance_paths(netlist, top, master)
        if len(paths) != 1:
            refused.append(
                "{}: {} instances in {}, not one".format(master, len(paths), top)
            )
            continue
        child = decls(module_text(rtl, rtl_master))
        kept = {}
        punched, dropped = [], []
        if master in modules(netlist):
            # a kept module cut out: its netlist's ports are the RTL's,
            # but at the clock and for the punched inputs
            kept = decls(module_text(netlist, master))
            punched, dropped, bad = classify(kept, child, is_clock)
            if bad:
                refused.append(
                    "{}: ports of its netlist and its RTL differ: {}".format(
                        child_path, ", ".join(bad)
                    )
                )
                continue
        pins = instance_pins(netlist, master)
        extra = sorted(pins - set(child))
        odd = [p for p in extra if not is_clock(p) and p not in punched]
        if odd:
            refused.append(
                "{}: pins {} its RTL lacks, not at the clock".format(master, odd)
            )
            continue
        vcd_scope = "TOP.{}.dut.{}".format(
            name, ".".join(_strip(s) for s in child_path.split("/") if s)
        )
        hier = "dut." + ".".join(_xmr(s) for s in paths[0])
        # the module the stub's instance is in
        container = (
            module_at(netlist, top, "/".join(_strip(s) for s in paths[0][:-1]))
            if len(paths[0]) > 1
            else top
        )
        faithful = []
        body = []
        decl_lines = []
        stub_ports = []
        traced = set()
        for p, (d, w) in sorted(child.items()):
            if p in dropped:
                continue
            if d != "output" and p not in pins and is_clock(p):
                # an RTL clock pin the netlist reaches through its leaves:
                # no pin of the stub; level 2 reads the replay's clock
                if top_clock and p not in traced:
                    trace.append((vcd_scope, p, top_clock[0]))
                    traced.add(p)
                continue
            stub_ports.append(p)
            rng = "[{}:0] ".format(w - 1) if w > 1 else ""
            decl_lines.append("  {} {}{};".format(d, rng, p))
            q = port()
            if d == "output":
                sigs.append((q, "input", w, scope + "." + p, "in"))
                body.append(
                    "  assign {} = {};".format(
                        p,
                        _stub_drive(
                            name,
                            q,
                            p,
                            w,
                            master,
                            kept,
                            record_stubs,
                            module_nets,
                            faithful,
                        ),
                    )
                )
            else:
                sigs.append((q, "output", w, scope + "." + p, "out"))
                checks.append("  assign {} = {}.{};".format(q, hier, p))
                if two_level:
                    checked.append((len(sigs) - 1, container, paths[0][-1], p, w))
                    stub_inputs.add(len(sigs) - 1)
            trace.append((vcd_scope, _strip(p), len(sigs) - 1))
            traced.add(p)
        aliases_here = {}
        for p in extra:
            w = kept[p][1] if p in kept else 1
            rng = "[{}:0] ".format(w - 1) if w > 1 else ""
            decl_lines.append("  input {}{};".format(rng, _xmr(p)))
            if p in punched:
                # driven in the unit, not by the capture: recorded, not checked
                alias = "pp_{}".format(len(aliases_here))
                aliases_here[p] = alias
                q = port()
                sigs.append((q, "output", w, vcd_scope + "." + alias, "rec"))
                checks.append("  assign {} = {}.{};".format(q, hier, _xmr(p)))
                trace.append((vcd_scope, alias, len(sigs) - 1))
        stub_maps[child_path] = {
            "module": master,
            "scope": vcd_scope,
            "punched": aliases_here,
            "dropped": dropped,
        }
        if record_stubs:
            stub_maps[child_path]["outputs_fixed"] = faithful
        stubs.append(
            "// {}: a shard of its own, its outputs from its capture\n"
            "module {} ({});\n{}\n{}\nendmodule\n".format(
                master,
                master,
                ", ".join(_xmr(p) for p in stub_ports + extra),
                "\n".join(decl_lines),
                "\n".join(body),
            )
        )
    if refused:
        raise ValueError(refused)

    exempt = []  # (index in sigs, bit, reason, value)
    for i, module, inst, p, w in checked if two_level else []:
        mn = module_nets(module)
        if inst is None:
            bits = mn.port_bits(p, w)
        else:
            e = mn.instances[inst][1].get(p)
            bits = [] if e is None else list(reversed(expr_bits(e, mn.ranges)))[:w]
        bits += [None] * (w - len(bits))  # an unconnected pin
        for b, bit in enumerate(bits):
            f = ("undriven", None) if bit is None else mn.fixed(bit)
            if f:
                exempt.append((i, b, f[0], f[1]))

    port_lines = []
    for port, d, w, _, _ in sigs:
        rng = "[{}:0] ".format(w - 1) if w > 1 else ""
        port_lines.append("    {} {}{}".format(d, rng, port))
    sv = (
        "// The replay of {top}: its netlist alone (scripts/replay_gen.py).\n"
        "module {name} (\n{ports}\n);\n  {top} dut ({conns});\n{checks}\nendmodule\n{stubs}"
    ).format(
        top=top,
        name=name,
        ports=",\n".join(port_lines),
        # one line per connection only where one line would be too long
        # for Verilator's preprocessor (40,000 tokens): a cut with
        # thousands of punched ports; every other replay keeps its text
        conns=(", " if sum(len(c) for c in conns) < 100000 else ",\n    ").join(conns),
        checks="\n".join(checks),
        stubs="".join(stubs),
    )
    if not record_stubs and any(r == "rec" for _, _, _, _, r in sigs):
        raise ValueError(
            [
                "{}: a stub with punched inputs, recorded only in a two-level replay's level 1 (--record-stubs)".format(
                    top
                )
            ]
        )
    if compare_from_reset and not two_level:
        raise ValueError(
            ["{}: --compare-from-reset is for a two-level replay's harness".format(top)]
        )
    if compare_from_reset and reset_row is None:
        raise ValueError(
            [
                "{}: --compare-from-reset, but no reset input {} driven from the "
                "capture".format(top, reset_port)
            ]
        )
    if count_outputs and not (record_stubs or stub_map is not None):
        raise ValueError(
            ["{}: --count-outputs is for a two-level replay's harness".format(top)]
        )
    if record_stubs or stub_map is not None:
        cc = (
            _harness_reset(
                _harness_count(_HARNESS, count_outputs),
                reset_row if compare_from_reset else None,
            )
            .replace("@NAME@", name)
            .replace("@TABLE@", _table(sigs, stub_inputs))
            .replace("@TRACE@", _trace_table(trace))
            .replace("@EXEMPT@", _exempt_table(exempt))
        )
    else:
        # no stub recorded: the one-level harness, byte for byte the one
        # before two-level replays, so a replay without stubs keeps its
        # cache key
        cc = _HARNESS_ONE_LEVEL.replace("@NAME@", name).replace("@TABLE@", _table(sigs))
    report = {
        "top": top,
        "signals": len(sigs),
        "bits_in": sum(w for _, d, w, _, _ in sigs if d == "input"),
        "bits_checked": sum(w for _, _, w, _, r in sigs if r == "out"),
        "bits_recorded": sum(w for _, _, w, _, r in sigs if r == "rec"),
        "clock_tied": tied,
        "children": sorted(cut),
        "path": path,
        "stubs": stub_maps,
        "punched": aliases,
        "dropped": dropped_here,
    }
    if count_outputs:
        report["count_outputs"] = True
    if compare_from_reset:
        report["compare_from_reset"] = sigs[reset_row][3]
    if two_level:
        report["not_compared"] = [
            {"signal": sigs[i][3], "bit": b, "reason": r, "value": v}
            for i, b, r, v in exempt
        ]
    return sv, cc, report, dut_netlist


def _table(sigs, stub_inputs=()):
    rows = []
    for i, (port, d, w, cap, role) in enumerate(sigs):
        member = "d->" + port
        if d == "input":
            fn = "[](V* d, const Words& v) {{ put({}, v); }}".format(member)
            rows.append(
                '    {{"{}", "{}", {}, {}, {}, nullptr}},'.format(
                    cap, port, w, "kClock" if role == "clock" else "kIn", fn
                )
            )
        else:
            fn = "[](V* d, Words& v) {{ get({}, v); }}".format(member)
            rows.append(
                '    {{"{}", "{}", {}, {}, nullptr, {}}},'.format(
                    cap,
                    port,
                    w,
                    {"rec": "kRec"}.get(
                        role, "kStubIn" if i in stub_inputs else "kOut"
                    ),
                    fn,
                )
            )
    return "\n".join(rows)


def _stub_drive(name, q, p, w, master, kept, record_stubs, module_nets, faithful):
    """What a stub drives its output `p` with: the capture's value, but,
    in level 1, a bit the cut module's netlist ties or drives with a
    constant is that constant, so the unit sees what the gates do."""
    src = "{}.{}".format(name, q)
    if not record_stubs or not kept:
        return src
    mn = module_nets(master)
    fixed = [mn.fixed(b) for b in mn.port_bits(p, w)]
    if not any(f and f[1] is not None for f in fixed):
        return src
    parts = []
    for b in reversed(range(w)):
        f = fixed[b] if b < len(fixed) else None
        if f and f[1] is not None:
            parts.append("1'b{}".format(f[1]))
            faithful.append({"port": p, "bit": b, "reason": f[0], "value": f[1]})
        else:
            parts.append("{}[{}]".format(src, b) if w > 1 else src)
    return "{" + ", ".join(parts) + "}" if w > 1 else parts[0]


def _exempt_table(exempt):
    return "".join(
        '    {{{}, {}, "{}", {}}},\n'.format(i, b, r, -1 if v is None else v)
        for i, b, r, v in exempt
    )


def _trace_table(trace):
    return "".join(
        '    {{"{}", "{}", {}}},\n'.format(scope, var, i) for scope, var, i in trace
    )


# The harness of a replay that records no stub (two-level replays' level 2
# and every unit without cuts), as it was before two-level replays.
_HARNESS_ONE_LEVEL = r"""// Generated by scripts/replay_gen.py: the replay harness of @NAME@.
//
//   replay <capture.vcd> <out> <window_start> <clk_period> [<window_end> [<from>=<to>]]
//
// Reads the capture, a VCD of the RTL simulation's unit wrappers, and
// at each of its times sets the clock pins and evaluates, sets the other
// inputs and evaluates, compares every checked signal, and dumps the
// trace: a SAIF from window_start to window_end (0: the capture's end),
// its time relative to the window, or a VCD of every time, absolute (a
// replay of RTL that is itself a capture). <from>=<to> reads a capture
// whose scopes begin <to> where this replay's names begin <from>.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "V@NAME@.h"
#include "verilated.h"
#if VM_TRACE_VCD
#include "verilated_vcd_c.h"
using Trace = VerilatedVcdC;
#else
#include "verilated_saif_c.h"
using Trace = VerilatedSaifC;
#endif

using V = V@NAME@;
using Words = std::vector<uint32_t>;

namespace {

template <typename T>
void put(T& p, const Words& v) {
    uint64_t x = v.empty() ? 0 : v[0];
    if (v.size() > 1) x |= static_cast<uint64_t>(v[1]) << 32;
    p = static_cast<T>(x);
}
template <std::size_t N>
void put(VlWide<N>& p, const Words& v) {
    for (std::size_t i = 0; i < N; i++) p[i] = i < v.size() ? v[i] : 0;
}
template <typename T>
void get(const T& p, Words& v) {
    uint64_t x = static_cast<uint64_t>(p);
    v.assign({static_cast<uint32_t>(x), static_cast<uint32_t>(x >> 32)});
}
template <std::size_t N>
void get(const VlWide<N>& p, Words& v) {
    v.assign(N, 0);
    for (std::size_t i = 0; i < N; i++) v[i] = p[i];
}

enum Role { kClock, kIn, kOut };
struct Sig {
    const char* capture;
    const char* port;
    int width;
    Role role;
    void (*set)(V*, const Words&);
    void (*read)(V*, Words&);
};

const Sig kSigs[] = {
@TABLE@
};
const std::size_t kCount = sizeof(kSigs) / sizeof(kSigs[0]);

Words masked(Words v, int width) {
    std::size_t n = (width + 31) / 32;
    v.resize(std::max<std::size_t>(n, 2), 0);
    for (std::size_t i = n; i < v.size(); i++) v[i] = 0;
    if (width % 32) v[n - 1] &= (1u << (width % 32)) - 1;
    v.resize(n);
    return v;
}

std::string hex(const Words& v) {
    std::string s;
    char b[16];
    for (std::size_t i = v.size(); i-- > 0;) {
        snprintf(b, sizeof(b), "%08x", v[i]);
        s += b;
    }
    return s;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 5 || argc > 7) {
        fprintf(stderr,
                "usage: %s <capture.vcd> <out> <window_start> <clk_period> "
                "[<window_end> [<from>=<to>]]\n",
                argv[0]);
        return 2;
    }
    const uint64_t end = argc > 5 ? strtoull(argv[5], nullptr, 0) : 0;
    std::string from, to;
    if (argc > 6) {
        std::string m = argv[6];
        from = m.substr(0, m.find('='));
        to = m.substr(m.find('=') + 1);
    }
    Verilated::commandArgs(argc, argv);
    std::ifstream vcd(argv[1]);
    const uint64_t start = strtoull(argv[3], nullptr, 0);
    const uint64_t period = strtoull(argv[4], nullptr, 0);

    // the header: each captured signal's id code
    std::map<std::string, std::size_t> by_name;
    for (std::size_t i = 0; i < kCount; i++) {
        std::string n = kSigs[i].capture;
        if (!from.empty() && n.compare(0, from.size(), from) == 0) n = to + n.substr(from.size());
        by_name[n] = i;
    }
    std::map<std::string, std::vector<std::size_t>> by_id;
    std::vector<std::string> scope;
    std::string line;
    while (std::getline(vcd, line)) {
        std::istringstream ss(line);
        std::string tok;
        ss >> tok;
        if (tok == "$scope") {
            std::string kind, name;
            ss >> kind >> name;
            scope.push_back(name);
        } else if (tok == "$upscope") {
            scope.pop_back();
        } else if (tok == "$var") {
            std::string type, width, id, name;
            ss >> type >> width >> id >> name;
            std::string full;
            for (const auto& s : scope) full += s + ".";
            full += name;
            auto it = by_name.find(full);
            if (it != by_name.end()) by_id[id].push_back(it->second);
        } else if (tok == "$enddefinitions") {
            break;
        }
    }
    std::vector<bool> seen(kCount, false);
    for (const auto& [id, list] : by_id)
        for (auto i : list) seen[i] = true;
    int missing = 0;
    for (std::size_t i = 0; i < kCount; i++) {
        if (!seen[i]) {
            fprintf(stderr, "replay: %s is not in the capture\n", kSigs[i].capture);
            missing++;
        }
    }
    if (missing) return 1;

    V* d = new V;
    Verilated::traceEverOn(true);
    Trace* saif = new Trace;
    d->trace(saif, 99);
    bool open = false;

    std::vector<Words> value(kCount);
    uint64_t xs = 0, steps = 0, compared = 0;
    auto step = [&](uint64_t t) -> bool {
        for (std::size_t i = 0; i < kCount; i++)
            if (kSigs[i].role == kClock) kSigs[i].set(d, value[i]);
        d->eval();
        for (std::size_t i = 0; i < kCount; i++)
            if (kSigs[i].role == kIn) kSigs[i].set(d, value[i]);
        d->eval();
        Words got;
        for (std::size_t i = 0; i < kCount; i++) {
            if (kSigs[i].role != kOut) continue;
            kSigs[i].read(d, got);
            Words a = masked(got, kSigs[i].width), b = masked(value[i], kSigs[i].width);
            compared++;
            if (a != b) {
                fprintf(stderr,
                        "replay: %s differs at cycle %llu (time %llu, clock %s): "
                        "captured %s, netlist %s\n",
                        kSigs[i].capture, (unsigned long long)(t / period),
                        (unsigned long long)t, (t % period) ? "high" : "low",
                        hex(b).c_str(), hex(a).c_str());
                return false;
            }
        }
#if VM_TRACE_VCD
        if (!open) {
            saif->open(argv[2]);
            open = true;
        }
        saif->dump(t);
#else
        if (t >= start && (end == 0 || t < end)) {
            if (!open) {
                saif->open(argv[2]);
                open = true;
            }
            saif->dump(t - start);
        }
#endif
        steps++;
        return true;
    };

    bool have = false;
    uint64_t t = 0;
    while (std::getline(vcd, line)) {
        if (line.empty() || line[0] == '$') continue;
        if (line[0] == '#') {
            if (have && !step(t)) return 1;
            t = strtoull(line.c_str() + 1, nullptr, 10);
            have = true;
            continue;
        }
        std::string bits, id;
        if (line[0] == 'b' || line[0] == 'B') {
            std::size_t sp = line.find(' ');
            bits = line.substr(1, sp - 1);
            id = line.substr(sp + 1);
        } else {
            bits = line.substr(0, 1);
            id = line.substr(1);
        }
        auto it = by_id.find(id);
        if (it == by_id.end()) continue;
        Words w((bits.size() + 31) / 32, 0);
        for (std::size_t k = 0; k < bits.size(); k++) {
            char c = bits[bits.size() - 1 - k];
            if (c == '1') w[k / 32] |= 1u << (k % 32);
            else if (c != '0') xs++;
        }
        for (auto i : it->second) value[i] = w;
    }
    if (have && !step(t)) return 1;
    if (open) saif->close();
    fprintf(stderr, "replay: %llu times, %llu comparisons, all equal; %llu x/z capture bits taken as 0\n",
            (unsigned long long)steps, (unsigned long long)compared, (unsigned long long)xs);
    d->final();
    delete saif;
    delete d;
    return 0;
}
"""

_HARNESS = r"""// Generated by scripts/replay_gen.py: the replay harness of @NAME@.
//
//   replay <capture.vcd> <out> <window_start> <clk_period> [<window_end> [<from>=<to>]]
//          [--stubs-vcd=<stubs.vcd>] [--strict-stub-inputs]
//          [--stub-inputs-json=<report.json>]
//
// Reads the capture, a VCD of the RTL simulation's unit wrappers, and
// at each of its times sets the clock pins and evaluates, sets the other
// inputs and evaluates, compares every checked signal, and dumps the
// trace: a SAIF from window_start to window_end (0: the capture's end),
// its time relative to the window, or a VCD of every time, absolute (a
// replay of RTL that is itself a capture). <from>=<to> reads a capture
// whose scopes begin <to> where this replay's names begin <from>.
// --stubs-vcd writes every port of every stub at every time, absolute,
// each punched port under its alias: level 2's capture.
//
// Every checked bit is compared at every time, from the first, but the
// bits the netlist fixes on its own (replay_gen.py decides them from the
// netlist): a tie cell's or a constant's, and a net nothing drives.
//
// What a two-level replay proves: level 1, the unit's own ports are the
// capture's (kOut); level 2, each cut piece's outputs are (its kOut, its
// stub's outputs, which are the capture's). The pins the unit drives into
// a stub (kStubIn) are internal nets of the unit, which the RTL also has:
// compared, and each differing cycle counted and reported (the top 20,
// --stub-inputs-json), but not required to match, unless
// --strict-stub-inputs: a difference there that matters shows at the
// piece's outputs in level 2.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "V@NAME@.h"
#include "verilated.h"
#if VM_TRACE_VCD
#include "verilated_vcd_c.h"
using Trace = VerilatedVcdC;
#else
#include "verilated_saif_c.h"
using Trace = VerilatedSaifC;
#endif

using V = V@NAME@;
using Words = std::vector<uint32_t>;

namespace {

template <typename T>
void put(T& p, const Words& v) {
    uint64_t x = v.empty() ? 0 : v[0];
    if (v.size() > 1) x |= static_cast<uint64_t>(v[1]) << 32;
    p = static_cast<T>(x);
}
template <std::size_t N>
void put(VlWide<N>& p, const Words& v) {
    for (std::size_t i = 0; i < N; i++) p[i] = i < v.size() ? v[i] : 0;
}
template <typename T>
void get(const T& p, Words& v) {
    uint64_t x = static_cast<uint64_t>(p);
    v.assign({static_cast<uint32_t>(x), static_cast<uint32_t>(x >> 32)});
}
template <std::size_t N>
void get(const VlWide<N>& p, Words& v) {
    v.assign(N, 0);
    for (std::size_t i = 0; i < N; i++) v[i] = p[i];
}

// kRec: a stub's punched input, read and recorded, never compared;
// kStubIn: a pin the unit drives into a stub, a diagnostic (above)
enum Role { kClock, kIn, kOut, kStubIn, kRec };
struct Sig {
    const char* capture;
    const char* port;
    int width;
    Role role;
    void (*set)(V*, const Words&);
    void (*read)(V*, Words&);
};

const Sig kSigs[] = {
@TABLE@
};
const std::size_t kCount = sizeof(kSigs) / sizeof(kSigs[0]);

struct TraceVar {
    const char* scope;
    const char* name;
    std::size_t sig;
};
const TraceVar kTrace[] = {
@TRACE@    {nullptr, nullptr, 0},
};
const std::size_t kTraceCount = sizeof(kTrace) / sizeof(kTrace[0]) - 1;

// the checked bits never compared: tie hi, tie lo, const, undriven
// (value -1)
struct Exempt {
    std::size_t sig;
    int bit;
    const char* reason;
    int value;
};
const Exempt kExempt[] = {
@EXEMPT@    {0, -1, nullptr, 0},
};
const std::size_t kExemptCount = sizeof(kExempt) / sizeof(kExempt[0]) - 1;

std::string vcd_id(std::size_t i) {
    std::string s;
    do {
        s += static_cast<char>('!' + i % 94);
        i /= 94;
    } while (i);
    return s;
}

std::vector<std::string> split(const std::string& s) {
    std::vector<std::string> out;
    std::size_t a = 0;
    for (std::size_t b; (b = s.find('.', a)) != std::string::npos; a = b + 1)
        out.push_back(s.substr(a, b - a));
    out.push_back(s.substr(a));
    return out;
}

// the stubs' ports, as a VCD the harness reads (level 2's capture)
struct StubsVcd {
    FILE* f = nullptr;
    std::vector<Words> last;
    bool first = true;

    void open(const char* path) {
        f = fopen(path, "w");
        if (!f) {
            fprintf(stderr, "replay: cannot write %s\n", path);
            exit(1);
        }
        fprintf(f, "$timescale 1ps $end\n");
        std::vector<std::size_t> order(kTraceCount);
        for (std::size_t i = 0; i < kTraceCount; i++) order[i] = i;
        std::stable_sort(order.begin(), order.end(), [](std::size_t a, std::size_t b) {
            return std::string(kTrace[a].scope) < std::string(kTrace[b].scope);
        });
        std::vector<std::string> stack;
        for (auto i : order) {
            auto want = split(kTrace[i].scope);
            std::size_t common = 0;
            while (common < stack.size() && common < want.size() &&
                   stack[common] == want[common])
                common++;
            while (stack.size() > common) {
                fprintf(f, "$upscope $end\n");
                stack.pop_back();
            }
            for (; common < want.size(); common++) {
                fprintf(f, "$scope module %s $end\n", want[common].c_str());
                stack.push_back(want[common]);
            }
            int w = kSigs[kTrace[i].sig].width;
            if (w > 1)
                fprintf(f, "$var wire %d %s %s [%d:0] $end\n", w, vcd_id(i).c_str(),
                        kTrace[i].name, w - 1);
            else
                fprintf(f, "$var wire 1 %s %s $end\n", vcd_id(i).c_str(), kTrace[i].name);
        }
        for (; !stack.empty(); stack.pop_back()) fprintf(f, "$upscope $end\n");
        fprintf(f, "$enddefinitions $end\n");
        last.resize(kTraceCount);
    }
};

Words masked(Words v, int width) {
    std::size_t n = (width + 31) / 32;
    v.resize(std::max<std::size_t>(n, 2), 0);
    for (std::size_t i = n; i < v.size(); i++) v[i] = 0;
    if (width % 32) v[n - 1] &= (1u << (width % 32)) - 1;
    v.resize(n);
    return v;
}

std::string json_str(const char* s) {
    std::string out = "\"";
    for (; *s; s++) {
        if (*s == '"' || *s == '\\') out += '\\';
        out += *s;
    }
    return out + "\"";
}

std::string hex(const Words& v) {
    std::string s;
    char b[16];
    for (std::size_t i = v.size(); i-- > 0;) {
        snprintf(b, sizeof(b), "%08x", v[i]);
        s += b;
    }
    return s;
}

}  // namespace

int main(int argc, char** argv) {
    std::string stubs_path, stub_inputs_json;
@RESET_ARGDECL@@COUNT_ARGDECL@    bool strict_stub_inputs = false;
    {
        int n = 0;
        for (int i = 0; i < argc; i++) {
            std::string a = argv[i];
            if (a.compare(0, 12, "--stubs-vcd=") == 0)
                stubs_path = a.substr(12);
            else if (a == "--strict-stub-inputs")
                strict_stub_inputs = true;
            else if (a.compare(0, 19, "--stub-inputs-json=") == 0)
                stub_inputs_json = a.substr(19);
@RESET_ARGS@@COUNT_ARGS@            else
                argv[n++] = argv[i];
        }
        argc = n;
    }
    if (argc < 5 || argc > 7) {
        fprintf(stderr,
                "usage: %s <capture.vcd> <out> <window_start> <clk_period> "
                "[<window_end> [<from>=<to>]] [--stubs-vcd=<stubs.vcd>]\n",
                argv[0]);
        return 2;
    }
    const uint64_t end = argc > 5 ? strtoull(argv[5], nullptr, 0) : 0;
    std::string from, to;
    if (argc > 6) {
        std::string m = argv[6];
        from = m.substr(0, m.find('='));
        to = m.substr(m.find('=') + 1);
    }
    Verilated::commandArgs(argc, argv);
    std::ifstream vcd(argv[1]);
    const uint64_t start = strtoull(argv[3], nullptr, 0);
    const uint64_t period = strtoull(argv[4], nullptr, 0);

    // the header: each captured signal's id code
    std::map<std::string, std::size_t> by_name;
    for (std::size_t i = 0; i < kCount; i++) {
        std::string n = kSigs[i].capture;
        if (!from.empty() && n.compare(0, from.size(), from) == 0) n = to + n.substr(from.size());
        by_name[n] = i;
    }
    std::map<std::string, std::vector<std::size_t>> by_id;
    std::vector<std::string> scope;
    std::string line;
    while (std::getline(vcd, line)) {
        std::istringstream ss(line);
        std::string tok;
        ss >> tok;
        if (tok == "$scope") {
            std::string kind, name;
            ss >> kind >> name;
            scope.push_back(name);
        } else if (tok == "$upscope") {
            scope.pop_back();
        } else if (tok == "$var") {
            std::string type, width, id, name;
            ss >> type >> width >> id >> name;
            std::string full;
            for (const auto& s : scope) full += s + ".";
            full += name;
            auto it = by_name.find(full);
            if (it != by_name.end()) by_id[id].push_back(it->second);
        } else if (tok == "$enddefinitions") {
            break;
        }
    }
    std::vector<bool> seen(kCount, false);
    for (const auto& [id, list] : by_id)
        for (auto i : list) seen[i] = true;
    int missing = 0;
    for (std::size_t i = 0; i < kCount; i++) {
        if (!seen[i] && kSigs[i].role != kRec) {
            fprintf(stderr, "replay: %s is not in the capture\n", kSigs[i].capture);
            missing++;
        }
    }
    if (missing) return 1;

    V* d = new V;
    Verilated::traceEverOn(true);
    Trace* saif = new Trace;
    d->trace(saif, 99);
    bool open = false;
    StubsVcd stubs;
    if (!stubs_path.empty()) stubs.open(stubs_path.c_str());

    std::vector<Words> value(kCount);
    uint64_t xs = 0, steps = 0, compared = 0;
    // per checked signal, the bits compared
    std::vector<Words> mask(kCount);
    for (std::size_t i = 0; i < kCount; i++)
        mask[i] = masked(Words((kSigs[i].width + 31) / 32, ~0u), kSigs[i].width);
    for (std::size_t k = 0; k < kExemptCount; k++)
        mask[kExempt[k].sig][kExempt[k].bit / 32] &= ~(1u << (kExempt[k].bit % 32));
    // per stub input: cycles it differed in, and the first one's values
    std::vector<uint64_t> differ_cycles(kCount, 0), last_cycle(kCount, ~0ull),
        first_cycle(kCount, 0);
    std::vector<Words> first_captured(kCount), first_netlist(kCount);
@RESET_DECL@@COUNT_DECL@    auto step = [&](uint64_t t) -> bool {
@RESET_STEP@        for (std::size_t i = 0; i < kCount; i++)
            if (kSigs[i].role == kClock) kSigs[i].set(d, value[i]);
        d->eval();
        for (std::size_t i = 0; i < kCount; i++)
            if (kSigs[i].role == kIn) kSigs[i].set(d, value[i]);
        d->eval();
        Words got;
        for (std::size_t i = 0; i < kCount; i++) {
            if (kSigs[i].role != kOut && kSigs[i].role != kStubIn) continue;
@RESET_CHECK@            kSigs[i].read(d, got);
            Words a = masked(got, kSigs[i].width), b = masked(value[i], kSigs[i].width);
            for (std::size_t w = 0; w < a.size(); w++) {
                a[w] &= mask[i][w];
                b[w] &= mask[i][w];
            }
            compared++;
            if (a != b && kSigs[i].role == kStubIn && !strict_stub_inputs) {
                const uint64_t c = t / period;
                if (last_cycle[i] != c) {
                    if (!differ_cycles[i]) {
                        first_cycle[i] = c;
                        first_captured[i] = b;
                        first_netlist[i] = a;
                    }
                    differ_cycles[i]++;
                    last_cycle[i] = c;
                }
                continue;
            }
@COUNT_CHECK@            if (a != b) {
                fprintf(stderr,
                        "replay: %s differs at cycle %llu (time %llu, clock %s): "
                        "captured %s, netlist %s\n",
                        kSigs[i].capture, (unsigned long long)(t / period),
                        (unsigned long long)t, (t % period) ? "high" : "low",
                        hex(b).c_str(), hex(a).c_str());
                return false;
            }
        }
        if (stubs.f) {
            fprintf(stubs.f, "#%llu\n", (unsigned long long)t);
            for (std::size_t k = 0; k < kTraceCount; k++) {
                const Sig& s = kSigs[kTrace[k].sig];
                Words v;
                if (s.role == kOut || s.role == kRec || s.role == kStubIn)
                    s.read(d, v);
                else
                    v = value[kTrace[k].sig];
                v = masked(v, s.width);
                if (!stubs.first && v == stubs.last[k]) continue;
                stubs.last[k] = v;
                std::string bits;
                for (int b = s.width; b-- > 0;) bits += (v[b / 32] >> (b % 32)) & 1 ? '1' : '0';
                if (s.width > 1)
                    fprintf(stubs.f, "b%s %s\n", bits.c_str(), vcd_id(k).c_str());
                else
                    fprintf(stubs.f, "%s%s\n", bits.c_str(), vcd_id(k).c_str());
            }
            stubs.first = false;
        }
#if VM_TRACE_VCD
        if (!open) {
            saif->open(argv[2]);
            open = true;
        }
        saif->dump(t);
#else
        if (t >= start && (end == 0 || t < end)) {
            if (!open) {
                saif->open(argv[2]);
                open = true;
            }
            saif->dump(t - start);
        }
#endif
        steps++;
        return true;
    };

    bool have = false;
    uint64_t t = 0;
    while (std::getline(vcd, line)) {
        if (line.empty() || line[0] == '$') continue;
        if (line[0] == '#') {
            if (have && !step(t)) return 1;
            t = strtoull(line.c_str() + 1, nullptr, 10);
            have = true;
            continue;
        }
        std::string bits, id;
        if (line[0] == 'b' || line[0] == 'B') {
            std::size_t sp = line.find(' ');
            bits = line.substr(1, sp - 1);
            id = line.substr(sp + 1);
        } else {
            bits = line.substr(0, 1);
            id = line.substr(1);
        }
        auto it = by_id.find(id);
        if (it == by_id.end()) continue;
        Words w((bits.size() + 31) / 32, 0);
        for (std::size_t k = 0; k < bits.size(); k++) {
            char c = bits[bits.size() - 1 - k];
            if (c == '1') w[k / 32] |= 1u << (k % 32);
            else if (c != '0') xs++;
        }
        for (auto i : it->second) value[i] = w;
    }
    if (have && !step(t)) return 1;
    if (open) saif->close();
    if (stubs.f) fclose(stubs.f);
    // the report: the bits the netlist fixed, never compared
    fprintf(stderr,
            "replay: %zu checked bits never compared, fixed by the netlist (a tie cell, a "
            "constant, no driver)\n",
            kExemptCount);
    for (std::size_t k = 0; k < kExemptCount && k < 20; k++) {
        const Exempt& e = kExempt[k];
        if (e.value < 0)
            fprintf(stderr, "replay: not compared, %s: %s[%d]\n", e.reason,
                    kSigs[e.sig].capture, e.bit);
        else
            fprintf(stderr, "replay: not compared, %s %d: %s[%d]\n", e.reason, e.value,
                    kSigs[e.sig].capture, e.bit);
    }
    // the stub inputs that differed from the RTL, most cycles first
    std::vector<std::size_t> differ;
    uint64_t differ_total = 0;
    for (std::size_t i = 0; i < kCount; i++)
        if (differ_cycles[i]) {
            differ.push_back(i);
            differ_total += differ_cycles[i];
        }
    std::stable_sort(differ.begin(), differ.end(), [&](std::size_t a, std::size_t b) {
        return differ_cycles[a] > differ_cycles[b];
    });
    for (std::size_t k = 0; k < differ.size() && k < 20; k++) {
        std::size_t i = differ[k];
        fprintf(stderr,
                "replay: stub input %s differs in %llu cycles, first at cycle %llu: captured %s, "
                "netlist %s\n",
                kSigs[i].capture, (unsigned long long)differ_cycles[i],
                (unsigned long long)first_cycle[i], hex(first_captured[i]).c_str(),
                hex(first_netlist[i]).c_str());
    }
    std::size_t stub_inputs = 0;
    for (std::size_t i = 0; i < kCount; i++) stub_inputs += kSigs[i].role == kStubIn;
    if (stub_inputs)
        fprintf(stderr,
                "replay: stub inputs differing from the RTL: %zu signals, %llu cycles; not "
                "required to match, each piece's outputs are (level 2)\n",
                differ.size(), (unsigned long long)differ_total);
    if (!stub_inputs_json.empty()) {
        FILE* j = fopen(stub_inputs_json.c_str(), "w");
        if (!j) {
            fprintf(stderr, "replay: cannot write %s\n", stub_inputs_json.c_str());
            return 1;
        }
        fprintf(j, "{\"signals\": %zu, \"cycles\": %llu, \"top\": [", differ.size(),
                (unsigned long long)differ_total);
        for (std::size_t k = 0; k < differ.size() && k < 20; k++) {
            std::size_t i = differ[k];
            fprintf(j,
                    "%s\n  {\"signal\": %s, \"cycles\": %llu, \"first_cycle\": %llu, "
                    "\"captured\": \"%s\", \"netlist\": \"%s\"}",
                    k ? "," : "", json_str(kSigs[i].capture).c_str(),
                    (unsigned long long)differ_cycles[i], (unsigned long long)first_cycle[i],
                    hex(first_captured[i]).c_str(), hex(first_netlist[i]).c_str());
        }
        fprintf(j, "]}\n");
        fclose(j);
    }
@RESET_REPORT@@COUNT_REPORT@    fprintf(stderr, "replay: %llu times, %llu comparisons, all equal%s; %llu x/z capture bits taken "
            "as 0\n",
            (unsigned long long)steps, (unsigned long long)compared,
            differ.empty() ? "" : " but the stub inputs above", (unsigned long long)xs);
    d->final();
    delete saif;
    delete d;
    return 0;
}
"""


# --count-outputs: a piece's outputs that differ from the RTL counted, not
# fatal, the run going on to its SAIF; inserted at the placeholders of
# _HARNESS, which are empty otherwise.
_COUNT = {
    "@COUNT_ARGDECL@": """    // --count-outputs: where to write the outputs that differed
    std::string outputs_json;
""",
    "@COUNT_ARGS@": """            else if (a.compare(0, 15, "--outputs-json=") == 0)
                outputs_json = a.substr(15);
""",
    "@COUNT_DECL@": """    // per checked output: cycles it differed in, the first one's values
    std::vector<uint64_t> out_cycles(kCount, 0), out_last(kCount, ~0ull), out_first(kCount, 0);
    std::vector<Words> out_captured(kCount), out_netlist(kCount);
""",
    "@COUNT_CHECK@": """            if (a != b && kSigs[i].role == kOut) {
                // counted, not fatal (--count-outputs)
                const uint64_t c = t / period;
                if (out_last[i] != c) {
                    if (!out_cycles[i]) {
                        out_first[i] = c;
                        out_captured[i] = b;
                        out_netlist[i] = a;
                    }
                    out_cycles[i]++;
                    out_last[i] = c;
                }
                continue;
            }
""",
    "@COUNT_REPORT@": """    // the outputs that differed from the RTL, most cycles first
    {
        std::vector<std::size_t> outs;
        uint64_t total = 0;
        std::size_t first = kCount;
        for (std::size_t i = 0; i < kCount; i++)
            if (out_cycles[i]) {
                outs.push_back(i);
                total += out_cycles[i];
                if (first == kCount || out_first[i] < out_first[first]) first = i;
            }
        std::stable_sort(outs.begin(), outs.end(), [&](std::size_t a, std::size_t b) {
            return out_cycles[a] > out_cycles[b];
        });
        for (std::size_t k = 0; k < outs.size() && k < 20; k++) {
            std::size_t i = outs[k];
            fprintf(stderr,
                    "replay: output %s differs in %llu cycles, first at cycle %llu: captured %s, "
                    "netlist %s\\n",
                    kSigs[i].capture, (unsigned long long)out_cycles[i],
                    (unsigned long long)out_first[i], hex(out_captured[i]).c_str(),
                    hex(out_netlist[i]).c_str());
        }
        if (outs.empty())
            fprintf(stderr, "replay: outputs differing from the RTL: 0 signals, 0 cycles\\n");
        else
            fprintf(stderr,
                    "replay: outputs differing from the RTL: %zu signals, %llu cycles; first at "
                    "cycle %llu: %s\\n",
                    outs.size(), (unsigned long long)total, (unsigned long long)out_first[first],
                    kSigs[first].capture);
        if (!outputs_json.empty()) {
            FILE* j = fopen(outputs_json.c_str(), "w");
            if (!j) {
                fprintf(stderr, "replay: cannot write %s\\n", outputs_json.c_str());
                return 1;
            }
            fprintf(j, "{\\"signals\\": %zu, \\"cycles\\": %llu, \\"first_cycle\\": ", outs.size(),
                    (unsigned long long)total);
            if (outs.empty())
                fprintf(j, "null, \\"first_signal\\": null");
            else
                fprintf(j, "%llu, \\"first_signal\\": %s", (unsigned long long)out_first[first],
                        json_str(kSigs[first].capture).c_str());
            fprintf(j, ", \\"top\\": [");
            for (std::size_t k = 0; k < outs.size() && k < 20; k++) {
                std::size_t i = outs[k];
                fprintf(j,
                        "%s\\n  {\\"signal\\": %s, \\"cycles\\": %llu, \\"first_cycle\\": %llu, "
                        "\\"captured\\": \\"%s\\", \\"netlist\\": \\"%s\\"}",
                        k ? "," : "", json_str(kSigs[i].capture).c_str(),
                        (unsigned long long)out_cycles[i], (unsigned long long)out_first[i],
                        hex(out_captured[i]).c_str(), hex(out_netlist[i]).c_str());
            }
            fprintf(j, "]}\\n");
            fclose(j);
        }
        if (!outs.empty()) {
            fprintf(stderr,
                    "replay: %llu times, %llu comparisons, outputs differing as above "
                    "(--count-outputs); %llu x/z capture bits taken as 0\\n",
                    (unsigned long long)steps, (unsigned long long)compared,
                    (unsigned long long)xs);
            d->final();
            delete saif;
            delete d;
            return 0;
        }
    }
""",
}


def _harness_count(harness, count_outputs):
    for k, v in _COUNT.items():
        harness = harness.replace(k, v if count_outputs else "")
    return harness


# --compare-from-reset: a piece's checked outputs compared only from the
# cycle after the captured reset first falls (asserted, then released):
# before it, the values are the simulators' initial ones, not the
# design's. Inserted at the placeholders of _HARNESS, empty otherwise;
# @RESET@ is the reset input's row in kSigs.
_FROM_RESET = {
    "@RESET_ARGDECL@": """    // --compare-from-reset: where to write the cycle comparing began
    std::string from_reset_json;
""",
    "@RESET_ARGS@": """            else if (a.compare(0, 18, "--from-reset-json=") == 0)
                from_reset_json = a.substr(18);
""",
    "@RESET_DECL@": """    // the captured reset: asserted once, then released at reset_fall;
    // checked outputs compared from the cycle after
    const std::size_t kReset = @RESET@;
    bool reset_seen = false, reset_fell = false;
    uint64_t reset_fall = 0, from_cycle = 0;
""",
    "@RESET_STEP@": """        if (!reset_fell) {
            const bool r = !value[kReset].empty() && (value[kReset][0] & 1);
            if (r) {
                reset_seen = true;
            } else if (reset_seen) {
                reset_fell = true;
                reset_fall = t;
                from_cycle = t / period + 1;
                fprintf(stderr,
                        "replay: %s falls at time %llu: outputs compared from cycle %llu\\n",
                        kSigs[kReset].capture, (unsigned long long)t,
                        (unsigned long long)from_cycle);
            }
        }
""",
    "@RESET_CHECK@": """            if (kSigs[i].role == kOut && !(reset_fell && t / period >= from_cycle)) continue;
""",
    "@RESET_REPORT@": """    if (!reset_fell) {
        fprintf(stderr,
                "replay: %s was never asserted and released in the capture: no output "
                "compared (--compare-from-reset)\\n",
                kSigs[kReset].capture);
        return 1;
    }
    fprintf(stderr,
            "replay: compared from cycle %llu (the cycle after the captured reset first falls, "
            "at time %llu)\\n",
            (unsigned long long)from_cycle, (unsigned long long)reset_fall);
    if (!from_reset_json.empty()) {
        FILE* j = fopen(from_reset_json.c_str(), "w");
        if (!j) {
            fprintf(stderr, "replay: cannot write %s\\n", from_reset_json.c_str());
            return 1;
        }
        fprintf(j, "{\\"reset\\": %s, \\"reset_falls_at\\": %llu, \\"compared_from_cycle\\": %llu}\\n",
                json_str(kSigs[kReset].capture).c_str(), (unsigned long long)reset_fall,
                (unsigned long long)from_cycle);
        fclose(j);
    }
""",
}


def _harness_reset(harness, reset):
    """`harness` with the --compare-from-reset code, `reset` the reset
    input's row, or without it (None)."""
    for k, v in _FROM_RESET.items():
        harness = harness.replace(
            k, "" if reset is None else v.replace("@RESET@", str(reset))
        )
    return harness


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--top", required=True)
    parser.add_argument("--netlist", required=True)
    parser.add_argument("--rtl", required=True, action="append")
    parser.add_argument("--capture-scope", required=True)
    parser.add_argument("--child", action="append", default=[])
    parser.add_argument("--clock-port", action="append", default=[])
    parser.add_argument(
        "--clock-net",
        action="append",
        default=[],
        help="a pattern of the clock tree's leaf nets a kept module's ports are named after",
    )
    parser.add_argument("--out-sv", required=True)
    parser.add_argument("--out-cc", required=True)
    parser.add_argument("--report")
    parser.add_argument(
        "--path", default="", help="the shard's instance path in the unit"
    )
    parser.add_argument("--out-netlist", required=True, help="the dut's netlist")
    parser.add_argument(
        "--record-stubs",
        action="store_true",
        help="level 1 of a two-level replay: a harness that can record the stubs' ports",
    )
    parser.add_argument(
        "--compare-from-reset",
        action="store_true",
        help="a two-level replay whose outputs are compared from the cycle after "
        "the captured reset first falls",
    )
    parser.add_argument(
        "--count-outputs",
        action="store_true",
        help="a two-level replay whose differing outputs are counted, not fatal",
    )
    parser.add_argument(
        "--out-stubs", help="the stubs' map, JSON: path -> scope, punched, dropped"
    )
    parser.add_argument(
        "--stub-map", help="level 1's --out-stubs: replay --path from its stubs VCD"
    )
    args = parser.parse_args(argv)
    stub_map = None
    if args.stub_map:
        with open(args.stub_map) as f:
            maps = json.load(f)
        if args.path not in maps:
            sys.stderr.write(
                "replay_gen: {} has no stub {}\n".format(args.stub_map, args.path)
            )
            return 1
        stub_map = maps[args.path]
    with open(args.netlist) as f:
        netlist = f.read()
    rtl = ""
    for path in args.rtl:
        with open(path) as f:
            rtl += f.read() + "\n"
    children = [tuple(c.split("=", 1)) for c in args.child]
    try:
        sv, cc, report, dut_netlist = generate(
            args.name,
            args.top,
            netlist,
            rtl,
            args.capture_scope,
            children,
            args.clock_port,
            args.path,
            args.clock_net,
            stub_map,
            args.record_stubs,
            args.count_outputs,
            args.compare_from_reset,
        )
    except ValueError as e:
        sys.stderr.write("replay_gen: " + "\n  ".join(e.args[0]) + "\n")
        return 1
    with open(args.out_sv, "w") as f:
        f.write(sv)
    with open(args.out_cc, "w") as f:
        f.write(cc)
    with open(args.out_netlist, "w") as f:
        f.write(dut_netlist)
    if args.out_stubs:
        with open(args.out_stubs, "w") as f:
            json.dump(report["stubs"], f, indent=2, sort_keys=True)
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
