#!/usr/bin/env python3
"""Sink a module's output registers into the modules that read them.

  sink_registers.py --module CtrlBlock --flatten RedirectGenerator
      --ports io_toIssueBlock_flush_ --parent Backend --instance inner_ctrlBlock
      --consumers inner_vecRegion=in_flush_,inner_fpRegion=in_flush_
      --yosys Y --slang S <in.sv> <out.sv>

The output ports of `module` named by the `--ports` prefix are a
combinational function of registers (and of a few other signals, the
leaves). Each consumer module gets a copy of those registers and of that
function, as a new module `<module>_sink`; `module` exports what the
copies need, the registers' next-state pins (D, enable, load) and the
leaves, as `sink_*` output ports, and the consumer's own input ports for
the bundle become wires driven by its copy. The original registers stay
where they are for every other reader.

A copy holds the same value as its original every cycle: same clock, same
next state, same reset. No register is added on any path and the Chisel
design is unchanged; the crossing moves from the registers' outputs to
their inputs, where a launch register's D cone usually has slack.

yosys (with the slang frontend) reads `module` and writes it back with the
extra ports; the consumers and the parent are edited as text, the way
firtool writes them.
"""

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys

CONST = {"0", "1", "x", "z"}


def is_ff(t):
    return t.startswith("$") and ("dff" in t or "dlatch" in t)


def base(name):
    """slang's per-instance module name back to the source module."""
    return name.split("$")[0] if not name.startswith("$") else name


def outputs_of(cell):
    pd = cell.get("port_directions", {})
    return (
        [p for p, d in pd.items() if d == "output"]
        if pd
        else [p for p in cell["connections"] if p in ("Y", "Q", "X", "CO")]
    )


def cone_of(mod, drivers, bits):
    """Registers and combinational cells behind bits, and the leaf bits."""
    cells, ffs, leaves, seen, todo = set(), set(), [], set(), list(bits)
    while todo:
        b = todo.pop()
        if b in CONST or b in seen:
            continue
        seen.add(b)
        d = drivers.get(b)
        if d and d[0] == "cell":
            c = mod["cells"][d[1]]
            if is_ff(c["type"]):
                ffs.add(d[1])
            elif c["type"].startswith("$") and not c["type"].startswith("$mem"):
                if d[1] not in cells:
                    cells.add(d[1])
                    outs = outputs_of(c)
                    for pin, pbits in c["connections"].items():
                        if pin not in outs:
                            todo.extend(pbits)
            else:
                leaves.append(b)
        else:
            leaves.append(b)
    return cells, ffs, leaves


