"""Classify the register arrays array_reroll left as registers.

Reads yosys's JSON of a design after `proc; opt -fast; array_reroll`,
groups the word registers of each array by name (slang names a packed
array's words `$driver$<array>[<i>]`), and names the structure from how
its words are updated and read:

  counter     a word's next value is its own value through an adder
  flags       words written with constants (set, clear) under per-word
              selects, a range compare among them for a range clear
  cam         every word compared against one shared key
  reduction   every word combined with a shared vector and reduced
              (an age matrix's oldest-select)

and writes one spec per array in generate_array's syntax: words, bits,
kind, and the signals that select rows. A prototype: the rules are
written against test/array_toys and move into the yosys plugin once they
hold on real designs.

    classify.py <design.json> [--module PREFIX]
"""

import argparse
import collections
import json
import re
import sys

_WORD = re.compile(r"^(?:\$driver\$)?(?P<base>.+)\[(?P<i>\d+)\]$")
_REGS = {"$dff", "$sdff", "$adff", "$dffe", "$sdffe", "$sdffce", "$adffe"}
_CONE_LIMIT = 5000000


class Module:
    def __init__(self, mod):
        self.cells = mod["cells"]
        self.names = {}
        for name, net in mod.get("netnames", {}).items():
            for bit in net["bits"]:
                if not isinstance(bit, str) and (
                    bit not in self.names or name.startswith("\\") is False
                ):
                    self.names.setdefault(bit, name)
        self.driver = {}
        self.readers = collections.defaultdict(list)
        for name, cell in self.cells.items():
            for port, bits in cell["connections"].items():
                out = cell["port_directions"][port] == "output"
                for bit in bits:
                    if isinstance(bit, str):
                        continue
                    if out:
                        self.driver[bit] = name
                    else:
                        self.readers[bit].append((name, port))

    def ins(self, name):
        cell = self.cells[name]
        return [
            (p, b)
            for p, b in cell["connections"].items()
            if cell["port_directions"][p] == "input"
        ]

    def cone(self, bits, stop):
        """Cells in the fan-in of bits, not crossing the cells in stop."""
        seen, todo = set(), [b for b in bits if not isinstance(b, str)]
        while todo and len(seen) < _CONE_LIMIT:
            bit = todo.pop()
            name = self.driver.get(bit)
            if name is None or name in seen or name in stop:
                continue
            seen.add(name)
            for _, b in self.ins(name):
                todo.extend(x for x in b if not isinstance(x, str))
        return seen

    def signal(self, bits):
        """A readable name for a signal: its net name, or a constant."""
        if all(isinstance(b, str) for b in bits):
            return "'" + "".join(reversed(bits))
        names = {self.names.get(b, "?") for b in bits if not isinstance(b, str)}
        return "/".join(sorted(n.lstrip("\\") for n in names))


def _const(bits):
    return all(isinstance(b, str) and b in "01" for b in bits)


def _value(bits):
    return int("".join(reversed(bits)), 2)


def arrays(mod, m):
    """The register arrays of a module: base name -> words in index order."""
    groups = collections.defaultdict(dict)
    for name, cell in m.cells.items():
        if cell["type"] not in _REGS:
            continue
        match = _WORD.match(name)
        if match:
            groups[match["base"]][int(match["i"])] = name
    out = {}
    for base, words in groups.items():
        n = max(words) + 1
        if len(words) == n and n > 1:
            out[base] = [words[i] for i in range(n)]
    return out


def classify(m, base, words):
    w = len(m.cells[words[0]]["connections"]["Q"])
    regs = set(words)
    q = [m.cells[r]["connections"]["Q"] for r in words]
    qbits = {b: i for i, bits in enumerate(q) for b in bits}
    # the fan-in of every word's next value, walked once: per-word walks
    # repeat the shared decode logic once per word
    allcone = m.cone([b for r in words for b in m.cells[r]["connections"]["D"]], regs)
    types = collections.Counter(m.cells[c]["type"] for c in allcone)

    # an adder in that fan-in fed by a word's own value
    arith = 0
    for i, bits in enumerate(q):
        if any(
            m.cells[name]["type"] in ("$sub", "$add") and name in allcone
            for b in bits
            for name, _ in m.readers.get(b, [])
        ):
            arith += 1

    # selects: a signal compared with each word's own index, or decoded
    selects = collections.Counter()
    ranges = collections.Counter()
    for c in allcone:
        cell = m.cells[c]
        if cell["type"] in ("$eq", "$ge", "$gt", "$le", "$lt"):
            a, b = cell["connections"]["A"], cell["connections"]["B"]
            for sig, other in ((a, b), (b, a)):
                if _const(other) and not _const(sig) and _value(other) < len(words):
                    target = selects if cell["type"] == "$eq" else ranges
                    target[m.signal(sig)] += 1
        elif cell["type"] == "$demux":
            selects[m.signal(cell["connections"]["S"])] += 1

    # constant data written into the words: set and clear
    const_writes = 0
    for c in allcone:
        cell = m.cells[c]
        if cell["type"] in ("$mux", "$bwmux", "$pmux"):
            for port in ("A", "B"):
                bits = cell["connections"].get(port, [])
                if bits and _const(bits) and len(set(bits)) == 1:
                    const_writes += 1

    # how the words are read: each word against one shared key, or each
    # word combined with one shared vector
    keys = collections.Counter()
    shared = collections.Counter()
    for i, bits in enumerate(q):
        for b in bits:
            for name, port in m.readers.get(b, []):
                if name in allcone:
                    continue
                cell = m.cells[name]
                other = "B" if port == "A" else "A"
                if other not in cell["connections"]:
                    continue
                obits = cell["connections"][other]
                if any(qbits.get(x) is not None for x in obits):
                    continue
                if cell["type"] == "$eq":
                    keys[m.signal(obits)] += 1
                elif cell["type"] in ("$and", "$or"):
                    shared[m.signal(obits)] += 1
    n = len(words)
    key = next((k for k, c in keys.items() if c >= n), None)
    vector = next((k for k, c in shared.items() if c >= n), None)

    if arith >= n:
        kind = "counter"
    elif key is not None:
        kind = "cam"
    elif vector is not None:
        kind = "reduction"
    elif const_writes and (selects or ranges):
        kind = "flags"
    else:
        kind = None
    spec = {
        "name": base,
        "words": n,
        "bits": w,
        "kind": kind,
        "selects": sorted(selects),
        "ranges": sorted(ranges),
        "key": key,
        "vector": vector,
        "cells": dict(types.most_common(6)),
    }
    return spec


def spec_text(s):
    lines = [
        f"name {s['name']}  words {s['words']}  bits {s['bits']}  kind {s['kind']}"
    ]
    lines += [f"select decode({sel})" for sel in s["selects"]]
    lines += [f"select range({r})" for r in s["ranges"]]
    if s["key"]:
        lines.append(f"compare key({s['key']})")
    if s["vector"]:
        lines.append(f"reduce with({s['vector']})")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--module", default="")
    args = ap.parse_args()
    d = json.load(open(args.json))
    found = 0
    for name, mod in d["modules"].items():
        if not name.startswith(args.module):
            continue
        m = Module(mod)
        for base, words in arrays(mod, m).items():
            s = classify(m, base, words)
            found += 1
            if s["kind"] is None:
                print(
                    f"# {name}: {base}, {s['words']} x {s['bits']}: not classified, cells {s['cells']}"
                )
            else:
                print(f"# {name}")
                print(spec_text(s))
    if not found:
        print("# no register arrays left")


if __name__ == "__main__":
    main()
