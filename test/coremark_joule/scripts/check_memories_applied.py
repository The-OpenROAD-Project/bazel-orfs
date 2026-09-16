#!/usr/bin/env python3
"""Assert that AUTO_MEMORIES actually reached the netlist.

The flow can detect a memory, generate a .lib and .lef for it, list it in
blackboxes.txt, and then synthesise it as flip-flops anyway. Nothing
fails: the run completes, the area and power look plausible, and the
design that gets measured is not the design that was asked for. That is
the failure this checks for.

Two assertions, because either alone can pass while the other is broken:

  every expected memory is in blackboxes.txt   -- detection still works
  every blackboxed memory is instantiated      -- and the netlist uses it

The expected list is declared by the caller rather than read from the
design, so a change that stops detecting a memory altogether -- leaving
an empty blackboxes.txt and a netlist full of flops -- fails here
instead of passing vacuously.

Usage:
  check_memories_applied.py <blackboxes.txt> <netlist.v> --expect NAME [NAME ...]
"""

import argparse
import re
import sys


def read_blackboxes(path):
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def instantiation_count(netlist_path, module):
    """Count instantiations of `module` in a structural Verilog netlist.

    yosys writes an instance as `  <module> <instance> (`, so anchoring on
    the module name at the start of a line and requiring an instance name
    and an open paren distinguishes an instantiation from the module's own
    declaration or a wire that merely shares the name.
    """
    pattern = re.compile(
        r"^\s*" + re.escape(module) + r"\s+\\?\S+\s*\(",
    )
    count = 0
    with open(netlist_path) as f:
        for line in f:
            if pattern.match(line):
                count += 1
    return count


def check(blackboxes, netlist_path, expected):
    problems = []

    for name in expected:
        if name not in blackboxes:
            problems.append(
                "{!r} was expected to be inferred as a memory but is not in "
                "blackboxes.txt; detection found {}".format(
                    name, blackboxes or "nothing"
                )
            )

    for name in blackboxes:
        n = instantiation_count(netlist_path, name)
        if n == 0:
            problems.append(
                "{!r} is blackboxed as a memory but is not instantiated in the "
                "netlist: the macro was generated and then ignored, and the "
                "design was synthesised with flip-flops instead".format(name)
            )

    return problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blackboxes")
    parser.add_argument("netlist")
    parser.add_argument("--expect", nargs="+", required=True)
    args = parser.parse_args(argv[1:])

    blackboxes = read_blackboxes(args.blackboxes)
    problems = check(blackboxes, args.netlist, args.expect)

    if problems:
        print("AUTO_MEMORIES did not reach the netlist:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1

    print("AUTO_MEMORIES applied: {}".format(", ".join(sorted(blackboxes))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
