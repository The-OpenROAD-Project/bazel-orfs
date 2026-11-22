#!/usr/bin/env python3
"""Assemble the RTL a gate-level netlist still needs to simulate.

A hierarchical parent's netlist instantiates its hardened blocks and its
SRAM macros as cells: module names with no body. The behavioural models
for both are the RTL modules of the same names, one file each in the
split-Verilog directory firtool wrote. The uncore around the core -- the
SoC wrapper, the bus, the memory behind DPI -- is RTL too. So the file
this writes is the closure of RTL modules reachable from the simulation
top, stopping at every module the netlist defines (the core itself), plus
the closure of every module the netlist instantiates but does not define
(the blocks, the memories), stopping nowhere.

Standard cells are the one kind of undefined name that is allowed: they
come from the cell-model library, and they are recognised by a suffix
(--cell-suffix). Any other undefined name with no RTL file is an error,
listed by name, because a module that silently vanishes from a
simulation is a memory that stores nothing.

Gate netlists of the hardened units (--gate-netlist, repeatable): for a
power measured in shards (flow/power.bzl's stage_power_shards) each
hardened block and generated register file is simulated as its own
global-route netlist, under the instance the parent netlist has it at,
so the SAIF holds its cells where its shard reads them. A gate
netlist's modules stop the RTL closure as the parent netlist's do, the
modules it instantiates but does not define (its SRAMs) are filled from
RTL, and it is written after the RTL into --out. Its top, the one module
nothing in it instantiates, keeps its name, the unit's; every other
module it defines is renamed `<top>__<module>` there, so the
submodules of two units' hierarchical netlists, which write_verilog
names after the same RTL, cannot collide. Refused, by name: a gate
netlist without exactly one top, two with one top, a top the parent
netlist also defines, a renamed module the parent netlist defines, and a
gate netlist nothing instantiates. Without --gate-netlist nothing
changes.

One simulation per unit: without --netlist the top and everything under
it are RTL, but for the gate netlists. A unit swapped in that way sits at
its own RTL instance path, every other unit is RTL.

RTL as files of several modules (--rtl-file, repeatable, beside or
instead of --rtl-dir): a later file's module replaces an earlier one's,
and the report lists every module replaced.

The clock (--clock-port, repeatable: the port names the SDC puts the
design's one clock on). A hardened unit's netlist need not have its RTL
module's clock ports: a flow can split one clock port into several, and
the parent netlist then connects several clock pins of a unit the RTL
has one of. Where a netlist meets RTL, the two are bridged at the clock
and nowhere else, without a level of hierarchy, so a SAIF scope is the
same either way:

  - a gate unit instantiated from RTL: a clock port of the netlist's top
    the RTL module lacks becomes a wire driven by the RTL module's one
    clock port, and an RTL clock port the netlist lacks becomes an
    unused input of the top;
  - an RTL module instantiated from a gate netlist on a clock pin it
    lacks: the pin becomes an unused input of the module.

RTL that differs below a module (--rtl-overlay, --overlay-root): the
flows synthesise a transformed copy of the design below the root, whose
modules' ports the netlists have (for XiangShan the surgered core below
XSTile); the overlay supplies every module at and below the root, the
base the rest, and a module both use keeps the base's name above the
root and is renamed <name>__<root> below it.

Every instance is checked against the module it resolves to, whatever
it came from: a pin the module does not have, or an input the instance
leaves unconnected, is refused by name (Verilator would only warn, and
leave the input 0). An input the design leaves unconnected on purpose
is tied by name (--tie MODULE.PORT=VALUE): XiangShan's SoC elaboration
ties XSTile's NMI inputs to 0 in Chisel and firtool removes them there,
while the core the flows harden from keeps them.

Any other difference between a netlist top's ports and its RTL module's,
or a pin an RTL module lacks, is refused by name; so is a gate unit
instantiated both from RTL and from a netlist.
"""

import argparse
import json
import os
import re
import sys

