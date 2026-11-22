#!/usr/bin/env python3
"""Spell `/` inside a netlist's escaped names so a SAIF can carry them.

    slash_names.py IN.v OUT.v [--token __SL__]

A flat ODB of a hierarchically synthesised block (OPENROAD_HIERARCHICAL=0
with SYNTH_HIERARCHICAL=1) names its cells after the hierarchy they came
from, as a hierarchical ODB does a cell below a module that was not
kept, and write_verilog escapes them:

    INVx1_ASAP7_75t_R \\u_core/lane[0].u_lane/_060_  (...);

Verilator's SAIF writer prints the name as it is, `/` and all, and `/`
is the hierarchy divider in OpenSTA's SAIF lexer, with no escape: the
instance cannot be read, filter_saif.py drops it, and every pin of the
cell goes unannotated. On the toy's hierarchical BlockA
(test/coremark_joule/power_shards) that was 600 of its 1,540 cells,
1,589 of 2,309 pins annotated.

This replaces every `/` inside an escaped identifier with TOKEN, here,
on the netlist that is simulated. The block's shard does the same to the
ODB's instance names before read_saif (flow/power_shard_grt.tcl), so the
two meet exactly; `$`, `[ ]` and `.` the lexer already accepts. The map
is reversible only while no name holds TOKEN already, so a netlist that
does is refused.

Only escaped identifiers can hold a `/`; a plain one cannot, so nothing
else changes.
"""

import argparse
import re
import sys

TOKEN = "__SL__"

# a Verilog escaped identifier: a backslash, then anything but white space
_ESCAPED = re.compile(r"\\\S+")


def slash_names(text, token=TOKEN):
    """(text with `/` in escaped names spelled as token, names changed)."""
    if token in text:
        raise ValueError(
            "the netlist already holds {}; the rename would not be reversible".format(
                token
            )
        )
    changed = set()

    def spell(m):
        name = m.group(0)
        if "/" not in name:
            return name
        changed.add(name)
        return name.replace("/", token)

    return _ESCAPED.sub(spell, text), len(changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("netlist")
    parser.add_argument("out")
    parser.add_argument("--token", default=TOKEN)
    args = parser.parse_args(argv)
    with open(args.netlist) as f:
        text = f.read()
    try:
        out, n = slash_names(text, args.token)
    except ValueError as e:
        sys.stderr.write("slash_names: {}: {}\n".format(args.netlist, e))
        return 1
    with open(args.out, "w") as f:
        f.write(out)
    sys.stderr.write("slash_names: {} names spelled with {}\n".format(n, args.token))
    return 0


if __name__ == "__main__":
    sys.exit(main())
