"""Extract a module's entries as one cell instanced per entry: generate_array's
front end, on yosys JSON after proc (proc_json.py, entries.py).

The largest group of entries that follow one rule (entries.py) becomes a
module <module>Entry, built from one entry's private cells (entry 1: entry
0's comparisons with its index are written in yosys's forms of x == 0).
Its inputs are the bits the entry reads from outside (shared logic,
inputs, other entries' registers), one port per bit; its outputs are the
bits of its own that are read outside, in any entry; the constants that
are the entry's index become an input, idx. In the module, every entry's
private cells and registers are replaced by an instance, wired through
that entry's own walk, which pairs each of its boundary bits with the
template's. No register is added or removed: the cell holds them.

It stops on anything that does not line up: entries off the rule, an
index that is not i itself, a token one entry has and another not, a bit
read outside that a merged form of x == 0 hides.

    extract.py <design.json> <module> <out.json> [--keep-idx]

--keep-idx leaves the index as the cell's input, without decode-once:
the form check.py proves equal to the original by a miter that
collapses; decode-once then rests on check.py --lemma.
"""

import collections
import copy
import json
import sys

from entries import FLOPS, OUT, Design, Entries, outputs

TEMPLATE = 1


def fail(msg):
    sys.exit(f"extract: {msg}")


def v_sense(e, where):
    """EQ or NE: how the walk read the x == K form at where."""
    return e._eq_form(where[0])[0]