_MODULE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z_0-9$]*)", re.M)
# `Foo foo_inst (` or `Foo #(...) foo_inst (`, at the start of a line.
_INSTANCE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z_0-9$]*)\s+(?:#\([^;]*?\)\s*)?[A-Za-z_\\][^\s(]*\s*\(", re.M
)
_KEYWORDS = {
    "module",
    "input",
    "output",
    "inout",
    "wire",
    "reg",
    "assign",
    "always",
    "initial",
    "parameter",
    "localparam",
    "logic",
    "integer",
    "genvar",
    "function",
    "task",
    "if",
    "else",
    "for",
    "case",
    "endmodule",
    "begin",
    "end",
    "posedge",
    "negedge",
    "typedef",
    "generate",
    "endgenerate",
    "unique",
    "priority",
    "default",
    "return",
    "automatic",
}


def instantiated(text):
    """Module names in instantiation position, keywords excluded."""
    return {m for m in _INSTANCE.findall(text) if m not in _KEYWORDS}


def rtl_index(directory):
    """Module name -> path, for every .sv/.v file in the directory."""
    index = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith((".sv", ".v")):
            continue
        stem = name.rsplit(".", 1)[0]
        index[stem] = os.path.join(directory, name)
    return index


_MODULE_TEXT = re.compile(
    r"^\s*module\s+([A-Za-z_][A-Za-z_0-9$]*).*?^\s*endmodule\b[^\n]*\n?", re.M | re.S
)


def rtl_files(paths, index=None):
    """(module name -> its text, modules a later file replaced), each
    file split at its modules; later files win."""
    index = dict(index or {})
    replaced = []
    for path in paths:
        with open(path, errors="replace") as f:
            text = f.read()
        for m in _MODULE_TEXT.finditer(text):
            if m.group(1) in index:
                replaced.append(m.group(1))
            index[m.group(1)] = ("text", m.group(0))
    return index, sorted(set(replaced))


def read_rtl(entry):
    """An index entry's text: a path, or ("text", text)."""
    if isinstance(entry, tuple):
        return entry[1]
    with open(entry, errors="replace") as f:
        return f.read()


_PORT = re.compile(
    r"\b(?:input|output|inout)\b(?:\s+(?:wire|reg|logic|signed))*\s*"
    r"(?:\[[^\]]*\]\s*)*(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)"
)


_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


_DIRECTION = re.compile(r"^\s*(input|output|inout)\b")
_RANGE = re.compile(r"\[[^\]]*\]")
_HEADER = re.compile(
    r"module\s+(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;", re.S
)


def _split_top(text):
    """`text` split at the commas outside brackets and parentheses."""
    items, depth, cur = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur))
    return [i.strip() for i in items if i.strip()]