def transform(mod, ports_prefix, stage_name, registers=None, sink="sink_"):
    drivers = {}
    for pname, p in mod["ports"].items():
        if p["direction"] == "input":
            for i, b in enumerate(p["bits"]):
                drivers[b] = ("port", pname, i)
    for cname, c in mod["cells"].items():
        for pin in outputs_of(c):
            for i, b in enumerate(c["connections"][pin]):
                drivers[b] = ("cell", cname, pin)
    names = {}
    for n, nn in mod["netnames"].items():
        if nn.get("hide_name"):
            continue
        for i, b in enumerate(nn["bits"]):
            names.setdefault(b, (n, i))
    if registers:
        # the bundle is every output whose cone holds one of the registers
        qname = {}
        for cname, c in mod["cells"].items():
            if is_ff(c["type"]):
                n = names.get(c["connections"]["Q"][0])
                if n:
                    qname[cname] = n[0]
        P = {}
        for n, p in mod["ports"].items():
            if p["direction"] != "output":
                continue
            _, f, _ = cone_of(mod, drivers, p["bits"])
            if any(
                qname.get(x)
                and any(fnmatch.fnmatchcase(qname[x], r) for r in registers)
                for x in f
            ):
                P[n] = p
    else:
        P = {
            n: p
            for n, p in mod["ports"].items()
            if n.startswith(ports_prefix) and p["direction"] == "output"
        }
    if not P:
        sys.exit(f"sink_registers: no output port reads {registers or ports_prefix}")
    cone, ffs, leaves = set(), set(), []
    seen, todo = set(), [b for p in P.values() for b in p["bits"]]
    while todo:
        b = todo.pop()
        if b in CONST or b in seen:
            continue
        seen.add(b)
        d = drivers.get(b)
        if d and d[0] == "cell":
            c = mod["cells"][d[1]]
            if is_ff(c["type"]):
                ffs.add(d[1])
            elif c["type"].startswith("$") and not c["type"].startswith("$mem"):
                if d[1] not in cone:
                    cone.add(d[1])
                    outs = outputs_of(c)
                    for pin, bits in c["connections"].items():
                        if pin not in outs:
                            todo.extend(bits)
            else:
                leaves.append(b)
        else:
            leaves.append(b)
    # the stage's bits
    nxt = [2]

    def fresh():
        nxt[0] += 1
        return nxt[0]

    smap = {}  # M bit -> stage bit, for bits the stage computes
    for cname in sorted(cone | ffs):
        c = mod["cells"][cname]
        for pin in outputs_of(c):
            for b in c["connections"][pin]:
                if b not in CONST:
                    smap[b] = fresh()
    clock_bit = fresh()
    groups = {}  # export port name -> list of M bits
    origins = {}  # export port name -> [(kind, where, pin, index)], with groups
    exported = {}  # M bit -> stage bit

    def export(b, name, origin=None):
        if b in CONST:
            return b
        if b in smap:
            return smap[b]
        if b not in exported:
            exported[b] = fresh()
            groups.setdefault(name, []).append(b)
            if origin is None:
                n = names.get(b)
                origin = ("net", n[0], None, n[1]) if n else ("net", None, None, None)
            origins.setdefault(name, []).append(origin)
        return exported[b]

    def leaf_name(b):
        n = names.get(b)
        return re.sub(r"\W", "_", n[0]) if n else "leaf"

    m_clock = set()
    scells = {}
    for cname in sorted(cone | ffs):
        c = mod["cells"][cname]
        outs = outputs_of(c)
        conn = {}
        if cname in ffs:
            q = c["connections"]["Q"]
            qn = leaf_name(q[0])
        for pin, bits in c["connections"].items():
            if pin in outs:
                conn[pin] = [smap.get(b, b) for b in bits]
            elif cname in ffs and pin == "CLK":
                m_clock.update(bits)
                conn[pin] = [clock_bit]
            elif cname in ffs:
                qnet = names.get(q[0], (None,))[0]
                conn[pin] = [
                    export(b, f"{qn}_{pin}", ("ff", qnet, pin, i))
                    for i, b in enumerate(bits)
                ]
            else:
                conn[pin] = [export(b, leaf_name(b)) for b in bits]
        scells[cname] = {k: v for k, v in c.items() if k != "connections"}
        scells[cname]["connections"] = conn
    for b in leaves:
        export(b, leaf_name(b))
    if len(m_clock) > 1:
        sys.exit(f"sink_registers: registers on {len(m_clock)} clocks")
    sports = {"clock": {"direction": "input", "bits": [clock_bit]}}
    for g, bits in groups.items():
        sports[sink + g] = {"direction": "input", "bits": [exported[b] for b in bits]}
    for n, p in P.items():
        sports[n] = {
            "direction": "output",
            "bits": [
                b if b in CONST else smap.get(b, exported.get(b)) for b in p["bits"]
            ],
        }
    stage = {
        "attributes": {},
        "ports": sports,
        "cells": scells,
        "netnames": {
            n: {"hide_name": 0, "bits": p["bits"], "attributes": {}}
            for n, p in sports.items()
        },
    }
    for cname in cone | ffs:  # keep the registers' names readable in the copy
        c = mod["cells"][cname]
        if cname in ffs:
            q = c["connections"]["Q"]
            n = names.get(q[0])
            if n:
                stage["netnames"][n[0]] = {
                    "hide_name": 0,
                    "attributes": {},
                    "bits": [smap[b] for b in q],
                }
    # the source module exports what the copies read
    for g, bits in groups.items():
        name = sink + g
        # an earlier sink of the same registers already brought them out
        old = mod["ports"].get(name)
        if old and old["bits"] != bits:
            sys.exit(f"sink_registers: port {name} exists with other bits")
        mod["ports"][name] = {"direction": "output", "bits": bits}
        mod["netnames"][name] = {"hide_name": 0, "bits": bits, "attributes": {}}
    widths = {sink + g: len(b) for g, b in groups.items()}
    transform.origins = origins
    return (
        stage,
        widths,
        {n: len(p["bits"]) for n, p in P.items()},
        {
            "registers": len(ffs),
            "cells": len(cone),
            "register_bits": sum(len(mod["cells"][f]["connections"]["Q"]) for f in ffs),
            "leaf_bits": len(set(leaves) - set(smap)),
        },
    )


