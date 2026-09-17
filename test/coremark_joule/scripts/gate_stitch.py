#!/usr/bin/env python3
"""Assemble the RTL a gate-level netlist still needs to simulate.

A hierarchical parent's netlist instantiates its hardened blocks and its
SRAM macros as cells: module names with no body. The behavioural models
for both are the RTL modules of the same names, one file each in the
split-Verilog directory firtool wrote. The uncore around the core -- the
SoC wrapper, the bus, the memory behind DPI -- is RTL too. So the file
this writes is the closure of RTL modules reachable from the simulation
top, stopping at every module the netlist defines (the core itself), plus
the closure of every module the netlist instantiates but does not define
(the blocks, the memories), stopping nowhere.

Standard cells are the one kind of undefined name that is allowed: they
come from the cell-model library, and they are recognised by a suffix
(--cell-suffix). Any other undefined name with no RTL file is an error,
listed by name, because a module that silently vanishes from a
simulation is a memory that stores nothing.
"""

import argparse
import json
import os
import re
import sys

_MODULE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z_0-9$]*)", re.M)
# `Foo foo_inst (` or `Foo #(...) foo_inst (`, at the start of a line.
_INSTANCE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z_0-9$]*)\s+(?:#\([^;]*?\)\s*)?[A-Za-z_\\][^\s(]*\s*\(", re.M
)
_KEYWORDS = {
    "module",
    "input",
    "output",
    "inout",
    "wire",
    "reg",
    "assign",
    "always",
    "initial",
    "parameter",
    "localparam",
    "logic",
    "integer",
    "genvar",
    "function",
    "task",
    "if",
    "else",
    "for",
    "case",
    "endmodule",
    "begin",
    "end",
    "posedge",
    "negedge",
    "typedef",
    "generate",
    "endgenerate",
    "unique",
    "priority",
    "default",
    "return",
    "automatic",
}


def instantiated(text):
    """Module names in instantiation position, keywords excluded."""
    return {m for m in _INSTANCE.findall(text) if m not in _KEYWORDS}


def rtl_index(directory):
    """Module name -> path, for every .sv/.v file in the directory."""
    index = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith((".sv", ".v")):
            continue
        stem = name.rsplit(".", 1)[0]
        index[stem] = os.path.join(directory, name)
    return index


def stitch(netlist_text, rtl, top, cell_suffixes):
    """Return (ordered module names to include, report dict).

    Raises ValueError with the offending names when an instantiated
    module has neither a netlist body, an RTL file nor a cell suffix.
    """
    defined = set(_MODULE.findall(netlist_text))
    from_netlist = instantiated(netlist_text) - defined

    included = []
    seen = set()
    missing = set()

    def walk(name):
        if name in seen or name in defined:
            return
        seen.add(name)
        if name not in rtl:
            if not any(name.endswith(s) or s in name for s in cell_suffixes):
                missing.add(name)
            return
        with open(rtl[name], errors="replace") as f:
            text = f.read()
        for child in sorted(instantiated(text)):
            walk(child)
        included.append(name)

    walk(top)
    uncore = len(included)
    for name in sorted(from_netlist):
        walk(name)

    if missing:
        raise ValueError(sorted(missing))
    report = {
        "top": top,
        "netlist_defines": sorted(defined),
        "netlist_instantiates_undefined": sorted(n for n in from_netlist if n in rtl),
        "cells_seen": sorted(n for n in from_netlist if n not in rtl),
        "uncore_modules": uncore,
        "block_and_memory_modules": len(included) - uncore,
        "modules": included,
    }
    return included, report


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--netlist", required=True, help="the parent's gate-level netlist"
    )
    parser.add_argument(
        "--rtl-dir", required=True, help="firtool split-Verilog directory"
    )
    parser.add_argument(
        "--top", required=True, help="simulation top module, e.g. cm_soc"
    )
    parser.add_argument(
        "--cell-suffix",
        action="append",
        default=[],
        help="substring marking a standard cell (repeatable), e.g. _ASAP7_",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", help="JSON summary of what was included")
    args = parser.parse_args(argv[1:])

    with open(args.netlist, errors="replace") as f:
        netlist_text = f.read()
    rtl = rtl_index(args.rtl_dir)
    try:
        included, report = stitch(netlist_text, rtl, args.top, args.cell_suffix)
    except ValueError as e:
        print(
            "gate_stitch: the netlist instantiates modules with no body, no RTL "
            "file and no cell suffix:\n  " + "\n  ".join(e.args[0]),
            file=sys.stderr,
        )
        return 1

    with open(args.out, "w") as out:
        for name in included:
            with open(rtl[name], errors="replace") as f:
                for line in f:
                    # Every included file is in this concatenation already.
                    if line.lstrip().startswith("`include"):
                        continue
                    out.write(line)
            out.write("\n")
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    print(
        "gate_stitch: {} uncore modules from {}, {} block/memory modules the "
        "netlist instantiates, {} cell kinds".format(
            report["uncore_modules"],
            args.top,
            report["block_and_memory_modules"],
            len(report["cells_seen"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
