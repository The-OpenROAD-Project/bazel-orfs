#!/usr/bin/env python3
"""Name a mapped netlist's registers for kepler-formal, the same on both sides.

kepler-formal checks combinational equivalence between registers it
matches by instance name. yosys renames cells when it maps them, so a
register is named here after the net its output drives: the reference's
name for that net. A register of a carved tile drives a net named after
the first tile's module under the tile's instance; the carve's census
maps those names to the reference's (tools/carve/carve.py, lec_names).
yosys's simple cell types become the cells of lec_cells.lib.
"""

import argparse
import json
import re
import sys

TYPES = {
    "$_AND_": "LEC_AND",
    "$_OR_": "LEC_OR",
    "$_XOR_": "LEC_XOR",
    "$_XNOR_": "LEC_XNOR",
    "$_NAND_": "LEC_NAND",
    "$_NOR_": "LEC_NOR",
    "$_ANDNOT_": "LEC_ANDNOT",
    "$_ORNOT_": "LEC_ORNOT",
    "$_NOT_": "LEC_NOT",
    "$_BUF_": "LEC_BUF",
    "$_MUX_": "LEC_MUX",
    "$_DFF_P_": "LEC_DFF",
    "$_DFF_PN0_": "LEC_DFF_PN0",
    "$_DFF_PN1_": "LEC_DFF_PN1",
    "$_DLATCH_P_": "LEC_DLATCH_P",
    "$_DLATCH_N_": "LEC_DLATCH_N",
}
REGISTERS = ("$_DFF_P_", "$_DFF_PN0_", "$_DFF_PN1_", "$_DLATCH_P_", "$_DLATCH_N_")


def bit_names(module):
    """{bit: [(hidden, name[i])]}, sorted, public names first."""
    names = {}
    for name, net in module["netnames"].items():
        for i, b in enumerate(net["bits"]):
            if not isinstance(b, str):
                names.setdefault(b, []).append(
                    (net.get("hide_name", 0), "%s[%d]" % (name, i))
                )
    return {b: sorted(v) for b, v in names.items()}


def register_name(candidates, mapping, tiles):
    """The reference's name for a register's output net."""
    for _, n in candidates:
        if n in mapping:
            return mapping[n]
    for _, n in candidates:
        if n.split(".", 1)[0] not in tiles:
            return n
    return None


def rename(design, top, mapping, tiles):
    module = design["modules"][top]
    names = bit_names(module)
    cells = {}
    for name, cell in module["cells"].items():
        t = cell["type"]
        if t not in TYPES:
            raise ValueError("cell %s: %s is not a simple cell" % (name, t))
        cell["type"] = TYPES[t]
        if t in REGISTERS:
            q = cell["connections"]["Q"][0]
            reg = register_name(names.get(q, []), mapping, tiles)
            if reg is None:
                raise ValueError(
                    "register %s drives a net with no name outside a tile" % name
                )
            name = "r_" + re.sub(r"[^A-Za-z0-9_]", "_", reg)
            if name in cells:
                raise ValueError("two registers named %s" % name)
        cells[name] = cell
    module["cells"] = cells
    return sum(1 for c in cells.values() if c["type"] in {TYPES[r] for r in REGISTERS})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", required=True, help="yosys JSON, flat, simple cells")
    parser.add_argument("--top", required=True)
    parser.add_argument(
        "--census", help="the carve's census: tile names, register names"
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.json) as f:
        design = json.load(f)
    mapping, tiles = {}, set()
    if args.census:
        with open(args.census) as f:
            census = json.load(f)
        mapping = census["lec_names"]
        tiles = {t["instance"] for t in census["tiles"]}
    try:
        n = rename(design, args.top, mapping, tiles)
    except ValueError as e:
        print("lec_names: %s" % e, file=sys.stderr)
        return 1
    with open(args.out, "w") as f:
        json.dump(design, f)
    print("lec_names: %d registers" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
