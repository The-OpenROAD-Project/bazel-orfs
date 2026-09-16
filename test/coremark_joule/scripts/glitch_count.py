"""Count transitions in a VCD, bucketed by scope and by what the CPU is doing.

Glitch power is the power in transitions that the logic function does not
require: a node settles to its final value only after its inputs have
finished arriving, and every intermediate value it passed through
charged a real capacitance on the way (5.2). A cycle-based simulator
cannot produce one, so this reads a timing-annotated event-driven run and
the same window run at zero delay, and the difference is the glitch.

Three things are counted at once, because they come from one pass:

- transitions in the whole core, which is the quantity 5.2 is missing;
- transitions inside one module subtree, named by --subtree. The
  multiplier is the structure the literature names as the worst
  offender, and in this netlist it is a preserved module boundary rather
  than a naming convention;
- the cycles that module spends busy, from a signal named by --busy,
  because a unit that is idle most of the time contributes glitch in
  proportion to how often it runs -- and that fraction is what changes
  as a core gets faster.

Counts are aggregated as they stream. A VCD for a real design over a
useful window is tens of gigabytes and must never be held in memory or,
preferably, written to disk at all.
"""

import argparse
import json
import re
import sys

_VAR = re.compile(r"\$var\s+\S+\s+(\d+)\s+(\S+)\s+([^\s$]+)")


def parse_header(stream):
    """Return (ids, width) where ids maps identifier -> full scope path."""
    path, ids, width = [], {}, {}
    for line in stream:
        s = line.strip()
        if s.startswith("$scope"):
            parts = s.split()
            if len(parts) >= 3:
                path.append(parts[2])
        elif s.startswith("$upscope"):
            if path:
                path.pop()
        elif s.startswith("$var"):
            m = _VAR.search(s)
            if m:
                w, ident, name = int(m.group(1)), m.group(2), m.group(3)
                ids.setdefault(ident, "/".join(path + [name]))
                width[ident] = w
        elif s.startswith("$enddefinitions"):
            return ids, width
    return ids, width


def bit_changes(old, new):
    """Transitions between two vector values, counted per bit.

    A net is a net: a 32-bit bus that changes in three bit positions has
    toggled three nets, not one. Unknown values are not transitions.
    """
    if old is None:
        return 0
    n = max(len(old), len(new))
    old = old.rjust(n, old[0] if old and old[0] in "xzXZ" else "0")
    new = new.rjust(n, new[0] if new and new[0] in "xzXZ" else "0")
    return sum(
        1
        for a, b in zip(old, new)
        if a != b and a in "01" and b in "01"
    )


def count(stream, subtree=None, busy=None, clock=None, pc=None):
    """Stream a VCD body, aggregating counts. Returns a dict."""
    ids, width = parse_header(stream)
    in_subtree = {
        i for i, p in ids.items() if subtree and subtree in p
    }
    busy_ids = {i for i, p in ids.items() if busy and p.endswith(busy)}
    clock_ids = {i for i, p in ids.items() if clock and p.endswith(clock)}
    pc_ids = {i for i, p in ids.items() if pc and p.endswith(pc)}

    values = {}
    total = subtree_total = 0
    cycles = busy_cycles = 0
    busy_now = False
    pc_now = None
    per_pc = {}

    for line in stream:
        s = line.strip()
        if not s:
            continue
        if s[0] == "#":
            continue
        if s[0] in "bBrR":
            parts = s.split()
            if len(parts) != 2:
                continue
            val, ident = parts[0][1:], parts[1]
        elif s[0] in "01xzXZ":
            val, ident = s[0], s[1:]
        else:
            continue
        if not ident:
            continue
        prev = values.get(ident)
        values[ident] = val
        if ident in clock_ids:
            if prev == "0" and val == "1":
                cycles += 1
                if busy_now:
                    busy_cycles += 1
                if pc_now is not None:
                    per_pc[pc_now] = per_pc.get(pc_now, 0) + 1
            continue
        if ident in busy_ids:
            busy_now = val == "1"
        if ident in pc_ids:
            pc_now = val
        n = 1 if width.get(ident, 1) == 1 else bit_changes(prev, val)
        if width.get(ident, 1) == 1:
            if prev is None or prev == val or prev not in "01" or val not in "01":
                n = 0
        total += n
        if ident in in_subtree:
            subtree_total += n

    return {
        "transitions_total": total,
        "transitions_subtree": subtree_total,
        "subtree": subtree,
        "cycles": cycles,
        "busy_cycles": busy_cycles,
        "busy_fraction": (busy_cycles / cycles) if cycles else 0.0,
        "signals": len(ids),
        "signals_in_subtree": len(in_subtree),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("vcd", help="- for stdin, so a simulator can pipe into this")
    ap.add_argument("--subtree", help="scope substring to count separately")
    ap.add_argument("--busy", help="signal whose high level means the subtree is working")
    ap.add_argument("--clock", default="clk", help="signal whose posedge is a cycle")
    ap.add_argument("--pc", help="signal carrying the fetch address")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    stream = sys.stdin if args.vcd == "-" else open(args.vcd, errors="replace")
    result = count(stream, args.subtree, args.busy, args.clock, args.pc)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        open(args.out, "w").write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