def split_top(s):
    """Split on commas outside parentheses/brackets/braces."""
    out, depth, cur = [], 0, []
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


def module_span(text, name):
    m = re.search(r"^module\s+" + re.escape(name) + r"\s*\(", text, re.M)
    if not m:
        sys.exit(f"sink_registers: module {name} not found")
    return m.start(), text.index("\nendmodule", m.start()) + len("\nendmodule")


def paren_span(text, open_at):
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return open_at, i
    raise ValueError


def rng(w):
    return f"[{w - 1}:0] " if w > 1 else ""


def edit_instance(body, inst, drop, add):
    """Rewrite an instance's connection list: drop ports, add (port, expr)."""
    m = re.search(r"^([ \t]+)(\w+)\s+" + re.escape(inst) + r"\s*\(", body, re.M)
    if not m:
        sys.exit(f"sink_registers: instance {inst} not found")
    a, z = paren_span(body, m.end() - 1)
    items = [
        i
        for i in split_top(body[a + 1 : z])
        if not re.match(r"\s*\.(\w+)", i)
        or re.match(r"\s*\.(\w+)", i).group(1) not in drop
    ]
    items = [i.strip() for i in items] + [f".{p} ({e})" for p, e in add]
    new = "\n" + ",\n".join("    " + i for i in items) + "\n  "
    return body[: a + 1] + new + body[z:], m.group(2), m.start()


def input_ports(text, module):
    """A module's input ports, a grouped declaration ("input a, b,") read as
    firtool means it."""
    s, e = module_span(text, module)
    mtext = text[s:e]
    a, z = paren_span(mtext, mtext.index("("))
    out, direction = set(), None
    for i in split_top(mtext[a + 1 : z]):
        m = re.match(r"\s*(input|output|inout)\b", i)
        if m:
            direction = m.group(1)
        name = re.search(r"(\w+)\s*$", i)
        if name and direction == "input":
            out.add(name.group(1))
    return out


