#!/usr/bin/env python3
"""Recompute a power shard's leakage from each cell's liberty states.

    leakage_states.py STATES.tsv --lib-dir DIR

OpenSTA (power/Power.cc, Power::findLeakagePower) weights each
conditional leakage group of a cell by the duty of its `when`
expression, from a BDD with one variable per pin and every variable's
duty independent. asap7's `when`s name the output too, "(A * !Y)" on an
inverter: the output is a function of the inputs, so the weights of the
states no longer sum to 1, and an inverter at duty d weighs its two
states d^2 and (1-d)^2 instead of d and 1-d (at d = 0.5, half its
leakage). A flop's QN is state, not a function of CLK and D, and its
weights do sum to 1.

Here every `when` is evaluated over the inputs only, the output taken as
its function of them (inputs still independent, as OpenSTA has them):
the input states are enumerated, each output computed, and each state's
probability times the leakage of the group it falls in summed. A cell
with no output in its `when`s, or with state (ff, latch, statetable),
keeps report_power's value. The same enumeration with the output taken
as an independent variable is OpenSTA's number: a check that the cell
and its duties were read as report_power read them.

STATES.tsv is leakage_states.tcl's; DIR holds the liberty files it names.
"""

import argparse
import gzip
import itertools
import os
import re
import sys


def _open(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def _cells(text):
    starts = [m for m in re.finditer(r"\n\s*cell\s*\(\s*\"?([\w$]+)\"?\s*\)", text)]
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        yield m.group(1), text[m.end() : end]


def parse_cells(text):
    """{cell: {inputs, outputs: {pin: function}, groups: [(value, when)],
    stateful}} for the VDD leakage groups of each cell."""
    out = {}
    for name, body in _cells(text):
        pins = {}
        for m in re.finditer(r"\bpin\s*\(\s*\"?(\w+)\"?\s*\)\s*\{", body):
            # the pin's own attributes, up to its first nested group
            head = body[m.end() : m.end() + 2000]
            d = re.search(r"direction\s*:\s*(\w+)", head)
            f = re.search(r'function\s*:\s*"([^"]*)"', head.split("{")[0])
            pins[m.group(1)] = (d.group(1) if d else "", f.group(1) if f else None)
        groups = []
        for m in re.finditer(r"leakage_power\s*\(\s*\)\s*\{([^}]*)\}", body):
            g = m.group(1)
            pg = re.search(r"related_pg_pin\s*:\s*\"?(\w+)", g)
            if pg and pg.group(1) != "VDD":
                continue
            v = float(re.search(r"value\s*:\s*([-\d.eE+]+)", g).group(1))
            w = re.search(r'when\s*:\s*"([^"]*)"', g)
            groups.append((v, w.group(1) if w else None))
        out[name] = {
            "inputs": [p for p, (d, _) in pins.items() if d == "input"],
            "outputs": {p: f for p, (d, f) in pins.items() if d == "output"},
            "groups": groups,
            "stateful": bool(re.search(r"\b(ff|latch|statetable)\s*\(", body)),
        }
    return out


def _py(expr):
    """A liberty boolean expression as a Python one over a dict `v`."""
    e = expr.replace("'", " ")  # postfix complement is not used by asap7
    e = re.sub(r"\b([A-Za-z_]\w*)\b", r"v['\1']", e)
    e = e.replace("!", " not ").replace("*", " and ").replace("+", " or ")
    e = e.replace("^", " != ")
    return compile(e.strip(), expr, "eval")


def leakage(cell, duties, output_free):
    """The duty-weighted leakage of one instance, in the library's unit.

    output_free: True takes an output as its function of the inputs;
    False as an independent variable with its own duty (OpenSTA)."""
    conds = [(v, _py(w)) for v, w in cell["groups"] if w]
    if not conds:
        return None
    outs = {p: _py(f) for p, f in cell["outputs"].items() if f}
    named = set()
    for _, w in cell["groups"]:
        if w:
            named |= set(re.findall(r"[A-Za-z_]\w*", w))
    if output_free:
        free = [p for p in cell["inputs"] if p in named]
    else:
        free = [p for p in cell["inputs"] + list(cell["outputs"]) if p in named]
    total = 0.0
    for bits in itertools.product((0, 1), repeat=len(free)):
        v = dict(zip(free, bits))
        p = 1.0
        for pin, b in v.items():
            d = duties.get(pin, 0.5)
            p *= d if b else 1.0 - d
        if p == 0.0:
            continue
        if output_free:
            for o, f in outs.items():
                v[o] = int(bool(eval(f, {}, {"v": v})))
        for value, f in conds:
            try:
                if eval(f, {}, {"v": v}):
                    total += p * value
            except KeyError:
                pass
    return total


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("states")
    parser.add_argument("--lib-dir", required=True)
    args = parser.parse_args(argv)
    cells = {}
    rows = []
    with open(args.states) as f:
        for line in f:
            parts = line.split()
            if parts[0] == "lib":
                path = os.path.join(args.lib_dir, parts[1])
                if not os.path.exists(path):
                    # a block's abstract: its cells keep report_power's value
                    print("not in --lib-dir, kept as reported: %s" % parts[1])
                    continue
                with _open(path) as lf:
                    cells.update(parse_cells(lf.read()))
                continue
            duties = {}
            for kv in parts[2:]:
                k, _, d = kv.partition("=")
                if d:
                    duties[k] = float(d)
            rows.append((parts[0], float(parts[1]), duties))
    unit = 1e-12  # asap7: leakage_power_unit 1pW
    reported = fixed = sta = 0.0
    by_kind = {}
    cache = {}
    for name, rep, duties in rows:
        reported += rep
        cell = cells.get(name)
        if cell is None or cell["stateful"]:
            fixed += rep
            sta += rep
            continue
        if not any(
            re.search(r"\b%s\b" % o, w or "")
            for o in cell["outputs"]
            for _, w in cell["groups"]
        ):
            fixed += rep
            sta += rep
            continue
        key = (name, tuple(sorted(duties.items())))
        if key not in cache:
            cache[key] = (leakage(cell, duties, True), leakage(cell, duties, False))
        right, theirs = cache[key]
        fixed += right * unit
        sta += theirs * unit
        kind = re.sub(r"x\w*$", "", name.split("_ASAP7")[0])
        k = by_kind.setdefault(kind, [0, 0.0, 0.0])
        k[0] += 1
        k[1] += rep
        k[2] += right * unit
    print("instances %d" % len(rows))
    print("report_power leakage           %.6g mW" % (reported * 1e3))
    print(
        "OpenSTA's weighting, recomputed %.6g mW (a check of this script)" % (sta * 1e3)
    )
    print(
        "output as function of inputs   %.6g mW (%+.1f%%)"
        % (fixed * 1e3, 100 * (fixed / reported - 1))
    )
    for kind, (n, rep, right) in sorted(
        by_kind.items(), key=lambda kv: -(kv[1][2] - kv[1][1])
    )[:12]:
        print(
            "  %-14s %7d cells  reported %.6g mW  states %.6g mW"
            % (kind, n, rep * 1e3, right * 1e3)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
