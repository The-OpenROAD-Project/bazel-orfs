#!/usr/bin/env python3
"""Fold the constants XiangShan ties into the modules this flow keeps.

firtool propagates constants across modules, but leaves some on instance
connections; yosys folds those wherever it flattens and cannot across a
boundary the flow keeps (a hardened block, SYNTH_KEEP_MODULES). The
manifest names each one: a module, an input port, the literal every
instance of the module ties it to. For each entry this script

  a) checks the precondition, exactly: the module is defined once and
     instanced exactly `instances` times in the whole file, every instance
     connects the port to `value` (a literal, or a wire its parent declares
     equal to one); anything else stops with the entry named;
  b) does the surgery: the port leaves the module's header and every
     instance's connection list, and the module declares
     `wire <range> <port> = <value>;` in its place.

Entries are applied in round order, each against the text the previous
ones left. A new XiangShan that moves anything makes this fail, never skip.

  xs_surgery.py apply --manifest manifest.json [--protect XSTile] <in.sv> <out.sv>
  xs_surgery.py propose --boundary XSTile_boundary_constants.json
      --verilog <in.sv> --out manifest.json

`propose` is how the manifest was written: every port boundary_constants.py
found tied to one literal on every instance, with the instance count taken
from the whole file. Python 3.6.
"""

import argparse
import json
import re
import sys

_MODULE = re.compile(r"^module\s+([A-Za-z_][A-Za-z_0-9$]*)\s*\(", re.M)
_LITERAL = re.compile(r"^\d+'[bhd][0-9a-fA-F_xz]+$")
_RANGE = re.compile(r"^\[[^\]]+\]$")
_DIRECTIONS = ("input", "output", "inout")


class SurgeryError(Exception):
    pass


_ANY_INSTANCE = re.compile(r"^\s+([A-Za-z_][A-Za-z_0-9$]*)\s+[A-Za-z_][A-Za-z_0-9$]*\s*\(", re.M)


class Netlist(object):
    """The file as segments, one per module, indexed once.

    segments[i] is [name or None, text]; a module's text runs from `module`
    through `endmodule`. where[name] is the segment defining it, users[name]
    the segments that instance it.
    """

    def __init__(self, text):
        self.segments = []
        pos = 0
        for m in _MODULE.finditer(text):
            if m.start() < pos:
                raise SurgeryError("module %s inside another" % m.group(1))
            end = text.find("endmodule", m.end())
            if end < 0:
                raise SurgeryError("module %s is not closed" % m.group(1))
            end += len("endmodule")
            self.segments.append([None, text[pos : m.start()]])
            self.segments.append([m.group(1), text[m.start() : end]])
            pos = end
        self.segments.append([None, text[pos:]])
        self.where = {}
        self.users = {}
        for i, (name, chunk) in enumerate(self.segments):
            if name is None:
                continue
            self.where.setdefault(name, []).append(i)
            for used in set(_ANY_INSTANCE.findall(chunk)):
                self.users.setdefault(used, []).append(i)

    def text(self):
        return "".join(chunk for _, chunk in self.segments)


def _strip_comment(line):
    i = line.find("//")
    return line if i < 0 else line[:i]


def parse_header(header):
    """Ports of a firtool ANSI header: [(direction, range, name)].

    firtool writes one port per line and leaves direction and range off a
    port that shares them with the one before; those are inherited here.
    """
    ports = []
    direction = None
    rng = ""
    for raw in header.splitlines():
        line = _strip_comment(raw).strip().rstrip(",").strip()
        if not line:
            continue
        tokens = line.split()
        if tokens[0] in _DIRECTIONS:
            direction = tokens[0]
            tokens = tokens[1:]
            rng = ""
            if tokens and tokens[0] in ("wire", "logic"):
                tokens = tokens[1:]
            if tokens and _RANGE.match(tokens[0]):
                rng = tokens[0]
                tokens = tokens[1:]
        if direction is None or len(tokens) != 1:
            raise SurgeryError("unrecognised port declaration %r" % raw.strip())
        ports.append((direction, rng, tokens[0]))
    return ports


def emit_header(name, ports):
    lines = ["module %s(" % name]
    for i, (direction, rng, port) in enumerate(ports):
        sep = "," if i + 1 < len(ports) else ""
        lines.append("  %s %s%s%s" % (direction, rng + " " if rng else "", port, sep))
    return "\n".join(lines) + "\n"


def _connections(body):
    """Connections of an instance body, [(port, expr)], parens matched."""
    out = []
    i = 0
    while True:
        dot = body.find(".", i)
        if dot < 0:
            break
        m = re.match(r"\.(\w+)\s*\(", body[dot:])
        if not m:
            raise SurgeryError("unrecognised connection near %r" % body[dot : dot + 40])
        j = dot + m.end()
        depth = 1
        k = j
        while depth:
            if k >= len(body):
                raise SurgeryError("unbalanced connection .%s" % m.group(1))
            c = body[k]
            depth += c == "("
            depth -= c == ")"
            k += 1
        out.append((m.group(1), body[j : k - 1].strip()))
        i = k
    return out


