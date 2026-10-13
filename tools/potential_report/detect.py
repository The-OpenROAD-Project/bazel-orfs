"""Tier 1 of the potential report: repeating structures in a netlist.

Reads yosys `write_json` of a design with its hierarchy intact (the
canonicalized RTLIL, or any module set after `proc`) and finds five
shapes, each a candidate for an RTL rewrite or a structured placement:

- replicated:   N instances of one module (slang's `Name$path` copies
                counted as one module);
- const_index:  an input port tied to a different constant on every
                instance, compared inside the leaf with something else:
                N x k compares that are k shared decoders in disguise;
- broadcast:    a net driving the same input port of N instances,
                compared inside the leaf: a CAM's search key;
- matrix:       registers named by two indices over 0..N-1 covering at
                least half the pairs: an age or dependence matrix;
- reduction:    a reduce/pmux cell whose inputs are mostly the outputs
                of one replicated group: the CAM's match or select tree.

Counts only; nothing is synthesised here. Each finding carries the
numbers its upside estimate needs and an analytic estimate stated as
such. A finding is a recommendation; the flow's period decides.
"""

import argparse
import json
import math
import re
import sys

COMPARES = {"$eq", "$ne", "$eqx", "$nex", "$lt", "$le", "$gt", "$ge"}
REDUCTIONS = {"$reduce_or", "$reduce_and", "$reduce_bool", "$reduce_xor", "$pmux"}


def base_name(module_type):
    """The module a uniquified or derived name came from."""
    name = module_type.lstrip("\\")
    if name.startswith("$paramod"):
        # $paramod\Name\PARAM=...  or  $paramod$hash\Name
        parts = [
            p for p in re.split(r"[\\$]", name) if p and not p.startswith("paramod")
        ]
        name = parts[0] if parts else name
    return name.split("$", 1)[0]


def is_const(bits):
    return all(isinstance(b, str) for b in bits)


def const_value(bits):
    """LSB-first bit list to an int; None if any bit is x or z."""
    v = 0
    for i, b in enumerate(bits):
        if b == "1":
            v |= 1 << i
        elif b != "0":
            return None
    return v


def instance_groups(module, modules, min_n):
    """Instances of user modules in `module`, grouped by base name."""
    groups = {}
    for name, cell in module["cells"].items():
        t = cell["type"]
        if t.startswith("$") and not t.startswith("$paramod"):
            continue
        if t not in modules:
            continue
        groups.setdefault(base_name(t), []).append((name, cell))
    return {b: g for b, g in groups.items() if len(g) >= min_n}


def leaf_compares(leaf, port_bits):
    """Compare cells in `leaf` with an operand among `port_bits`.

    Returns (count, width, other operands' bit sets)."""
    bits = set(port_bits)
    count, width = 0, 0
    others = []
    for cell in leaf["cells"].values():
        if cell["type"] not in COMPARES:
            continue
        a = cell["connections"].get("A", [])
        b = cell["connections"].get("B", [])
        if bits & set(a):
            count += 1
            width = max(width, len(a))
            others.append(b)
        elif bits & set(b):
            count += 1
            width = max(width, len(b))
            others.append(a)
    return count, width, others


def port_bits(leaf, port):
    return leaf["ports"][port]["bits"]


def detect_groups(top_name, module, modules, min_n, findings):
    for base, group in instance_groups(module, modules, min_n).items():
        n = len(group)
        leaf_type = group[0][1]["type"]
        leaf = modules[leaf_type]
        leaf_cells = len(leaf["cells"])
        findings.append(
            {
                "kind": "replicated",
                "module": top_name,
                "leaf": base,
                "n": n,
                "leaf_cells": leaf_cells,
                "distinct_definitions": len({c["type"] for _, c in group}),
                "estimate": "synthesise the leaf once: %d mappings of %d word-level cells become 1"
                % (n, leaf_cells),
            }
        )
        directions = group[0][1].get("port_directions", {})
        inputs = [p for p, d in sorted(directions.items()) if d == "input"]
        conns_of = {p: [c["connections"].get(p, []) for _, c in group] for p in inputs}
        # A pointer compared with a constant index is a decoder, not a
        # CAM key: the const_index finding owns it.
        const_bits = set()
        for port in inputs:
            if conns_of[port][0] and all(is_const(b) for b in conns_of[port]):
                const_bits.update(port_bits(leaf, port))
        for port in inputs:
            conns = conns_of[port]
            if not conns[0]:
                continue
            if all(is_const(b) for b in conns):
                values = [const_value(b) for b in conns]
                distinct = len(set(values))
                if distinct < 0.9 * n:
                    continue
                k, w, others = leaf_compares(leaf, port_bits(leaf, port))
                if k == 0:
                    continue
                w = max(w, len(conns[0]))
                # One shared decoder per distinct thing compared with the
                # index; the same pointer compared twice is one decoder.
                distinct = len({tuple(o) for o in others})
                findings.append(
                    const_index_finding(top_name, base, port, n, k, distinct, w)
                )
            elif all(b == conns[0] for b in conns) and not is_const(conns[0]):
                k, w, others = leaf_compares(leaf, port_bits(leaf, port))
                k -= sum(1 for o in others if const_bits & set(o))
                if k <= 0:
                    continue
                findings.append(
                    broadcast_finding(top_name, base, port, n, k, len(conns[0]))
                )
        detect_reductions(top_name, module, base, group, findings)


