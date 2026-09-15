#!/usr/bin/env python3
"""Make instance names unique within each module of a written netlist.

OpenROAD's `write_verilog` can emit two different instances under the
same name in one module. On VeeR EH1 at global route it does it exactly
once: two AND2x2 clock cells, on different clock leaves
(`clknet_leaf_24_clk_i` and `clknet_leaf_152_clk_i`), both called
`_131758_` inside `ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp` -- one
collision among that module's 88,520 instances. The ODB's own instance
namespace is unique, so the collision is created on the way out.

The result is not valid Verilog and Verilator rejects it, which is how
it was found. That is the good case. The bad case is a tool that accepts
it and silently keeps one of the two, because then a gate-level
simulation runs a design that is not the one the power was reported on.

So this renames the later occurrences rather than dropping them, and
says what it renamed. Two consequences worth stating:

  - The renamed instance's pins carry a name the SAIF cannot match back
    to the ODB, so `read_saif` leaves them unannotated and the pin audit
    (scripts/classify_pins.py) counts them. That is the correct outcome:
    the cost of the workaround shows up as a number in the audit rather
    than disappearing.
  - `--max-renames` defaults to zero, so a netlist with no collisions
    asserts that it has none. This is a gate on every core, not a patch
    applied to one.

Carried here, not upstreamed, per the moratorium in CLAUDE.md. It
retires when a bump brings a `write_verilog` that uniquifies.

Before reporting this upstream, read OpenROAD's own history first: it has
carried fixes in this area before -- name escaping, and the hierarchical
(-hier) flow -- so the fix may already exist. A bump is cheaper than a
report, and is the first thing to try when this workaround is next
touched.
"""

import argparse
import re
import sys

# `<master> <instance> (` -- the shape of an instance declaration in the
# netlist OpenROAD writes. Deliberately narrow: a declaration keyword in
# the master position is a port or a net, not an instance.
_INSTANCE = re.compile(r"^(\s*)([A-Za-z_][\w$]*)(\s+)(\\?[\w$\[\].]+)(\s*\()")

_NOT_MASTERS = frozenset(
    ("input", "output", "inout", "wire", "reg", "assign", "parameter", "module")
)


def uniquify(lines):
    """Rewrite `lines`, renaming duplicate instance names per module.

    Returns (out_lines, renames), where renames is a list of
    (module, original_name, new_name).
    """
    out = []
    renames = []
    module = None
    seen = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("module "):
            module = stripped.split()[1].split("(")[0]
            seen = set()
            out.append(line)
            continue
        if stripped.startswith("endmodule"):
            module = None
            out.append(line)
            continue
        m = _INSTANCE.match(line) if module is not None else None
        if not m or m.group(2) in _NOT_MASTERS:
            out.append(line)
            continue
        name = m.group(4)
        if name not in seen:
            seen.add(name)
            out.append(line)
            continue
        suffix = 1
        new = "{}_uniq{}".format(name, suffix)
        while new in seen:
            suffix += 1
            new = "{}_uniq{}".format(name, suffix)
        seen.add(new)
        renames.append((module, name, new))
        out.append("{}{}{}{}{}".format(m.group(1), m.group(2), m.group(3), new, line[m.end(4):]))
    return out, renames


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist")
    parser.add_argument("out")
    parser.add_argument(
        "--max-renames",
        type=int,
        default=0,
        help="how many collisions this design is known to have. Zero "
        "turns the script into an assertion that there are none.",
    )
    args = parser.parse_args(argv[1:])

    with open(args.netlist) as f:
        lines = f.readlines()
    out, renames = uniquify(lines)

    for module, old, new in renames:
        print("uniquify_netlist: {}: {} -> {}".format(module, old, new), file=sys.stderr)

    with open(args.out, "w") as f:
        f.writelines(out)

    if len(renames) > args.max_renames:
        print(
            "uniquify_netlist: {} duplicate instance name(s), over the "
            "declared budget of {}. A netlist with collisions the design "
            "has not accounted for is a different problem from the one "
            "this works around.".format(len(renames), args.max_renames),
            file=sys.stderr,
        )
        return 1
    print("uniquify_netlist: {} rename(s), budget {}".format(len(renames), args.max_renames))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
