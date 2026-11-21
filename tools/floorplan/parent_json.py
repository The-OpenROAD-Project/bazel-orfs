#!/usr/bin/env python3
"""The parent's extract dump (extract_parent.tcl) as parent.json.

The crossings between the parent's blocks, its own logic (the glue) and
its ports, per pair of buses: how many bits of each end take part, how
the parent connects them (a wire, combinational cells, one register) and
the parent's own delay between the two boundaries. Schema:

  parent, identity {dump, tool}
  glue {std_um2}, modules {instance: {module, um2}}
  crossings [{a, a_inst, a_bus, b, b_inst, b_bus, via, a_bits, b_bits,
              bits, depth, glue_ps}]

a and b are block modules (by instance) or the parent's own name: its
ports (instance "-") or its registers (instance "reg", no bus). bits is
the wider end. glue_ps: through cells, the arrival at the bus entering b
less the arrival at the bus leaving a, each its worst bit; from a
register, the register's launch to b.

The crossings come from the dump's graph (extract_parent.tcl's key, bit,
port and cell records): every net carries the set of block buses that
reach it through the glue's combinational cells, as a bitset, once, in
place of one search per bus; depth is the fewest cells from the nearest
source. A dump of cross records is read as it is. Stdlib only.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict

TOOL = "parent_json 1"


def bus_of(name):
    return re.sub(r"\[[0-9]+\]$", "", name)


def ones(v):
    while v:
        low = v & -v
        yield low.bit_length() - 1
        v ^= low


def closure(seeds, edges):
    """Per net, the OR of `seeds` over every net that reaches it through
    `edges` (net -> nets one cell before it), and the fewest cells from a
    seeded net; memoised, iterative, a combinational loop read as empty."""
    val, lvl = {}, {}

    def visit(n0):
        stack = [(n0, False)]
        while stack:
            n, done = stack.pop()
            if not done:
                if n in val:
                    continue
                val[n] = None
                stack.append((n, True))
                stack.extend((i, False) for i in edges.get(n, ()) if i not in val)
                continue
            v, lv = seeds.get(n, 0), None
            for i in edges.get(n, ()):
                if val.get(i):
                    v |= val[i]
                    lv = lvl[i] + 1 if lv is None else min(lv, lvl[i] + 1)
            val[n] = v
            lvl[n] = 0 if n in seeds or lv is None else lv

    def get(n):
        visit(n)
        return val[n] or 0, lvl.get(n, 0)

    return get


def search(top, keys, bits, ports, cells):
    """The cross records of the graph, as extract_parent.tcl's search
    wrote them: (from, from inst, from bus, from bits, to, to inst, to bus,
    to bits, via, depth, glue_ps)."""
    out_bus, in_bus = defaultdict(list), defaultdict(list)
    in_bits, arrival = defaultdict(list), {}
    for k, bus, name, io, net, ps in bits:
        arrival[net] = max(arrival.get(net, 0.0), ps)
        if io == "input":
            in_bits[net].append((k, name))
            in_bus[(k, bus)].append(net)
        elif io == "output":
            out_bus[(k, bus)].append(net)
    srcs, sinks = sorted(out_bus), sorted(in_bus)
    src_seed, sink_seed = defaultdict(int), defaultdict(int)
    for i, s in enumerate(srcs):
        for n in out_bus[s]:
            src_seed[n] |= 1 << i
    for i, s in enumerate(sinks):
        for n in in_bus[s]:
            sink_seed[n] |= 1 << i
    back, fwd = defaultdict(list), defaultdict(list)
    for kind, ins, outs in cells:
        if kind != "comb":
            continue
        for o in outs:
            back[o].extend(ins)
        for i in ins:
            fwd[i].extend(outs)
    F = closure(src_seed, back)
    B = closure(sink_seed, fwd)
    name = {k: (inst, module) for k, inst, module in keys}

    reached = defaultdict(dict)
    for net, ends in in_bits.items():
        v, lv = F(net)
        for s in ones(v):
            via = "wire" if src_seed.get(net, 0) >> s & 1 else "comb"
            for to, bit in ends:
                if to != srcs[s][0]:
                    key = (s, name[to][1], name[to][0], bus_of(bit), via)
                    reached[key][bit] = (lv if via == "comb" else 0, arrival[net])
    for pname, io, net in ports:
        if io != "output":
            continue
        v, lv = F(net)
        for s in ones(v):
            via = "wire" if src_seed.get(net, 0) >> s & 1 else "comb"
            reached[(s, top, "-", bus_of(pname), via)][pname] = (lv, 0.0)
    regs_in, regs_out = defaultdict(dict), defaultdict(dict)
    port_in = defaultdict(lambda: defaultdict(dict))
    for ci, (kind, ins, outs) in enumerate(cells):
        if kind != "reg":
            continue
        for n in ins:
            v, lv = F(n)
            for s in ones(v):
                regs_in[s][ci] = max(regs_in[s].get(ci, 0), lv)
        for n in outs:
            v, lv = B(n)
            for t in ones(v):
                regs_out[t][ci] = max(regs_out[t].get(ci, 0), lv)
    for pname, io, net in ports:
        if io != "input":
            continue
        v, lv = B(net)
        for t in ones(v):
            port_in[t][bus_of(pname)][pname] = lv

    def worst(nets):
        return max([arrival.get(n, 0.0) for n in nets] or [0.0])

    rows = []
    for (s, to, to_inst, to_bus, via), got in reached.items():
        k, bus = srcs[s]
        ps = 0.0
        if via == "comb" and to_inst not in ("reg", "-"):
            ps = round(max(a for _, a in got.values()) - worst(out_bus[srcs[s]]), 1)
        rows.append(
            (
                name[k][1],
                name[k][0],
                bus,
                len(out_bus[srcs[s]]),
                to,
                to_inst,
                to_bus,
                len(got),
                via,
                max(d for d, _ in got.values()),
                ps,
            )
        )
    for s, regs in regs_in.items():
        k, bus = srcs[s]
        rows.append(
            (
                name[k][1],
                name[k][0],
                bus,
                len(out_bus[srcs[s]]),
                top,
                "reg",
                "",
                len(regs),
                "reg",
                max(regs.values()),
                0.0,
            )
        )
    # a block input bus's glue: one depth over its registers and ports
    for t in set(regs_out) | set(port_in):
        k, bus = sinks[t]
        nb = len(in_bus[sinks[t]])
        depth = max(
            list(regs_out[t].values())
            + [d for pins in port_in[t].values() for d in pins.values()]
        )
        if regs_out[t]:
            rows.append(
                (
                    top,
                    "reg",
                    "",
                    len(regs_out[t]),
                    name[k][1],
                    name[k][0],
                    bus,
                    nb,
                    "reg",
                    depth,
                    round(worst(in_bus[sinks[t]]), 1),
                )
            )
        for pbus, pins in port_in[t].items():
            rows.append(
                (
                    top,
                    "-",
                    pbus,
                    len(pins),
                    name[k][1],
                    name[k][0],
                    bus,
                    nb,
                    "comb" if depth > 0 else "wire",
                    depth,
                    0.0,
                )
            )
    return rows


def build(lines, dump_hash):
    parent = None
    glue = 0.0
    modules = {}
    crossings = []
    keys, bits, ports, cells = [], [], [], []
    for line in lines:
        f = line.rstrip("\n").split("\t")
        if not f[0]:
            continue
        if f[0] == "parent":
            parent = f[1]
        elif f[0] == "glue":
            glue = float(f[1])
        elif f[0] == "module":
            modules[f[1]] = {"module": f[2], "um2": float(f[3])}
        elif f[0] == "key":
            keys.append(tuple(f[1:4]))
        elif f[0] == "bit":
            bits.append((f[1], f[2], f[3], f[4], int(f[5]), float(f[6])))
        elif f[0] == "port":
            ports.append((f[1], f[2], int(f[3])))
        elif f[0] == "cell":
            cells.append(
                (
                    f[1],
                    [int(x) for x in f[2].split(",") if x],
                    [int(x) for x in f[3].split(",") if x],
                )
            )
        elif f[0] == "cross":
            crossings.append(f[1:12])
    if keys:
        crossings += search(parent, keys, bits, ports, cells)
    rows, crossings = crossings, []
    for a, ai, ab, na, b, bi, bb, nb, via, depth, ps in rows:
        crossings.append(
            {
                "a": a,
                "a_inst": ai,
                "a_bus": ab,
                "b": b,
                "b_inst": bi,
                "b_bus": bb,
                "via": via,
                "a_bits": int(na),
                "b_bits": int(nb),
                "bits": max(int(na), int(nb)),
                "depth": int(depth),
                "glue_ps": float(ps),
            }
        )
    crossings.sort(
        key=lambda x: (
            x["a"],
            x["a_inst"],
            x["a_bus"],
            x["b"],
            x["b_inst"],
            x["b_bus"],
            x["via"],
        )
    )
    return {
        "parent": parent,
        "identity": {"dump": "sha256:" + dump_hash, "tool": TOOL},
        "glue": {"std_um2": round(glue, 3)},
        "modules": modules,
        "crossings": crossings,
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump")
    ap.add_argument("out")
    args = ap.parse_args(argv)
    with open(args.dump, "rb") as f:
        raw = f.read()
    out = build(raw.decode().splitlines(), hashlib.sha256(raw).hexdigest())
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
