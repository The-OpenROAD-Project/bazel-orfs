#!/usr/bin/env python3
"""Rank the block stretches of reg2reg paths above a period: surgery candidates.

    crossings.py XSTile_crossings.tsv [--above 2000] [--top 25]

Reads sta_flat.tcl's STA_CROSSINGS output: one line per endpoint, its
period, its class (classify.tcl), then each part its worst path runs
through as part:entry_net:exit_net:ps, a block's nets named inside the
block (the nets of the ports the path crosses). A stretch in a block is
where a surgery would act:

- out:   the path starts in the block; its logic after the last flop, to
         the output port it leaves by
- in:    the path ends in the block; its logic from the input port it
         enters by, to the first flop
- thru:  the path passes through the block, in at one port and out at
         another with no flop between (surgery's in2out case)

Ports are folded into groups (bit and index numbers to N), and each group
is ranked by the endpoints whose worst path crosses it: how many, how far
above the period in sum (the mass a fix would remove), and the time spent
inside the block.
"""

import argparse
import re
import sys


def port_group(net):
    """A port's net, its bit and index numbers folded: io_x_2_bits[5] is
    io_x_N_bits."""
    name = re.sub(r"\[\d+\]$", "", net)
    return re.sub(r"_\d+(?=_|$)", "_N", name)


def parse(line):
    """(period, class, [(part, entry, exit, ps), ...]) of one line."""
    fields = line.rstrip("\n").split("\t")
    stretches = []
    for f in fields[2:]:
        if f.startswith(("M=", "L=")):
            continue
        part, entry, exit_, ps = f.split(":")
        stretches.append((part, entry, exit_, int(ps)))
    return int(fields[0]), fields[1], stretches


def keys(stretches, parent):
    """The (kind, block, port group(s)) a path's block stretches give, with
    the time spent in each."""
    out = []
    n = len(stretches)
    for i, (part, entry, exit_, ps) in enumerate(stretches):
        if part == parent or n == 1:
            continue
        if 0 < i < n - 1:
            out.append((("thru", part, port_group(entry), port_group(exit_)), ps))
        elif i == 0:
            out.append((("out", part, port_group(exit_)), ps))
        else:
            out.append((("in", part, port_group(entry)), ps))
    return out


def rank(lines, above, parent):
    """{key: [endpoints, excess ps summed, worst period, block ps summed]}"""
    table = {}
    for line in lines:
        if not line.strip():
            continue
        period, _, stretches = parse(line)
        if period <= above:
            continue
        for key, ps in keys(stretches, parent):
            row = table.setdefault(key, [0, 0, 0, 0])
            row[0] += 1
            row[1] += period - above
            row[2] = max(row[2], period)
            row[3] += ps
    return table


def render(table, top):
    rows = sorted(table.items(), key=lambda kv: -kv[1][1])[:top]
    lines = [
        "| kind | block | port group(s) | endpoints | excess, ps summed | worst, ps | in block, ps mean |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, (n, excess, worst, block_ps) in rows:
        kind, block = key[0], key[1]
        ports = " → ".join(key[2:])
        lines.append(
            f"| {kind} | {block} | `{ports}` | {n:,} | {excess:,} | {worst:,} | {block_ps // n:,} |"
        )
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tsv")
    ap.add_argument("--above", type=int, default=2000)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--parent", default="XSTile")
    args = ap.parse_args(argv)
    with open(args.tsv) as f:
        table = rank(f, args.above, args.parent)
    print(render(table, args.top))


if __name__ == "__main__":
    main(sys.argv[1:])