def edit_consumer(text, cmod, mapping, widths, stage_name, outw):
    """cmod's ports in `mapping` (consumer port -> stage output) become wires
    driven by its own copy; it gains the sink_* inputs."""
    s, e = module_span(text, cmod)
    mtext = text[s:e]
    a, z = paren_span(mtext, mtext.index("("))
    items = split_top(mtext[a + 1 : z])
    # firtool groups ports of one type under one declaration ("input a, b,"):
    # a removed port that carries the declaration hands it to the next
    keep, carry = [], None
    decl = re.compile(r"^(\s*)((?:input|output|inout)\b\s*(?:\[[^\]]*\])?\s*)")
    for i in items:
        mdecl = decl.match(i)
        if re.search(r"(\w+)\s*$", i).group(1) in mapping:
            if mdecl:
                carry = mdecl.group(2)
            continue
        if carry and not mdecl:
            lead = re.match(r"^(\s*)", i).group(1)
            i = lead + carry + i[len(lead) :]
        carry = None
        keep.append(i)
    if len(keep) != len(items) - len(mapping):
        sys.exit(f"sink_registers: {cmod} lacks some of {sorted(mapping)[:3]}")
    keep = [i.rstrip() for i in keep] + [
        f"\n  input  {rng(w)}{n}" for n, w in widths.items()
    ]
    header = mtext[: a + 1] + ",".join(keep) + "\n" + mtext[z : mtext.index(";", z) + 1]
    decl = "".join(f"\n  wire {rng(outw[o])}{c};" for c, o in mapping.items())
    conns = (
        [".clock (clock)"]
        + [f".{n} ({n})" for n in widths]
        + [f".{o} ({c})" for c, o in mapping.items()]
    )
    inst = (
        f"\n  {stage_name} {stage_name.lower()} (\n"
        + ",\n".join("    " + c for c in conns)
        + "\n  );"
    )
    rest = mtext[mtext.index(";", z) + 1 :]
    return text[:s] + header + decl + inst + rest + text[e:]


def add_ports(text, module, ports):
    """Append (direction, width, name) ports to a module's ANSI header."""
    s, e = module_span(text, module)
    mtext = text[s:e]
    a, z = paren_span(mtext, mtext.index("("))
    items = [i.rstrip() for i in split_top(mtext[a + 1 : z])]
    if any(re.match(r"\s*(input|output|inout)\b", i) for i in items):
        items += [f"\n  {d:<6} {rng(w)}{n}" for d, w, n in ports]
        return text[:s] + mtext[: a + 1] + ",".join(items) + "\n" + mtext[z:] + text[e:]
    # a non-ANSI header (yosys writes them): names in the list, declarations after
    items += [f" {n}" for _, _, n in ports]
    head_end = mtext.index(";", z) + 1
    decl = "".join(f"\n  {d} {rng(w)}{n};" for d, w, n in ports)
    return (
        text[:s]
        + mtext[: a + 1]
        + ",".join(items)
        + mtext[z:head_end]
        + decl
        + mtext[head_end:]
        + text[e:]
    )


def module_json(a, module, work):
    """One module as yosys reads it, its submodules kept."""
    path = os.path.join(work, module + ".json")
    subprocess.run(
        [
            a.yosys,
            "-q",
            "-m",
            a.slang,
            "-p",
            f"read_slang --keep-hierarchy --top {module} {a.src}; hierarchy -top {module}; "
            f"select {module}; write_json -selected {path}",
        ],
        check=True,
    )
    return json.load(open(path))["modules"][module]


