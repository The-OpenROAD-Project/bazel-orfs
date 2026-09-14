#!/usr/bin/env python3
"""Collect whatever the study has measured so far into one table.

Discovery rather than a fixed list: the report takes the result files it
was given and says what is in them. A configuration nobody has run yet is
absent, and absence is reported as "not yet measured" rather than as a
gap the reader has to notice. That keeps the report honest while the
study is half-finished, which is most of its life.

Usage: report.py <result.json> [<result.json> ...]
"""

import argparse
import json
import os
import sys

# Every configuration the study intends to cover. Listed here so a
# missing measurement is visible as a row rather than as nothing at all.
EXPECTED = [
    ("picorv32", "rv32im", "native: M extension via PCPI"),
    ("picorv32", "rv32i", "common ISA, libgcc __mulsi3"),
    ("serv", "rv32i", "native: no M extension"),
    ("ibex", "rv32imc", "native: M and C extensions"),
    ("ibex", "rv32i", "common ISA, libgcc __mulsi3"),
]


def key_from_path(path):
    """Result files are named <core>_<isa>_per_mhz.json."""
    base = os.path.basename(path)
    stem = base[: -len("_per_mhz.json")] if base.endswith("_per_mhz.json") else base
    core, _, isa = stem.partition("_")
    return core, isa


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="*")
    args = parser.parse_args(argv[1:])

    measured = {}
    for path in args.results:
        with open(path) as f:
            measured[key_from_path(path)] = json.load(f)

    print()
    print("CoreMark/MHz")
    print()
    print(
        "{:<10} {:<9} {:>14} {:>16}  {}".format(
            "core", "isa", "CoreMark/MHz", "cycles/iter", "note"
        )
    )
    print("-" * 78)

    for core, isa, note in EXPECTED:
        row = measured.get((core, isa))
        if row is None:
            print(
                "{:<10} {:<9} {:>14} {:>16}  {}".format(
                    core, isa, "-", "not yet measured", note
                )
            )
            continue
        print(
            "{:<10} {:<9} {:>14.4f} {:>16,}  {}".format(
                core,
                isa,
                row["coremark_per_mhz"],
                row["cycles_per_iteration"],
                note,
            )
        )

    unexpected = sorted(set(measured) - {(c, i) for c, i, _ in EXPECTED})
    for core, isa in unexpected:
        row = measured[(core, isa)]
        print(
            "{:<10} {:<9} {:>14.4f} {:>16,}  (not in the expected set)".format(
                core, isa, row["coremark_per_mhz"], row["cycles_per_iteration"]
            )
        )

    print()
    print("Not a reportable CoreMark score: a three-iteration run does not")
    print("satisfy CoreMark's run rules. Comparable within this study only.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
