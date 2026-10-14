#!/usr/bin/env python3
"""Count the clock gates under a top module of firtool's Verilog.

Every `ClockGate` instance reachable from --top, as the flow hardens it:
how many there are once the hierarchy is expanded (a module instantiated
twelve times contributes its gates twelve times), and for each module that
holds one, the expressions on E and TE. A gate whose E or TE is a literal
1 is always on: it gates nothing, and on ASAP7 it is the cell whose
conditioned CLK->GCLK arc hides the rising edge (parallaxsw/OpenSTA#532).

The parse is firtool's output shape: one `module`..`endmodule` per module,
instances as `Name inst (` at the start of a line, one `.port (expr)` per
line.

Usage: clock_gate_census.py <verilog> --top XSTile --out census.json
"""

import argparse
import json
import re
import sys

_MODULE = re.compile(r"^module\s+([A-Za-z_][A-Za-z_0-9$]*)", re.M)
_INSTANCE = re.compile(
    r"^\s+([A-Za-z_][A-Za-z_0-9$]*)\s+([A-Za-z_][A-Za-z_0-9$]*)\s*\(", re.M
)
_PORT = re.compile(r"^\s*\.(\w+)\s*\((.*?)\)\s*,?\s*(?://.*)?$", re.M)
_ONE = re.compile(r"^(?:1'h1|1'b1)$")

GATE = "ClockGate"


def modules(text):
    """Map module name -> body text."""
    found = {}
    starts = [(m.start(), m.group(1)) for m in _MODULE.finditer(text)]
    for (start, name), nxt in zip(starts, starts[1:] + [(len(text), None)]):
        end = text.find("endmodule", start, nxt[0])
        if end < 0:
            raise SystemExit("clock_gate_census: module %s has no endmodule" % name)
        if name in found:
            raise SystemExit("clock_gate_census: module %s defined twice" % name)
        found[name] = text[start:end]
    return found


def instances(body, names):
    """(module, instance, ports text) for each instance of a known module."""
    out = []
    for m in _INSTANCE.finditer(body):
        if m.group(1) not in names:
            continue
        close = body.find(");", m.end())
        out.append((m.group(1), m.group(2), body[m.end() : close]))
    return out


def census(text, top):
    mods = modules(text)
    if top not in mods:
        raise SystemExit("clock_gate_census: no module %s" % top)
    # The gate counts whether or not the netlist defines it; firtool does
    # not, its body comes from ClockGate.sv.
    known = set(mods) | {GATE}
    children = {name: instances(body, known) for name, body in mods.items()}
    # Every module under top, then each one's expanded instance count.
    order = [top]
    seen = {top}
    i = 0
    while i < len(order):
        for child, _, _ in children[order[i]]:
            if child in mods and child not in seen:
                seen.add(child)
                order.append(child)
        i += 1
    # Parents before children: firtool's hierarchy is a DAG.
    indeg = {m: 0 for m in order}
    for m in order:
        for child, _, _ in children[m]:
            if child in indeg:
                indeg[child] += 1
    ready = [top]
    count = {m: 0 for m in order}
    count[top] = 1
    while ready:
        m = ready.pop()
        for child, _, _ in children[m]:
            if child not in indeg:
                continue
            count[child] += count[m]
            indeg[child] -= 1
            if indeg[child] == 0:
                ready.append(child)
    holders = []
    total = 0
    always_on = 0
    for m in order:
        gates = []
        for child, inst, ports in children[m]:
            if child != GATE:
                continue
            conn = {p: e.strip() for p, e in _PORT.findall(ports)}
            on = bool(_ONE.match(conn.get("E", ""))) or bool(
                _ONE.match(conn.get("TE", ""))
            )
            gates.append(
                {
                    "instance": inst,
                    "E": conn.get("E"),
                    "TE": conn.get("TE"),
                    "always_on": on,
                }
            )
        if gates:
            n = count[m]
            total += n * len(gates)
            always_on += n * sum(g["always_on"] for g in gates)
            holders.append({"module": m, "instances": n, "gates": gates})
    return {
        "top": top,
        "gates": total,
        "always_on": always_on,
        "gate_module_defined": GATE in mods,
        "modules": holders,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("verilog")
    p.add_argument("--top", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    with open(a.verilog) as f:
        result = census(f.read(), a.top)
    with open(a.out, "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
        f.write("\n")
    sys.stdout.write(
        "%s: %d clock gates, %d always on\n"
        % (a.top, result["gates"], result["always_on"])
    )


if __name__ == "__main__":
    main()