def hier_export(text, a, M, widths, origins, sink="sink_"):
    """Bring each exported bit out of the source module without rewriting
    it as a whole: a register's pins out of the module that holds it, at
    any depth (rewritten by yosys, which alone sees the next state; a module
    instanced several times is rewritten once and every instance carries
    its own copy up), then up through each level's header by a port named
    by the path below it; a net of the source module itself likewise."""

    def inst_type(module, inst):
        ms, me = module_span(text, module)
        m = re.search(r"^\s+(\w+)\s+" + re.escape(inst) + r"\s*\(", text[ms:me], re.M)
        return m.group(1) if m else None

    def san(x):
        return re.sub(r"\W", "_", x)

    leaf = {}  # module -> {local port: (kind, local name, pin, idx)}
    chains = []  # (M port, [(holder, inst, child port, holder port)], width)
    for g, orig in origins.items():
        port = sink + g
        kind, where, pin, _ = orig[0]
        idx = [o[3] for o in orig]
        if where is None:
            sys.exit(f"sink_registers: {port} has no named source")
        parts, module, path = where.split("."), M, []
        while len(parts) > 1:
            t = inst_type(module, parts[0])
            if t is None:
                break
            path.append((module, parts[0]))
            module = t
            parts = parts[1:]
        name = ".".join(parts)
        local = sink + san(name) + (f"_{pin}" if kind == "ff" else "")
        leaf.setdefault(module, {})[local] = (kind, name, pin, idx)
        # the port at each level is named by the path below it
        links, below = [], local
        for holder, inst in reversed(path):
            here = port if holder == M else sink + san(inst) + "_" + below[len(sink) :]
            links.append((holder, inst, below, here))
            below = here
        chains.append((port, links, len(idx)))
    # the modules that hold the registers, the source module last: it is
    # read from the input file, and the ports below it are connected after
    for module in sorted(leaf, key=lambda m: m == M):
        smod = module_json(a, module, a.work)
        nets = {n: v["bits"] for n, v in smod["netnames"].items()}
        for local, (kind, name, pin, idx) in leaf[module].items():
            if kind == "ff":
                cell = [
                    c
                    for c in smod["cells"].values()
                    if is_ff(c["type"]) and c["connections"]["Q"] == nets.get(name)
                ]
                if len(cell) != 1:
                    sys.exit(f"sink_registers: register {name} not found in {module}")
                bits = [cell[0]["connections"][pin][i] for i in idx]
            else:
                bits = [nets[name][i] for i in idx]
            smod["ports"][local] = {"direction": "output", "bits": bits}
            smod["netnames"][local] = {"hide_name": 0, "bits": bits, "attributes": {}}
        for c in smod["cells"].values():
            c["type"] = base(c["type"])
        sj = os.path.join(a.work, module + ".sunk.json")
        sv = os.path.join(a.work, module + ".sunk.v")
        json.dump({"modules": {module: smod}}, open(sj, "w"))
        subprocess.run(
            [a.yosys, "-q", "-p", f"read_json {sj}; write_verilog -noattr {sv}"],
            check=True,
        )
        written = open(sv).read()
        ws, we = module_span(written, module)
        ts, te = module_span(text, module)
        text = text[:ts] + written[ws:we] + text[te:]
    # up through each level, once per (holder, port) and per instance
    added, connected = set(), set()
    for port, links, w in chains:
        for holder, inst, child, here in links:
            if (holder, inst, child) not in connected:
                connected.add((holder, inst, child))
                hs, he = module_span(text, holder)
                hbody, _, _ = edit_instance(text[hs:he], inst, set(), [(child, here)])
                text = text[:hs] + hbody + text[he:]
            if (holder, here) not in added:
                added.add((holder, here))
                text = add_ports(text, holder, [("output", w, here)])
    return text