def extract(mod, name, decode=True):
    d = Design(mod)
    groups = [Entries(d, n, a).narrowed() for n, a in d.groups().items()]
    groups = [e for e in groups if e.uniform]
    if not groups:
        fail("no group of entries follows one rule")
    e = max(
        groups,
        key=lambda e: e.n
        * sum(len(d.cells[f]["connections"]["Q"]) for f in e.flops[0]),
    )
    # an array whose registers take the entry's index as their value (a
    # free list's reset to i) cannot lose its index: it stays in the module
    keep_out = set()
    for k in e.index_sites:
        c = e.walks[TEMPLATE]["consts"][k][0][0]
        if c in e.array_of:
            keep_out.add(e.array_of[c])
    if keep_out:
        arrays = {
            a: {i: e.flops[i][e.arrs.index(a)] for i in range(e.n)}
            for a in e.arrs
            if a not in keep_out
        }
        if not arrays:
            fail(f"every array is kept out ({sorted(keep_out)}): nothing to extract")
        e = Entries(d, e.n, arrays)
        if not e.uniform:
            fail(f"without {sorted(keep_out)} the entries no longer follow one rule")
    n, t = e.n, TEMPLATE
    iw = max(1, (n - 1).bit_length())

    def private(i):
        return {c for c in e.cones[i] if e.reach[c] == 1} | set(e.flops[i])

    def cells_of(i):
        """Entry i's cells in the template's positions: walk order, then flops."""
        return e.walks[i]["order"] + e.flops[i]

    tw = e.walks[t]
    # a cell that drives only constants (a $buf of a literal) is read as
    # its constant and never walked
    walked = set(tw["order"]) | set(tw["merged"]) | tw["folded"]
    unwalked = {c for c in e.cones[t] if e.reach[c] == 1} - walked
    if any(
        d.const.get(b) is None
        for c in unwalked
        for p in outputs(d.cells[c])
        for b in d.cells[c]["connections"][p]
    ):
        fail("the template's walk does not cover its private cells")
    for k, (s, o) in e.index_sites.items():
        if (s, o) != (1, 0):
            fail(f"constant site {k} is {s} * i + {o}, not the index itself")
    tokens = sorted(tw["tokens"])
    for i in range(n):
        if sorted(e.walks[i]["tokens"]) != tokens:
            fail(f"entry {i} reads other boundary bits than the template")
        if len(cells_of(i)) != len(cells_of(t)):
            fail(
                f"entry {i} has {len(cells_of(i))} cells, the template {len(cells_of(t))}"
            )

    # who reads each bit, and the module's output bits
    readers = collections.defaultdict(set)
    for c, cl in d.cells.items():
        for p, bs in cl["connections"].items():
            if p not in outputs(cl):
                for b in bs:
                    if not isinstance(b, str):
                        readers[b].add(c)
    out_bits = {
        b
        for v in mod["ports"].values()
        if v["direction"] == "output"
        for b in v["bits"]
        if not isinstance(b, str)
    }

    # the cell's outputs: (position, port, bit) read outside, in any entry
    outs = set()
    for i in range(n):
        priv = private(i)
        for pos, c in enumerate(cells_of(i)):
            cl = d.cells[c]
            for p in outputs(cl):
                for k, b in enumerate(cl["connections"][p]):
                    if b in out_bits or readers[b] - priv:
                        outs.add((pos, p, k))
        hidden = private(i) - set(cells_of(i))
        for c in hidden:
            cl = d.cells[c]
            for p in outputs(cl):
                for b in cl["connections"][p]:
                    if b in out_bits or readers[b] - private(i):
                        fail(
                            f"entry {i}: {c}, folded into a comparison, is read outside"
                        )
    outs = sorted(outs)

    # the cell module, from the template's cells
    ids = max(
        [
            b
            for v in mod["netnames"].values()
            for b in v["bits"]
            if not isinstance(b, str)
        ]
        + [0]
    )
    idx = list(range(ids + 1, ids + 1 + iw))
    cell_cells = {}
    for c in sorted(private(t)):
        cell_cells[c] = copy.deepcopy(d.cells[c])
        cl = cell_cells[c]
        for p in [q for q in cl["connections"] if cl["port_directions"][q] == "input"]:
            cl["connections"][p] = [
                (
                    d.const[b]
                    if not isinstance(b, str) and d.const.get(b) is not None
                    else b
                )
                for b in cl["connections"][p]
            ]
    # a duplicate the walk merged (Entries._walk) reads as the cell it
    # duplicates: a merged comparison of the index would otherwise keep the
    # template's literal
    same = {}
    for dup, kept in tw["merged"].items():
        a, b = d.cells[dup]["connections"], d.cells[kept]["connections"]
        for p in outputs(d.cells[dup]):
            same.update(zip(a[p], b[p]))
        del cell_cells[dup]
    for cl in cell_cells.values():
        for p, bs in cl["connections"].items():
            cl["connections"][p] = [same.get(x, x) for x in bs]
    sites = [tw["consts"][k] for k in e.index_sites]
    # decode once: a comparison of the index with an operand every entry
    # shares becomes an input of the cell, the comparison made once in the
    # module for all entries (a one-hot shift) and bit i handed to entry i
    token_of = {b: tok for tok, b in tw["tokens"].items()}
    decoded = []  # (hit port, the operand's template bits)
    rest = []
    for where, v, w in sites:
        c, p = where[0], where[1]
        cl = d.cells[c]
        if p == "EQ":
            # x == K, however yosys wrote it: x is the form's own bits
            operand = list(where[2])
            hit = cl["connections"][outputs(cl)[0]][0]
            absolute = all(
                b in token_of and "rel" not in token_of[b] and "mod" not in token_of[b]
                for b in operand
            )
            if absolute and decode:
                del cell_cells[c]
                decoded.append((f"hit{len(decoded)}", hit, operand))
            else:
                rest.append((where, v, w))
            continue
        other = "A" if p == "B" else "B"
        operand = cl["connections"].get(other, [])
        absolute = operand and all(
            not isinstance(b, str)
            and b in token_of
            and "rel" not in token_of[b]
            and "mod" not in token_of[b]
            and "@" not in token_of[b]
            for b in operand
        )
        if (
            decode
            and cl["type"] == "$eq"
            and absolute
            and len(cl["connections"]["Y"]) == 1
        ):
            hit = cl["connections"]["Y"][0]
            del cell_cells[c]
            decoded.append((f"hit{len(decoded)}", hit, operand))
        else:
            rest.append(((c, p), v, w))
    for where, _, w in rest:
        c, p = where[0], where[1]
        if p == "EQ":
            if decode:
                fail(f"an index comparison in {c} reads bits that differ per entry")
            # keep-idx: the form's root reads x == idx; its inner cells
            # stay and their output is unused
            cl = cell_cells[c]
            y = cl["connections"][outputs(cl)[0]]
            operand = list(where[2])
            cell_cells[c] = {
                "hide_name": 1,
                "type": "$eq",
                "attributes": {},
                "parameters": {
                    "A_SIGNED": "0",
                    "A_WIDTH": format(len(operand), "032b"),
                    "B_SIGNED": "0",
                    "B_WIDTH": format(iw, "032b"),
                    "Y_WIDTH": format(1, "032b"),
                },
                "port_directions": {"A": "input", "B": "input", "Y": "output"},
                "connections": {"A": operand, "B": idx, "Y": y},
            }
            if v_sense(e, where) == "NE":
                cell_cells[c]["type"] = "$ne"
            continue
        cell_cells[c]["connections"][p] = [idx[k] if k < iw else "0" for k in range(w)]
    sites = rest
    ports = {}
    netnames = {}
    for k, tok in enumerate(tokens):
        ports[f"in{k}"] = {"direction": "input", "bits": [tw["tokens"][tok]]}
    if sites:
        ports["idx"] = {"direction": "input", "bits": idx}
    for hp, hit, _ in decoded:
        ports[hp] = {"direction": "input", "bits": [hit]}
    template_cells = cells_of(t)
    for k, (pos, p, kb) in enumerate(outs):
        ports[f"out{k}"] = {
            "direction": "output",
            "bits": [d.cells[template_cells[pos]]["connections"][p][kb]],
        }
    for pn, v in ports.items():
        netnames[pn] = {"hide_name": 0, "bits": v["bits"], "attributes": {}}
    for c in template_cells:
        if d.cells[c]["type"] in FLOPS:
            netnames[c.replace("$driver$", "") + "_q"] = {
                "hide_name": 0,
                "bits": d.cells[c]["connections"]["Q"],
                "attributes": {},
            }
    cell_mod = {
        "attributes": {"keep_hierarchy": "00000000000000000000000000000001"},
        "ports": ports,
        "cells": cell_cells,
        "netnames": netnames,
    }

    # the module: every entry's private cells and registers become an instance
    cell_name = name + "Entry"
    parent = copy.deepcopy(mod)
    for i in range(n):
        for c in private(i):
            del parent["cells"][c]
    next_id = [max(idx) + 1]
    one_hot = {}
    for hp, _, operand in decoded:
        y = list(range(next_id[0], next_id[0] + n))
        next_id[0] += n
        # the operand's bits are shared, the same for every entry
        parent["cells"][f"$decode_once${hp}"] = {
            "hide_name": 1,
            "type": "$shl",
            "parameters": {
                "A_SIGNED": "0",
                "A_WIDTH": format(n, "032b"),
                "B_SIGNED": "0",
                "B_WIDTH": format(len(operand), "032b"),
                "Y_WIDTH": format(n, "032b"),
            },
            "attributes": {},
            "port_directions": {"A": "input", "B": "input", "Y": "output"},
            "connections": {"A": ["1"] + ["0"] * (n - 1), "B": operand, "Y": y},
        }
        parent["netnames"][f"decode_once_{hp}"] = {
            "hide_name": 0,
            "bits": y,
            "attributes": {},
        }
        one_hot[hp] = y
    for i in range(n):
        w = e.walks[i]
        conns, dirs = {}, {}
        for k, tok in enumerate(tokens):
            conns[f"in{k}"] = [w["tokens"][tok]]
            dirs[f"in{k}"] = "input"
        if sites:
            conns["idx"] = ["1" if i >> k & 1 else "0" for k in range(iw)]
            dirs["idx"] = "input"
        for hp, _, _ in decoded:
            conns[hp] = [one_hot[hp][i]]
            dirs[hp] = "input"
        mine = cells_of(i)
        for k, (pos, p, kb) in enumerate(outs):
            conns[f"out{k}"] = [d.cells[mine[pos]]["connections"][p][kb]]
            dirs[f"out{k}"] = "output"
        parent["cells"][f"entry_{i}"] = {
            "hide_name": 0,
            "type": cell_name,
            "parameters": {},
            "attributes": {},
            "port_directions": dirs,
            "connections": conns,
        }
    # each entry's registers in the cell, by the template's names: what a
    # check renames the flattened cell's flops back to
    renames = {
        f"entry_{i}.{tf}": f for i in range(n) for tf, f in zip(e.flops[t], e.flops[i])
    }
    stats = {
        "entries": n,
        "arrays": len(e.arrs),
        "cell_cells": len(cell_cells),
        "inputs": len(tokens),
        "outputs": len(outs),
        "index_sites_left": len(sites),
        "decoded_once": len(decoded),
        "kept_out": sorted(keep_out),
        "register_bits": sum(len(d.cells[f]["connections"]["Q"]) for f in e.flops[0])
        * n,
    }
    return {cell_name: cell_mod, name: parent}, stats, renames


def main(argv):
    src, name, out = argv[1:4]
    decode = "--keep-idx" not in argv
    design = json.load(open(src))
    mods, stats, renames = extract(design["modules"][name], name, decode)
    design["modules"].update(mods)
    with open(out, "w") as f:
        json.dump(design, f)
    with open(out + ".renames", "w") as f:
        json.dump(renames, f)
    print("extract: " + ", ".join(f"{k} {v}" for k, v in stats.items()))


if __name__ == "__main__":
    main(sys.argv)