def const_index_finding(top, leaf, port, n, k, operands, w):
    # Today: n*k compares of w bits, each w XNOR and a w-input AND tree,
    # and every bit of the other operand loads n*k XNOR inputs. Shared:
    # k decoders of w -> n, two-bit predecode (4 lines per bit pair) and
    # one AND of ceil(w/2) predecoded lines per entry.
    today = n * k * (2 * w - 1)
    pairs = math.ceil(w / 2)
    shared = operands * (n * max(pairs - 1, 1) + 4 * pairs)
    return {
        "kind": "const_index",
        "module": top,
        "leaf": leaf,
        "port": port,
        "n": n,
        "compares_per_leaf": k,
        "operands": operands,
        "width": w,
        "gates_today": today,
        "gates_shared": shared,
        "operand_bit_loads_today": n * k // operands,
        "operand_bit_loads_shared": 2,
        "estimate": "analytic, two-input gates: %d compares of %d bits (%d gates) against %d distinct operands, as %d shared decoders (%d gates), %.0f%% fewer; "
        "each operand bit from %d loads to 2"
        % (
            n * k,
            w,
            today,
            operands,
            operands,
            shared,
            100.0 * (1 - shared / today),
            n * k // operands,
        ),
    }


def broadcast_finding(top, leaf, port, n, k, w):
    # Logical effort: a bit driving n*k compare inputs needs about
    # log4(n*k) FO4 of buffering before the first compare gate.
    loads = n * k
    return {
        "kind": "broadcast",
        "module": top,
        "leaf": leaf,
        "port": port,
        "n": n,
        "compares_per_leaf": k,
        "width": w,
        "key_bit_loads": loads,
        "fanout_fo4_floor": round(math.log(loads, 4), 1),
        "estimate": "analytic: each of %d key bits drives %d compare inputs, at least %.1f FO4 of fanout before the first compare"
        % (w, loads, math.log(loads, 4)),
    }


def detect_reductions(top, module, base, group, findings):
    outs = set()
    for _, cell in group:
        for port, direction in cell.get("port_directions", {}).items():
            if direction == "output":
                outs.update(
                    b
                    for b in cell["connections"].get(port, [])
                    if not isinstance(b, str)
                )
    for name, cell in module["cells"].items():
        if cell["type"] not in REDUCTIONS:
            continue
        key = "S" if cell["type"] == "$pmux" else "A"
        ins = cell["connections"].get(key, [])
        if len(ins) < len(group):
            continue
        fed = sum(1 for b in ins if b in outs)
        if fed < 0.5 * len(ins):
            continue
        findings.append(
            {
                "kind": "reduction",
                "module": top,
                "leaf": base,
                "cell": cell["type"],
                "width": len(ins),
                "depth_floor": math.ceil(math.log2(len(ins))),
                "estimate": "analytic: a %d-input %s over the %s outputs, at least %d two-input levels"
                % (len(ins), cell["type"], base, math.ceil(math.log2(len(ins)))),
            }
        )