def self_consumer(body, inst, outw, widths, stage_name):
    """The parent's own logic reads the source's outputs: a copy inline in
    the parent, and every read outside the source's instance moves to it."""
    m = re.search(r"^([ \t]+)(\w+)\s+" + re.escape(inst) + r"\s*\(", body, re.M)
    i0 = m.start()
    _, i1 = paren_span(body, m.end() - 1)
    sunk = {n: f"_{inst}_{n}_sunk" for n in outw}
    pats = {
        n: re.compile(r"\b_" + re.escape(inst) + "_" + re.escape(n) + r"\b")
        for n in outw
    }

    def move(chunk):
        out = []
        for line in chunk.split("\n"):
            if not re.match(r"\s*(wire|reg|logic)\b", line):
                for n, pat in pats.items():
                    line = pat.sub(sunk[n], line)
            out.append(line)
        return "\n".join(out)

    body = move(body[:i0]) + body[i0:i1] + move(body[i1:])
    conns = (
        [".clock (clock)"]
        + [f".{n} (_{inst}_{n})" for n in widths]
        + [f".{n} ({sunk[n]})" for n in outw]
    )
    stage = (
        f"  {stage_name} {stage_name.lower()} (\n"
        + ",\n".join("    " + c for c in conns)
        + "\n  );\n"
    )
    m = re.search(r"^([ \t]+)(\w+)\s+" + re.escape(inst) + r"\s*\(", body, re.M)
    body = body[: m.start()] + stage + body[m.start() :]
    # declared right after the header: the parent may read them anywhere
    decl = "".join(f"\n  wire {rng(w)}{sunk[n]};" for n, w in outw.items())
    hdr = body.index(";", paren_span(body, body.index("("))[1]) + 1
    return body[:hdr] + decl + body[hdr:]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--flatten", default="")
    ap.add_argument("--ports", default="")
    ap.add_argument(
        "--registers",
        default="",
        help="the bundle is every output reading one of these registers (flattened names)",
    )
    ap.add_argument(
        "--hier",
        action="store_true",
        help="keep the source module's text; export from the submodules that hold the registers",
    )
    ap.add_argument("--parent", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--consumers", required=True)
    ap.add_argument("--yosys", required=True)
    ap.add_argument("--slang", required=True)
    ap.add_argument("--work", default=".")
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args(argv)
    M = a.module
    # a module sunk before (an earlier run on this file) keeps its copy's
    # name; this run's copy takes the next free one
    src_text = open(a.src).read()
    stage_name, k = M + "_sink", 1
    while re.search(r"^module\s+" + re.escape(stage_name) + r"\b", src_text, re.M):
        k += 1
        stage_name = f"{M}_sink{k}"
    w = a.work
    mj, sj, mv = (os.path.join(w, f) for f in ("m.json", "m2.json", "m.v"))
    flat = "".join(
        f"setattr -mod -unset keep_hierarchy {f}$*; " for f in a.flatten.split(",") if f
    )
    subprocess.run(
        [
            a.yosys,
            "-q",
            "-m",
            a.slang,
            "-p",
            f"read_slang --keep-hierarchy --top {M} {a.src}; hierarchy -top {M}; "
            f"setattr -mod -set keep_hierarchy 1 *; {flat}flatten {M}; "
            f"select {M}; write_json -selected {mj}",
        ],
        check=True,
    )
    design = json.load(open(mj))
    mod = design["modules"][M]
    regs = set(r for r in a.registers.split(",") if r)
    # each copy its own port prefix, so a later copy of the same registers
    # never meets an earlier one's ports
    sink = "sink_" if k == 1 else f"sink{k}_"
    stage, widths, outw, stats = transform(mod, a.ports, stage_name, regs, sink)
    for c in mod["cells"].values():
        c["type"] = base(c["type"])
    json.dump({"modules": {M: mod, stage_name: stage}}, open(sj, "w"))
    subprocess.run(
        [a.yosys, "-q", "-p", f"read_json {sj}; write_verilog -noattr {mv}"], check=True
    )
    written = open(mv).read()
    text = open(a.src).read()
    ss, se = module_span(written, stage_name)
    if a.hier:
        text = (
            hier_export(text, a, M, widths, transform.origins, sink)
            + "\n\n"
            + written[ss:se]
            + "\n"
        )
    else:
        # the source module, rewritten
        ws, we = module_span(written, M)
        s, e = module_span(text, M)
        text = text[:s] + written[ws:we] + text[e:] + "\n\n" + written[ss:se] + "\n"
    # an instance path (backend/inner_ctrlBlock): each module between the
    # parent and the source carries the sink_* ports up
    path = a.instance.split("/")
    if len(path) > 1:
        holders = [a.parent]
        for inst in path[:-1]:
            hs, he = module_span(text, holders[-1])
            mm = re.search(
                r"^\s+(\w+)\s+" + re.escape(inst) + r"\s*\(", text[hs:he], re.M
            )
            if not mm:
                sys.exit(f"sink_registers: instance {inst} not found in {holders[-1]}")
            holders.append(mm.group(1))
        for holder, inst in reversed(list(zip(holders[1:], path[1:]))):
            hs, he = module_span(text, holder)
            hbody = text[hs:he]
            mm = re.search(r"^[ \t]+\w+\s+" + re.escape(inst) + r"\s*\(", hbody, re.M)
            ia, iz = paren_span(hbody, mm.end() - 1)
            # a port an earlier sink already connected keeps its wire, and
            # the holder's new output is assigned from it
            have = dict(re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", hbody[ia:iz]))
            hbody, _, _ = edit_instance(
                hbody, inst, set(), [(n, n) for n in widths if n not in have]
            )
            assigns = "".join(
                f"  assign {n} = {have[n]};\n" for n in widths if n in have
            )
            if assigns:
                hbody = (
                    hbody[: hbody.rindex("\nendmodule")]
                    + "\n"
                    + assigns
                    + hbody[hbody.rindex("\nendmodule") :]
                )
            text = text[:hs] + hbody + text[he:]
            text = add_ports(
                text, holder, [("output", w, n) for n, w in widths.items()]
            )
        a.instance = path[0]
    # the parent: wires from the source's sink_* ports to each consumer
    ps, pe = module_span(text, a.parent)
    body = text[ps:pe]
    wires = {n: f"_{a.instance}_{n}" for n in widths}
    body, _, at = edit_instance(body, a.instance, set(), list(wires.items()))
    # declared right after the header: a consumer may come before the source
    decl = "".join(f"\n  wire {rng(widths[n])}{x};" for n, x in wires.items())
    hdr = body.index(";", paren_span(body, body.index("("))[1]) + 1
    body = body[:hdr] + decl + body[hdr:]
    edited = set()
    for spec in a.consumers.split(","):
        if spec == "self":
            body = self_consumer(body, a.instance, outw, widths, stage_name)
            stats.setdefault("consumers", []).append(
                f"{a.parent} itself ({len(outw)} ports)"
            )
            continue
        inst, cprefix = spec.split("=")
        if cprefix == "@":
            # the consumer's ports are matched by wiring, not by name: each
            # input connected to one of the source's output wires
            mi = re.search(r"^[ \t]+\w+\s+" + re.escape(inst) + r"\s*\(", body, re.M)
            ia, iz = paren_span(body, mi.end() - 1)
            wired = dict(re.findall(r"\.(\w+)\s*\(\s*(\w+)\s*\)", body[ia:iz]))
            by_wire = {f"_{a.instance}_{n}": n for n in outw}
            mapping = {c: by_wire[w] for c, w in wired.items() if w in by_wire}
        else:
            mapping = {cprefix + n[len(a.ports) :]: n for n in outw}
        body, cmod, _ = edit_instance(body, inst, set(mapping), list(wires.items()))
        if cmod not in edited:
            edited.add(cmod)
            text = text[:ps] + body + text[pe:]
            cs, _ = module_span(text, cmod)
            mapping = {c: o for c, o in mapping.items() if c in input_ports(text, cmod)}
            n_inst = len(
                re.findall(r"^\s+" + re.escape(cmod) + r"\s+\w+\s*\(", text, re.M)
            )
            text = edit_consumer(text, cmod, mapping, widths, stage_name, outw)
            ps, pe = module_span(text, a.parent)
            body = text[ps:pe]
            stats.setdefault("consumers", []).append(
                f"{cmod} ({len(mapping)} ports, {n_inst} instances)"
            )
    text = text[:ps] + body + text[pe:]
    open(a.dst, "w").write(text)
    print(
        f"sink_registers: {M} -> {stage_name}: {stats['registers']} registers "
        f"({stats['register_bits']} bits), {stats['cells']} cells, "
        f"{stats['leaf_bits']} leaf bits, {len(widths)} sink ports; "
        f"consumers {', '.join(stats.get('consumers', []))}"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
