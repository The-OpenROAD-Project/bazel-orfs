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

from entries import FLOPS, OUT, Design, Entries, outputs, plan

TEMPLATE = 1


def fail(msg):
    sys.exit(f"extract: {msg}")


def v_sense(e, where):
    """EQ, NE, GE or LT: how the walk read the form at where."""
    return e._eq_form(where[0])[0]


def extract(mod, name, decode=True):
    d = Design(mod)
    groups = [e for e in plan(d) if e.uniform]
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
        e = Entries(d, e.n, arrays, e.read, e.thresholds, e.common_read)
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
        # a threshold's K may be the index plus a constant (x >= i + 1)
        if tw["consts"][k][0][1] == "GE":
            if s != 1 or o < 1:
                fail(f"threshold site {k} is {s} * i + {o}, not i + o with o >= 1")
        elif (s, o) != (1, 0):
            fail(f"constant site {k} is {s} * i + {o}, not the index itself")
    tokens = sorted(tw["tokens"])
    for i in range(n):
        if sorted(e.walks[i]["tokens"]) != tokens:
            fail(f"entry {i} reads other boundary bits than the template")
        if len(cells_of(i)) != len(cells_of(t)):
            fail(
                f"entry {i} has {len(cells_of(i))} cells, the template {len(cells_of(t))}"
            )
    # one port per bit: a bit read in two columns has two tokens, which must
    # name one bit in every entry (two ports on one wire are two drivers)
    first = {}
    for tok in tokens:
        b = tw["tokens"][tok]
        if b in first:
            for i in range(n):
                w = e.walks[i]["tokens"]
                if w[tok] != w[first[b]]:
                    fail(
                        f"{first[b]} and {tok} are one bit in the template, two in entry {i}"
                    )
        else:
            first[b] = tok
    tokens = [tok for tok in tokens if first[tw["tokens"][tok]] == tok]

    # a duplicate the walk merged, read outside its entry (the read side's
    # reductions), is read as the cell it duplicates: the same type,
    # parameters and inputs
    for i in range(n):
        inside = private(i)
        same = {}
        for dup, kept in e.walks[i]["merged"].items():
            a, b = d.cells[dup]["connections"], d.cells[kept]["connections"]
            for p in outputs(d.cells[dup]):
                same.update(zip(a[p], b[p]))
        if not same:
            continue
        for c, cl in d.cells.items():
            if c in inside:
                continue
            for p, bs in cl["connections"].items():
                if p not in outputs(cl):
                    cl["connections"][p] = [same.get(x, x) for x in bs]
        for v in mod["ports"].values():
            if v["direction"] == "output" and set(v["bits"]) & set(same):
                fail(f"entry {i}: a merged duplicate drives a module output")

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
    in_parent = set()
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
                        if cl["type"] in ("$buf", "$pos"):
                            # a port buffer the walk saw through, read
                            # outside too: it stays in the module as well
                            in_parent.add(c)
                            continue
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
    # new bits inside the cell, after the index's
    fresh = [ids + 1 + iw + 1024]
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
    sites = [tw["consts"][k] + (e.index_sites[k][1],) for k in e.index_sites]
    # decode once: a comparison of the index with an operand from outside
    # the entries becomes an input of the cell, the comparison made once in
    # the module per distinct operand (a one-hot shift) and bit i handed to
    # entry i: one decoder for an operand every entry shares, one per bank
    # for a bank's pointer (i % B, i // B: the Rob's eight). A threshold,
    # x >= i + o, is bit i + o - 1 of the thermometer (1 << x) - 1, whose
    # bit j is x > j
    token_of = {b: tok for tok, b in tw["tokens"].items()}

    def outside(b):
        tok = token_of.get(b)
        return tok is not None and "rel" not in tok and "@" not in tok

    decoded = []  # (hit port, the operand's template bits, offset or None)
    rest = []
    for where, v, w, o in sites:
        c, p = where[0], where[1]
        cl = d.cells[c]
        if p in ("EQ", "GE"):
            # x == K (x >= K), however yosys wrote it: x is the form's bits
            operand = list(where[2])
            hit = cl["connections"][outputs(cl)[0]][0]
            if all(outside(b) for b in operand) and decode:
                if v_sense(e, where) in ("NE", "LT"):
                    # x != K, x < K: the cell inverts the decoder's x == K,
                    # x >= K
                    hit_in = fresh[0]
                    fresh[0] += 1
                    cell_cells[c] = {
                        "hide_name": 1,
                        "type": "$not",
                        "attributes": {},
                        "parameters": {
                            "A_SIGNED": "0",
                            "A_WIDTH": format(1, "032b"),
                            "Y_WIDTH": format(1, "032b"),
                        },
                        "port_directions": {"A": "input", "Y": "output"},
                        "connections": {"A": [hit_in], "Y": [hit]},
                    }
                    hit = hit_in
                else:
                    del cell_cells[c]
                decoded.append(
                    (f"hit{len(decoded)}", hit, operand, o if p == "GE" else None)
                )
            else:
                rest.append((where, v, w, o))
            continue
        other = "A" if p == "B" else "B"
        operand = [e.root(b)[0] for b in cl["connections"].get(other, [])]
        if (
            decode
            and cl["type"] == "$eq"
            and operand
            and all(not isinstance(b, str) and outside(b) for b in operand)
            and len(cl["connections"]["Y"]) == 1
        ):
            hit = cl["connections"]["Y"][0]
            del cell_cells[c]
            decoded.append((f"hit{len(decoded)}", hit, operand, None))
        else:
            rest.append(((c, p), v, w, o))
    for where, _, w, o in rest:
        c, p = where[0], where[1]
        if p in ("EQ", "GE"):
            if decode:
                fail(f"an index comparison in {c} reads bits that differ per entry")
            # keep-idx: the form's root reads x == idx (x >= idx + o); its
            # inner cells stay and their output is unused
            cl = cell_cells[c]
            y = cl["connections"][outputs(cl)[0]]
            operand = list(where[2])
            bound, bw = idx, iw
            if p == "GE":
                # idx + o, wide enough not to wrap
                bw = max(iw, o.bit_length()) + 1
                bound = list(range(fresh[0], fresh[0] + bw))
                fresh[0] += bw
                cell_cells[f"$threshold_bound${c}"] = {
                    "hide_name": 1,
                    "type": "$add",
                    "attributes": {},
                    "parameters": {
                        "A_SIGNED": "0",
                        "A_WIDTH": format(iw, "032b"),
                        "B_SIGNED": "0",
                        "B_WIDTH": format(bw, "032b"),
                        "Y_WIDTH": format(bw, "032b"),
                    },
                    "port_directions": {"A": "input", "B": "input", "Y": "output"},
                    "connections": {
                        "A": idx,
                        "B": [str(o >> k & 1) for k in range(bw)],
                        "Y": bound,
                    },
                }
            cell_cells[c] = {
                "hide_name": 1,
                "type": "$eq",
                "attributes": {},
                "parameters": {
                    "A_SIGNED": "0",
                    "A_WIDTH": format(len(operand), "032b"),
                    "B_SIGNED": "0",
                    "B_WIDTH": format(bw, "032b"),
                    "Y_WIDTH": format(1, "032b"),
                },
                "port_directions": {"A": "input", "B": "input", "Y": "output"},
                "connections": {"A": operand, "B": bound, "Y": y},
            }
            sense = v_sense(e, where)
            if sense != "EQ":
                cell_cells[c]["type"] = {"NE": "$ne", "GE": "$ge", "LT": "$lt"}[sense]
            continue
        cell_cells[c]["connections"][p] = [idx[k] if k < iw else "0" for k in range(w)]
    sites = rest
    # a decoder's enable: x == i read only by en && (x == i), en one bit from
    # outside the entries, is decoded with it, (1 << x) & {en}, and the cell gets
    # the one wire: en no longer reaches every cell (VirtualStoreQueue's
    # retireCarryVec_k, a serial carry, each link fanned out to 128 cells
    # before the next one). yosys may leave the conjunction in several
    # cells, one per process that reads it: each is the one wire
    cell_out_bits = {
        d.cells[cells_of(t)[pos]]["connections"][p][kb] for pos, p, kb in outs
    }
    cell_readers = collections.defaultdict(list)
    for c, cl in cell_cells.items():
        for p, bs in cl["connections"].items():
            if cl["port_directions"][p] == "input":
                for b in bs:
                    if not isinstance(b, str):
                        cell_readers[b].append((c, p))

    def enable_of(c, p):
        """en when cell c is a one-bit en && x read at its port p, else None."""
        cl = cell_cells[c]
        cn = cl["connections"]
        if cl["type"] not in ("$and", "$logic_and") or p not in ("A", "B"):
            return None
        if len(cn["A"]) != 1 or len(cn["B"]) != 1 or len(cn["Y"]) != 1:
            return None
        other = cn["B" if p == "A" else "A"][0]
        if isinstance(other, str) or not outside(other):
            return None
        if cn["Y"][0] in cell_out_bits:
            return None
        return other

    enabled = []
    for hp, hit, operand, o in decoded:
        rd = cell_readers.get(hit, [])
        ens = {enable_of(c, p) for c, p in rd}
        if not decode or o is not None or not rd or hit in cell_out_bits:
            ens = {None}
        en = ens.pop() if len(ens) == 1 else None
        if en is not None:
            ys = [cell_cells[c]["connections"]["Y"][0] for c, _ in rd]
            hit = ys[0]
            for c, _ in rd:
                del cell_cells[c]
            alias = {y: hit for y in ys[1:]}
            for cl in cell_cells.values():
                for p, bs in cl["connections"].items():
                    cl["connections"][p] = [alias.get(x, x) for x in bs]
        enabled.append((hp, hit, operand, o, en))
    decoded = enabled
    # a boundary bit the cell no longer reads (a decoded operand, an enable)
    # gets no port: the parent wires nothing into the cells for it
    read_bits = {
        b
        for cl in cell_cells.values()
        for p, bs in cl["connections"].items()
        if cl["port_directions"][p] == "input"
        for b in bs
    }
    tokens = [tok for tok in tokens if tw["tokens"][tok] in read_bits]
    ports = {}
    netnames = {}
    for k, tok in enumerate(tokens):
        ports[f"in{k}"] = {"direction": "input", "bits": [tw["tokens"][tok]]}
    if sites:
        ports["idx"] = {"direction": "input", "bits": idx}
    for hp, hit, _, _, _ in decoded:
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
        for c in private(i) - in_parent:
            del parent["cells"][c]
    next_id = [max(idx + [fresh[0]]) + 1]

    def decoder(hp, g, operand, y, o, en):
        m = len(y)
        shifted = y
        if o is not None:
            # the thermometer (1 << x) - 1: 1 << x wider than x is 0, and
            # 0 - 1 every bit set, x > j for every j as it should be
            shifted = list(range(next_id[0], next_id[0] + m))
            next_id[0] += m
            parent["cells"][f"$decode_once${hp}_{g}_minus_1"] = {
                "hide_name": 1,
                "type": "$sub",
                "parameters": {
                    "A_SIGNED": "0",
                    "A_WIDTH": format(m, "032b"),
                    "B_SIGNED": "0",
                    "B_WIDTH": format(1, "032b"),
                    "Y_WIDTH": format(m, "032b"),
                },
                "attributes": {},
                "port_directions": {"A": "input", "B": "input", "Y": "output"},
                "connections": {"A": shifted, "B": ["1"], "Y": y},
            }
        parent["cells"][f"$decode_once${hp}_{g}"] = {
            "hide_name": 1,
            "type": "$shl",
            "parameters": {
                "A_SIGNED": "0",
                "A_WIDTH": format(m, "032b"),
                "B_SIGNED": "0",
                "B_WIDTH": format(len(operand), "032b"),
                "Y_WIDTH": format(m, "032b"),
            },
            "attributes": {},
            "port_directions": {"A": "input", "B": "input", "Y": "output"},
            "connections": {
                "A": ["1"] + ["0"] * (m - 1),
                "B": operand,
                "Y": shifted,
            },
        }
        if en is not None:
            # the enable after the decode, not shifted through it as en << x:
            # yosys's shifter then carried it through every stage, and
            # LoadQueueRAR's late write slot came out of the decoder through
            # an AO32 driving 34 fF (1,052 ps against 950)
            decoded = list(range(next_id[0], next_id[0] + m))
            next_id[0] += m
            parent["cells"][f"$decode_once${hp}_{g}"]["connections"]["Y"] = decoded
            parent["cells"][f"$decode_once${hp}_{g}_en"] = {
                "hide_name": 1,
                "type": "$and",
                "parameters": {
                    "A_SIGNED": "0",
                    "A_WIDTH": format(m, "032b"),
                    "B_SIGNED": "0",
                    "B_WIDTH": format(m, "032b"),
                    "Y_WIDTH": format(m, "032b"),
                },
                "attributes": {},
                "port_directions": {"A": "input", "B": "input", "Y": "output"},
                "connections": {"A": decoded, "B": [en] * m, "Y": shifted},
            }
        parent["netnames"][f"decode_once_{hp}_{g}"] = {
            "hide_name": 0,
            "bits": y,
            "attributes": {},
        }

    one_hot = {}  # (hit port, entry) -> the entry's bit of its decoder
    for hp, _, template_operand, o, en in decoded:
        # (1 << x) & {en} where the cell's x == i had an enable: one decoder per
        # distinct operand and enable
        toks = [token_of[b] for b in template_operand + ([] if en is None else [en])]
        by_operand = collections.defaultdict(list)
        for i in range(n):
            by_operand[tuple(e.walks[i]["tokens"][t] for t in toks)].append(i)
        # entry i's bit: i of the one-hot, i + o - 1 of the thermometer
        shift = 0 if o is None else o - 1
        for g, (operand, members) in enumerate(by_operand.items()):
            y = list(range(next_id[0], next_id[0] + n + shift))
            next_id[0] += n + shift
            for i in members:
                one_hot[hp, i] = y[i + shift]
            if en is not None:
                decoder(hp, g, list(operand[:-1]), y, o, operand[-1])
            else:
                decoder(hp, g, list(operand), y, o, None)
    for i in range(n):
        w = e.walks[i]
        conns, dirs = {}, {}
        for k, tok in enumerate(tokens):
            conns[f"in{k}"] = [w["tokens"][tok]]
            dirs[f"in{k}"] = "input"
        if sites:
            conns["idx"] = ["1" if i >> k & 1 else "0" for k in range(iw)]
            dirs["idx"] = "input"
        for hp, _, _, _, _ in decoded:
            conns[hp] = [one_hot[hp, i]]
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
        "enables_decoded": sum(1 for *_, en in decoded if en is not None),
        "kept_out": sorted(keep_out),
        "register_bits": sum(len(d.cells[f]["connections"]["Q"]) for f in e.flops[0])
        * n,
    }
    return {cell_name: cell_mod, name: parent}, stats, renames


def main(argv):
    src, name, out = argv[1:4]
    decode = "--keep-idx" not in argv
    if "--no-read" in argv:
        import entries

        entries.NO_READ = True
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