def _width(rng):
    m = re.match(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", rng)
    return abs(int(m.group(1)) - int(m.group(2))) + 1 if m else 1


def port_decls(module_text):
    """{port: (direction, width)} of one module, ANSI or not.

    A declaration may name several ports (firtool writes `input [5:0] a,`
    and then `b,` on the next line): each takes the direction and range of
    the last one written out.
    """
    text = _COMMENT.sub("", module_text)
    m = _HEADER.search(text)
    if not m:
        return {}
    out = {}
    header = m.group(2)
    if re.search(r"\b(input|output|inout)\b", header):
        items = _split_top(header)
    else:
        items = []
        body = text[m.end() :]
        for d in re.finditer(r"\b(input|output|inout)\b([^;]*);", body):
            names = _split_top(d.group(2))
            items.append(d.group(1) + " " + names[0])
            items += names[1:]
    direction, rng = None, ""
    for item in items:
        dm = _DIRECTION.match(item)
        if dm:
            direction = dm.group(1)
            rest = item[dm.end() :]
            rest = re.sub(r"\b(wire|reg|logic|signed|unsigned)\b", " ", rest)
            ranges = _RANGE.findall(rest)
            rng = ranges[0] if ranges else ""
            rest = _RANGE.sub(" ", rest)
        else:
            rest = item
        name = rest.split()[-1] if rest.split() else None
        if direction and name and name not in _KEYWORDS:
            out[name] = (direction, _width(rng))
    return out


def ports(module_text):
    """A module's port names, from its input/output/inout declarations."""
    return set(port_decls(module_text))


_INSTANCE_FULL = re.compile(
    r"^\s*(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)\s+(?:#\s*\(.*?\)\s*)?(\\\S+\s|[A-Za-z_][A-Za-z_0-9$\[\]]*)\s*\((.*?)\);",
    re.M | re.S,
)


def instances(text):
    """[(master, instance, {pin names})] of every named-pin instance."""
    out = []
    for m in _INSTANCE_FULL.finditer(_COMMENT.sub("", text)):
        if m.group(1) in _KEYWORDS:
            continue
        pins = set(re.findall(r"\.(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)\s*\(", m.group(3)))
        if pins:
            out.append((m.group(1), m.group(2).strip(), pins))
    return out


def check_pins(texts, ties=None):
    """Every instance against the module it resolves to, among `texts`:
    a pin the module lacks, or an input of the module the instance leaves
    unconnected, is a list of refusals. A port named in `ties` (module ->
    {port: value}) is connected to its value instead, in the text
    returned. Returns (texts with the ties made, refusals, ties made)."""
    ties = ties or {}
    defs = {}
    for t in texts:
        for m in re.finditer(
            r"^\s*module\s+(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)\b.*?^\s*endmodule\b",
            t,
            re.M | re.S,
        ):
            defs[m.group(1)] = port_decls(m.group(0))
    refused = []
    made = []
    out = []
    for t in texts:
        for master, inst, pins in instances(t):
            if master not in defs:
                continue
            declared = defs[master]
            extra = sorted(pins - set(declared))
            if extra:
                refused.append(
                    "{} {}: pins {} that {} does not have".format(
                        master, inst, ", ".join(extra), master
                    )
                )
            missing = sorted(
                p for p, (d, _) in declared.items() if d == "input" and p not in pins
            )
            tie = ties.get(master, {})
            untied = [p for p in missing if p not in tie]
            if untied:
                refused.append(
                    "{} {}: inputs {} unconnected".format(
                        master, inst, ", ".join(untied)
                    )
                )
            fill = [p for p in missing if p in tie]
            if fill:
                head = re.search(
                    r"^\s*"
                    + re.escape(master)
                    + r"\s+(?:#\s*\(.*?\)\s*)?"
                    + re.escape(inst)
                    + r"\s*\(",
                    t,
                    re.M | re.S,
                )
                t = (
                    t[: head.end()]
                    + "".join(".{}({}), ".format(p, tie[p]) for p in fill)
                    + t[head.end() :]
                )
                made.append(
                    "{} {}: {}".format(
                        master, inst, ", ".join("{}={}".format(p, tie[p]) for p in fill)
                    )
                )
        out.append(t)
    return out, refused, made


def rename_masters(text, renames, keep=()):
    """`text` with each module definition and instantiation named in
    `renames` renamed, but for the names in `keep`."""

    def name(n):
        return renames.get(n, n) if n not in keep else n

    text = _GATE_MODULE.sub(lambda m: m.group(1) + name(m.group(2)), text)
    return _GATE_INSTANCE.sub(
        lambda m: m.group(1) + name(m.group(2)) + m.group(3), text
    )


def apply_overlay(base, overlay_paths, root, top):
    """(index, renames): `base` with the overlay's modules for everything
    at and below `root`.

    The overlay is the RTL a design's flows synthesise below `root` (for
    XiangShan the surgered core under XSTile, whose ports the hardened
    units' netlists have), the base the RTL around it. A module the base
    uses above `root` and the overlay defines too keeps the base's under
    its name; the overlay's is renamed `<name>__<root>`, in every overlay
    module that instantiates it.
    """
    overlay, _ = rtl_files(overlay_paths)
    above = set()
    stack = [top]
    while stack:
        m = stack.pop()
        if m in above or m == root or m not in base:
            continue
        above.add(m)
        stack += list(instantiated(read_rtl(base[m])))
    renames = {m: "{}__{}".format(m, root) for m in overlay if m in above and m != root}
    index = dict(base)
    for m, entry in overlay.items():
        text = rename_masters(read_rtl(entry), renames)
        index[renames.get(m, m)] = ("text", text)
    return index, renames


def instance_pins(text, master):
    """Every pin name an instance of `master` connects in `text`."""
    pins = set()
    pattern = re.compile(
        r"^\s*" + re.escape(master) + r"\s+(?:#\(.*?\)\s*)?\S+\s*\((.*?)\);",
        re.M | re.S,
    )
    for m in pattern.finditer(text):
        pins |= set(re.findall(r"\.(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)\s*\(", m.group(1)))
    return pins


def add_input_ports(module_text, names):
    """The module with `names` as extra inputs, ANSI header or not."""
    m = re.search(r"module\s+\S+?\s*(?:#\s*\(.*?\)\s*)?\(", module_text, re.S)
    head, rest = module_text[: m.end()], module_text[m.end() :]
    ansi = re.match(r"\s*(?:input|output|inout)\b", rest)
    if ansi:
        return head + "".join("\n    input {},".format(n) for n in names) + rest
    end = rest.index(";")
    decl = "".join("\n  input {};".format(n) for n in names)
    return (
        head
        + "".join("{}, ".format(n) for n in names)
        + rest[: end + 1]
        + decl
        + rest[end + 1 :]
    )


def bridge_netlist_clocks(text, top, extra, clock):
    """The netlist top with each port in `extra` a wire driven by `clock`."""
    m = re.search(
        r"^\s*module\s+" + re.escape(top) + r"\s*\((.*?)\);", text, re.M | re.S
    )
    names = [n.strip() for n in m.group(1).split(",")]
    kept = [n for n in names if n not in extra]
    text = text[: m.start(1)] + ", ".join(kept) + text[m.end(1) :]
    for name in extra:
        decl = re.compile(r"^(\s*)input\s+" + re.escape(name) + r"\s*;", re.M)
        text, n = decl.subn(
            lambda d: "{0}wire {1};\n{0}assign {1} = {2};".format(
                d.group(1), name, clock
            ),
            text,
            count=1,
        )
        if n != 1:
            raise ValueError(["{}: no input declaration of {}".format(top, name)])
    return text


# a gate netlist's module and master names, escaped ones included
_NAME = r"(\\\S+|[A-Za-z_][A-Za-z_0-9$]*)"
_GATE_MODULE = re.compile(r"^(\s*module\s+)" + _NAME, re.M)
_GATE_INSTANCE = re.compile(
    r"^(\s*)" + _NAME + r"(\s+(?:#\([^;]*?\)\s*)?[A-Za-z_\\][^\s(]*\s*\()", re.M
)


def _GATE_MODULE_NAMES(text):
    return [m.group(2) for m in _GATE_MODULE.finditer(text)]


def gate_unit(text):
    """(top, text with every other module renamed <top>__<module>, defined)."""
    defined = [m.group(2) for m in _GATE_MODULE.finditer(text)]
    inside = {m.group(2) for m in _GATE_INSTANCE.finditer(text)} - _KEYWORDS
    tops = sorted(set(defined) - inside)
    if len(tops) != 1:
        raise ValueError(["a gate netlist with tops {}".format(tops or "none")])
    top = tops[0]

    def renamed(name):
        if name == top or name not in defined:
            return name
        if name.startswith("\\"):
            return "\\" + top.lstrip("\\") + "__" + name[1:]
        return top + "__" + name

    text = _GATE_MODULE.sub(lambda m: m.group(1) + renamed(m.group(2)), text)
    text = _GATE_INSTANCE.sub(
        lambda m: m.group(1) + renamed(m.group(2)) + m.group(3), text
    )
    return top, text, {renamed(d) for d in defined}


def _gate_top_text(text, top):
    m = re.search(
        r"^\s*module\s+" + re.escape(top) + r"\b.*?^\s*endmodule", text, re.M | re.S
    )
    return m.group(0)


def stitch(
    netlist_text, rtl, top, cell_suffixes, gate_texts=(), clock_ports=(), ties=None
):
    """Return (ordered module names to include, report dict, gate texts).

    Raises ValueError with the offending names when an instantiated
    module has neither a netlist body, an RTL file nor a cell suffix, or
    when a gate netlist is refused (see the module's docstring).
    """
    defined = set(_MODULE.findall(netlist_text))
    from_netlist = instantiated(netlist_text) - defined

    gates = []
    refused = []
    parent_defined = set(defined)
    tops = {}
    top_of = []
    for text in gate_texts:
        unit, renamed, unit_defined = gate_unit(text)
        top_of.append(unit)
        if unit in tops:
            refused.append("two gate netlists define {}".format(unit))
        if unit in parent_defined:
            refused.append("{} is defined in the parent netlist too".format(unit))
        for name in sorted((unit_defined - {unit}) & parent_defined):
            refused.append("{} is defined in the parent netlist too".format(name))
        tops[unit] = len(unit_defined)
        gates.append(renamed)
        defined |= unit_defined
    if refused:
        raise ValueError(refused)
    for text in gates:
        from_netlist |= instantiated(text)
    # escaped masters too: a kept module of a hierarchical netlist is
    # named \\<Module>$<path>, and a replay's top instantiates one
    from_gates = instantiated(netlist_text) | (
        {m.group(2) for m in _GATE_INSTANCE.finditer(netlist_text)} - _KEYWORDS
    )
    for text in gates:
        from_gates |= {m.group(2) for m in _GATE_INSTANCE.finditer(text)}
    from_netlist -= defined

    included = []
    seen = set()
    missing = set()
    from_rtl = set()

    def walk(name):
        if name in defined:
            from_rtl.add(name)
            return
        if name in seen:
            return
        seen.add(name)
        if name not in rtl:
            if not any(name.endswith(s) or s in name for s in cell_suffixes):
                missing.add(name)
            return
        for child in sorted(instantiated(read_rtl(rtl[name]))):
            walk(child)
        included.append(name)

    if top in defined:
        from_rtl.discard(top)
    else:
        walk(top)
    uncore = len(included)
    for name in sorted(from_netlist):
        walk(name)

    if missing:
        raise ValueError(sorted(missing))
    unused = sorted(set(tops) - from_gates - from_rtl)
    if unused:
        raise ValueError(
            ["gate netlist {} is instantiated nowhere".format(u) for u in unused]
        )

    # the clock bridges, and every other port difference refused
    clocks = set(clock_ports)
    patched = {}
    bridged = []
    for i, unit in enumerate(top_of):
        if unit not in from_rtl:
            continue
        if unit in from_gates:
            refused.append(
                "{} is instantiated from RTL and from a netlist".format(unit)
            )
            continue
        if unit not in rtl:
            continue
        rtl_ports = ports(read_rtl(rtl[unit]))
        gate_ports = ports(_gate_top_text(gates[i], unit))
        odd = sorted((rtl_ports ^ gate_ports) - clocks)
        if odd:
            refused.append(
                "{}: ports of its netlist and its RTL differ, not at the clock: {}".format(
                    unit, ", ".join(odd)
                )
            )
            continue
        only_gates = sorted(gate_ports - rtl_ports)
        only_rtl = sorted(rtl_ports - gate_ports)
        if only_gates:
            rtl_clock = sorted(rtl_ports & clocks)
            if len(rtl_clock) != 1:
                refused.append(
                    "{}: its RTL has clock ports {}, not one to bridge {} to".format(
                        unit, rtl_clock, only_gates
                    )
                )
                continue
            gates[i] = bridge_netlist_clocks(gates[i], unit, only_gates, rtl_clock[0])
        if only_rtl:
            body = _gate_top_text(gates[i], unit)
            gates[i] = gates[i].replace(body, add_input_ports(body, only_rtl))
        if only_gates or only_rtl:
            bridged.append("{}: netlist {} / RTL {}".format(unit, only_gates, only_rtl))
    gate_all = netlist_text + "".join(gates)
    for name in included:
        if name not in from_netlist and name not in from_gates:
            continue
        pins = instance_pins(gate_all, name)
        if not pins:
            continue
        text = read_rtl(rtl[name])
        lacking = sorted(pins - ports(text))
        odd = [p for p in lacking if p not in clocks]
        if odd:
            refused.append(
                "{}: a netlist connects pins its RTL lacks, not at the clock: {}".format(
                    name, ", ".join(odd)
                )
            )
        elif lacking:
            patched[name] = add_input_ports(text, lacking)
            bridged.append("{}: RTL given {}".format(name, lacking))
    if refused:
        raise ValueError(refused)

    # every instance against its module: a pin the module lacks, or an
    # input left unconnected (Verilator only warns, PINMISSING, and the
    # input is silently 0), is refused; a tie connects it on purpose
    texts = (
        [netlist_text] + [patched.get(n) or read_rtl(rtl[n]) for n in included] + gates
    )
    checked, refused, tied = check_pins(texts, ties)
    if refused:
        raise ValueError(refused)
    if checked[0] != netlist_text:
        raise ValueError(["a tie in the netlist given, which is not written out"])
    for n, before, after in zip(
        included, texts[1 : 1 + len(included)], checked[1 : 1 + len(included)]
    ):
        if after != before:
            patched[n] = after
    gates = checked[1 + len(included) :]
    report = {
        "top": top,
        "netlist_defines": sorted(defined),
        "netlist_instantiates_undefined": sorted(n for n in from_netlist if n in rtl),
        "cells_seen": sorted(n for n in from_netlist if n not in rtl),
        "uncore_modules": uncore,
        "block_and_memory_modules": len(included) - uncore,
        "modules": included,
    }
    if gates:
        report["gate_units"] = tops
    if bridged:
        report["clock_bridges"] = bridged
    if tied:
        report["ties"] = tied
    return included, report, gates, patched


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--netlist", help="the parent's gate-level netlist; none: the top is RTL"
    )
    parser.add_argument("--rtl-dir", help="firtool split-Verilog directory")
    parser.add_argument(
        "--rtl-file",
        action="append",
        default=[],
        help="an RTL file of modules (repeatable); a later one's module wins",
    )
    parser.add_argument(
        "--rtl-overlay",
        action="append",
        default=[],
        help="RTL for everything at and below --overlay-root (repeatable)",
    )
    parser.add_argument("--overlay-root", help="the module the overlay starts at")
    parser.add_argument(
        "--tie",
        action="append",
        default=[],
        help="MODULE.PORT=VALUE: an input every instance of MODULE that leaves "
        "it unconnected is given, by name (repeatable)",
    )
    parser.add_argument(
        "--clock-port",
        action="append",
        default=[],
        help="a port name the SDC puts the one clock on (repeatable)",
    )
    parser.add_argument(
        "--top", required=True, help="simulation top module, e.g. cm_soc"
    )
    parser.add_argument(
        "--cell-suffix",
        action="append",
        default=[],
        help="substring marking a standard cell (repeatable), e.g. _ASAP7_",
    )
    parser.add_argument(
        "--gate-netlist",
        action="append",
        default=[],
        help="a hardened unit's own gate netlist (repeatable)",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", help="JSON summary of what was included")
    args = parser.parse_args(argv[1:])

    netlist_text = ""
    if args.netlist:
        with open(args.netlist, errors="replace") as f:
            netlist_text = f.read()
    rtl, replaced = rtl_files(
        args.rtl_file, rtl_index(args.rtl_dir) if args.rtl_dir else {}
    )
    gate_texts = []
    for path in args.gate_netlist:
        with open(path, errors="replace") as f:
            gate_texts.append(f.read())
    renames = {}
    if args.rtl_overlay:
        if not args.overlay_root:
            print("gate_stitch: --rtl-overlay needs --overlay-root", file=sys.stderr)
            return 1
        rtl, renames = apply_overlay(rtl, args.rtl_overlay, args.overlay_root, args.top)
        # the netlists are below the root: what they instantiate is the
        # overlay's
        netlist_text = rename_masters(
            netlist_text, renames, set(_GATE_MODULE_NAMES(netlist_text))
        )
        gate_texts = [
            rename_masters(t, renames, set(_GATE_MODULE_NAMES(t))) for t in gate_texts
        ]
    try:
        ties = {}
        for t in args.tie:
            target, value = t.split("=", 1)
            module, port = target.rsplit(".", 1)
            ties.setdefault(module, {})[port] = value
        included, report, gates, patched = stitch(
            netlist_text,
            rtl,
            args.top,
            args.cell_suffix,
            gate_texts,
            args.clock_port,
            ties,
        )
    except ValueError as e:
        print(
            "gate_stitch: refused, or modules with no body, no RTL file and no "
            "cell suffix:\n  " + "\n  ".join(e.args[0]),
            file=sys.stderr,
        )
        return 1

    with open(args.out, "w") as out:
        for name in included:
            text = patched.get(name) or read_rtl(rtl[name])
            for line in text.splitlines(True):
                # Every included file is in this concatenation already.
                if line.lstrip().startswith("`include"):
                    continue
                out.write(line)
            out.write("\n")
        for text in gates:
            out.write(text)
            out.write("\n")
    report["rtl_replaced"] = replaced
    report["overlay_renamed"] = sorted(renames)
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    print(
        "gate_stitch: {} uncore modules from {}, {} block/memory modules the "
        "netlist instantiates, {} cell kinds".format(
            report["uncore_modules"],
            args.top,
            report["block_and_memory_modules"],
            len(report["cells_seen"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