def detect_matrix(top, module, findings, min_n):
    """Registers whose names carry two indices: age_i_j, r[i].c[j]."""
    bitname = {}
    for name, net in module["netnames"].items():
        if name.startswith("$"):
            continue
        two = len(re.findall(r"\[\d+\]|_\d+(?=_|$)", name)) >= 2
        for b in net["bits"]:
            if two or b not in bitname:
                bitname[b] = name
    stems = {}
    for cell in module["cells"].values():
        if not cell["type"].startswith(("$dff", "$adff", "$sdff", "$dffe", "$aldff")):
            continue
        for b in cell["connections"].get("Q", []):
            name = bitname.get(b)
            if not name:
                continue
            idx = re.findall(r"\[(\d+)\]|_(\d+)(?=_|$)", name)
            nums = [int(x or y) for x, y in idx]
            if len(nums) < 2:
                continue
            stem = re.sub(r"\[\d+\]|_\d+(?=_|$)", "#", name)
            stems.setdefault(stem, set()).add((nums[-2], nums[-1]))
    for stem, pairs in stems.items():
        rows = max(i for i, _ in pairs) + 1
        cols = max(j for _, j in pairs) + 1
        n = max(rows, cols)
        # An age or dependence matrix is one triangle of an N x N square
        # (with or without its diagonal), both indices over the same
        # entries; a full square or a rectangle is an array of records.
        if n < min_n or abs(rows - cols) > 1:
            continue
        if not n * (n - 1) / 2 <= len(pairs) <= n * (n + 1) / 2:
            continue
        findings.append(
            {
                "kind": "matrix",
                "module": top,
                "stem": stem,
                "n": n,
                "bits": len(pairs),
                "estimate": "an %d x %d matrix of %d state bits: a 2-D tile, row and column wires of %d loads"
                % (n, n, len(pairs), n),
            }
        )


def detect_flat_cam(top, module, findings, min_n):
    """N compares of one key against N registered words in one module: a
    CAM whose entries are registers, not instances (a TLB's tags)."""
    dff_q = set()
    for cell in module["cells"].values():
        if cell["type"].startswith(("$dff", "$adff", "$sdff", "$dffe", "$aldff")):
            dff_q.update(
                b for b in cell["connections"].get("Q", []) if not isinstance(b, str)
            )
    by_key = {}
    for cell in module["cells"].values():
        if cell["type"] not in ("$eq", "$ne"):
            continue
        a = cell["connections"].get("A", [])
        b = cell["connections"].get("B", [])
        for key, word in ((a, b), (b, a)):
            if len(word) >= 4 and all(
                not isinstance(x, str) and x in dff_q for x in word
            ):
                if not all(not isinstance(x, str) and x in dff_q for x in key):
                    by_key.setdefault(tuple(key), set()).add(tuple(word))
    for key, words in by_key.items():
        n = len(words)
        if n < min_n:
            continue
        w = len(key)
        findings.append(
            {
                "kind": "flat_cam",
                "module": top,
                "n": n,
                "width": w,
                "key_bit_loads": n,
                "fanout_fo4_floor": round(math.log(n, 4), 1),
                "estimate": "analytic: a %d-entry CAM of %d-bit registered words in one module; each key bit drives %d compare inputs, at least %.1f FO4 of fanout"
                % (n, w, n, math.log(n, 4)),
            }
        )


def detect(design, min_n=8):
    modules = design["modules"]
    findings = []
    for name, module in modules.items():
        if module.get("attributes", {}).get("blackbox"):
            continue
        detect_groups(name, module, modules, min_n, findings)
        detect_matrix(name, module, findings, min_n)
        detect_flat_cam(name, module, findings, min_n)
    return dedup(findings)


def dedup(findings):
    """One finding per shape: slang gives every copy of a module its own
    definition (Name$path), so a parent instanced k times reports each
    of its shapes k times. Keep the first, count the copies."""
    seen = {}
    out = []
    for f in findings:
        key = (
            f["kind"],
            base_name(f["module"]),
            f.get("leaf"),
            f.get("port"),
            f.get("cell"),
            re.sub(r"\d+", "#", f.get("stem", "")),
            f.get("n"),
        )
        if key in seen:
            seen[key]["copies"] += 1
            continue
        f = dict(f, copies=1)
        seen[key] = f
        out.append(f)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("json", help="yosys write_json of the design")
    p.add_argument("--min-n", type=int, default=8, help="smallest repetition reported")
    p.add_argument("--out", help="findings as JSON (default: stdout)")
    args = p.parse_args(argv)
    with open(args.json) as f:
        findings = detect(json.load(f), args.min_n)
    text = json.dumps(findings, indent=1, sort_keys=True)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    sys.exit(main())
