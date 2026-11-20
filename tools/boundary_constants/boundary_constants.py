#!/usr/bin/env python3
"""Constants that stop at a boundary synthesis keeps, under a top module.

firtool propagates constants across modules (and removes the ports it can),
so what reaches yosys as a constant on an instance connection is a constant
firtool left: usually a module whose instances disagree, which its dedup
made one module. Where yosys flattens, it folds those itself. Where the flow
keeps a module (a hardened block, SYNTH_KEEP_MODULES, a generated register
file), it cannot, and the logic behind the constant is paid for.

For every instance of a kept module under --top this reports the input
ports connected to a literal (or to a wire declared equal to one), and the
output ports left unconnected. One row per (module, port), with how many of
the module's instances tie it and to what.

Usage: boundary_constants.py <verilog> --top XSTile --plan plan.json
           --plan-bzl plan.bzl --out boundary.json
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
_LITERAL = re.compile(r"^\d+'[bhd][0-9a-fA-F_xz]+$")
# `wire x = <literal>;`, or `assign x = <literal>;` as xs_surgery.py
# writes a constant output into its parent.
_CONST_WIRE = re.compile(
    r"^\s*(?:wire\s+(?:\[[^\]]+\]\s*)?|assign\s+)(\w+)\s*=\s*(\d+'[bhd][0-9a-fA-F_xz]+)\s*;",
    re.M,
)
_KEEP = re.compile(r'"SYNTH_KEEP_MODULES":\s*"([^"]*)"')


def modules(text):
    found = {}
    starts = [(m.start(), m.group(1)) for m in _MODULE.finditer(text)]
    for (start, name), nxt in zip(starts, starts[1:] + [(len(text), None)]):
        end = text.find("endmodule", start, nxt[0])
        if end < 0:
            raise SystemExit("boundary_constants: module %s has no endmodule" % name)
        found[name] = text[start:end]
    return found


def kept(plan_json, plan_bzl):
    """Module -> boundary kind."""
    kinds = {}
    for m in plan_json["macros"]:
        kinds[m if isinstance(m, str) else m["name"]] = "macro"
    for n in plan_json.get("netlists", []):
        kinds.setdefault(n["module"], "netlist")
    for m in plan_json["parent"].get("keep", []):
        kinds.setdefault(m, "keep")
    for group in _KEEP.findall(plan_bzl):
        for m in group.split():
            kinds.setdefault(m, "keep")
    return kinds


def scan(text, top, kinds):
    mods = modules(text)
    if top not in mods:
        raise SystemExit("boundary_constants: no module %s" % top)
    rows = {}
    seen = {top}
    work = [top]
    instances_of = {}
    while work:
        parent = work.pop()
        body = mods[parent]
        consts = dict(_CONST_WIRE.findall(body))
        for m in _INSTANCE.finditer(body):
            child = m.group(1)
            if child not in mods:
                continue
            if child not in seen:
                seen.add(child)
                work.append(child)
            if child not in kinds:
                continue
            instances_of[child] = instances_of.get(child, 0) + 1
            ports = body[m.end() : body.find(");", m.end())]
            for port, expr in _PORT.findall(ports):
                # firtool writes an unconnected output as `/* unused */`.
                expr = re.sub(r"/\*.*?\*/", "", expr).strip()
                value = None
                if _LITERAL.match(expr):
                    value = expr
                elif expr in consts:
                    value = consts[expr]
                elif expr == "":
                    value = "unconnected"
                if value is None:
                    continue
                row = rows.setdefault((child, port), {})
                row[value] = row.get(value, 0) + 1
    out = []
    for (child, port), values in sorted(rows.items()):
        # References inside the module beyond its port declaration: 0 means
        # firtool already folded the constant and only the pin is left.
        uses = len(re.findall(r"\b%s\b" % re.escape(port), mods[child])) - 1
        out.append(
            {
                "module": child,
                "kind": kinds[child],
                "port": port,
                "instances": instances_of[child],
                "tied": values,
                "uses": uses,
            }
        )
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("verilog")
    p.add_argument("--top", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--plan-bzl", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    with open(a.plan) as f:
        plan_json = json.load(f)
    with open(a.plan_bzl) as f:
        kinds = kept(plan_json, f.read())
    with open(a.verilog) as f:
        rows = scan(f.read(), a.top, kinds)
    with open(a.out, "w") as f:
        json.dump(rows, f, indent=1, sort_keys=True)
        f.write("\n")
    sys.stdout.write("%s: %d tied or unconnected boundary ports\n" % (a.top, len(rows)))


if __name__ == "__main__":
    main()