def _instances(text, module):
    """[(start of connections, end of connections)] of every instance."""
    pat = re.compile(r"^(\s+)%s\s+([A-Za-z_][A-Za-z_0-9$]*)\s*\(" % re.escape(module), re.M)
    out = []
    for m in pat.finditer(text):
        # The connection list ends at the `);` that closes this instance.
        depth = 1
        k = m.end()
        while depth:
            if k >= len(text):
                raise SurgeryError("instance %s of %s is not closed" % (m.group(2), module))
            depth += text[k] == "("
            depth -= text[k] == ")"
            k += 1
        out.append((m.end(), k - 1, m.group(1)))
    return out


def _parent_constant(chunk, pos, name):
    """The literal a `wire <name> = <literal>;` in this module says."""
    m = re.search(r"^\s*wire\s+(?:\[[^\]]+\]\s*)?%s\s*=\s*([^;]+);" % re.escape(name), chunk, re.M)
    return m.group(1).strip() if m else None


def apply_entry(net, e):
    module, port, value, count = e["module"], e["port"], e["value"], e["instances"]
    where = "%s.%s" % (module, port)
    defs = net.where.get(module, [])
    if len(defs) != 1:
        raise SurgeryError("%s: module defined %d times, expected once" % (where, len(defs)))
    insts = [(i, x) for i in net.users.get(module, []) for x in _instances(net.segments[i][1], module)]
    if len(insts) != count:
        raise SurgeryError("%s: %d instances, the manifest says %d" % (where, len(insts), count))
    for i in sorted(set(i for i, _ in insts)):
        chunk = net.segments[i][1]
        # Back to front, so offsets stay valid.
        for start, end, indent in sorted(_instances(chunk, module), reverse=True):
            conns = _connections(chunk[start:end])
            found = [x for p, x in conns if p == port]
            if len(found) != 1:
                raise SurgeryError("%s: an instance connects the port %d times" % (where, len(found)))
            got = found[0]
            if not _LITERAL.match(got):
                got = _parent_constant(chunk, start, got) or got
            if got != value:
                raise SurgeryError("%s: an instance ties it to %r, the manifest says %r" % (where, got, value))
            kept = [(p, x) for p, x in conns if p != port]
            inner = ",\n".join("%s  .%s (%s)" % (indent, p, x) for p, x in kept)
            chunk = chunk[:start] + ("\n" + inner + "\n" + indent if kept else "") + chunk[end:]
        net.segments[i][1] = chunk
    # The module: header without the port, the port as a constant wire.
    i = defs[0]
    chunk = net.segments[i][1]
    open_paren = chunk.find("(")
    header_end = chunk.find(");", open_paren)
    ports = parse_header(chunk[open_paren + 1 : header_end])
    hit = [q for q in ports if q[2] == port]
    if len(hit) != 1 or hit[0][0] != "input":
        raise SurgeryError("%s: not one input port in the header" % where)
    rest = [q for q in ports if q[2] != port]
    rng = hit[0][1]
    wire = "  wire %s%s = %s; // xs_surgery: tied by every instance\n" % (rng + " " if rng else "", port, value)
    net.segments[i][1] = emit_header(module, rest) + ");\n" + wire + chunk[header_end + 2 :]


def apply(text, manifest, protect=()):
    net = Netlist(text)
    for e in sorted(manifest["entries"], key=lambda e: e["round"]):
        if e["module"] in protect:
            raise SurgeryError("%s.%s: %s's ports are protected" % (e["module"], e["port"], e["module"]))
        apply_entry(net, e)
    return net.text()


def propose(boundary, text, origin):
    net = Netlist(text)
    counts = {}
    entries = []
    for row in boundary:
        tied = row["tied"]
        if len(tied) != 1:
            continue
        value, n = list(tied.items())[0]
        if value == "unconnected" or not _LITERAL.match(value):
            continue
        module = row["module"]
        if module not in counts:
            counts[module] = sum(len(_instances(net.segments[i][1], module)) for i in net.users.get(module, []))
        # Every instance in the file, not only those under the top, must
        # tie it: the module text is shared.
        if n != counts[module]:
            continue
        entries.append(
            {
                "round": 1,
                "module": module,
                "kind": row["kind"],
                "port": row["port"],
                "value": value,
                "instances": counts[module],
                "origin": origin,
            }
        )
    return {"entries": entries}


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("apply")
    a.add_argument("--manifest", required=True)
    a.add_argument("--protect", action="append", default=[], help="a module whose ports must not change")
    a.add_argument("input")
    a.add_argument("output")
    q = sub.add_parser("propose")
    q.add_argument("--boundary", required=True)
    q.add_argument("--verilog", required=True)
    q.add_argument("--origin", default="boundary_constants.py: one literal on every instance")
    q.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if args.cmd == "apply":
        with open(args.manifest) as f:
            manifest = json.load(f)
        with open(args.input) as f:
            text = f.read()
        try:
            text = apply(text, manifest, args.protect)
        except SurgeryError as e:
            sys.stderr.write("xs_surgery: %s\n" % e)
            return 1
        with open(args.output, "w") as f:
            f.write(text)
        sys.stdout.write("xs_surgery: %d entries applied\n" % len(manifest["entries"]))
        return 0
    if args.cmd == "propose":
        with open(args.boundary) as f:
            boundary = json.load(f)
        with open(args.verilog) as f:
            text = f.read()
        manifest = propose(boundary, text, args.origin)
        with open(args.out, "w") as f:
            json.dump(manifest, f, indent=1, sort_keys=True)
            f.write("\n")
        sys.stdout.write("xs_surgery: %d entries proposed\n" % len(manifest["entries"]))
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
