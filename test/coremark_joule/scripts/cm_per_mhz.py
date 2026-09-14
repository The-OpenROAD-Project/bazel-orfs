#!/usr/bin/env python3
"""CoreMark/MHz from a two-iteration and a three-iteration cycle count.

    CoreMark/MHz = 1e6 / (cycles_3 - cycles_2)

CoreMark's score is iterations per second. At f Hz with C cycles per
iteration that is f/C, and dividing by f/1e6 gives 1e6/C -- so the
frequency cancels and what is left is a property of the core and the
binary alone. The frequency comes back in only for CoreMark/Joule.

Taking C as a difference rather than as a single run's total is what
removes CoreMark's ten-second run rule from the problem: everything the
two runs share -- reset, .bss zeroing, data init, the CRC checks, the
whole printed report -- subtracts out, leaving exactly one iteration.

This is not a reportable CoreMark score. A three-iteration run does not
satisfy CoreMark's run rules, so the number is comparable within this
study and not against published figures.

Usage: cm_per_mhz.py --cycles-2 A --cycles-3 B --report R --out O
"""

import argparse
import json
import re
import sys

_FLAGS = re.compile(r"^CoreMark 1\.0 : .*? / (.*)$")


def read_count(path):
    with open(path) as f:
        return int(f.read().strip())


def build_flags(report_text):
    """CoreMark echoes COMPILER_VERSION and COMPILER_FLAGS in its report.

    Carrying them into the result means a number can always be traced to
    the binary that produced it without consulting the BUILD file that
    happened to be checked out at the time.
    """
    for line in report_text.splitlines():
        m = _FLAGS.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles-2", required=True)
    parser.add_argument("--cycles-3", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])

    c2 = read_count(args.cycles_2)
    c3 = read_count(args.cycles_3)
    delta = c3 - c2

    if delta <= 0:
        # Not an arithmetic guard but a correctness one: a non-positive
        # difference means the two runs are not what they claim to be --
        # the same image ran twice, or the extra iteration did no work.
        print(
            "cm_per_mhz: cycles_3 ({}) is not greater than cycles_2 ({}); the "
            "two runs did not differ by one iteration".format(c3, c2),
            file=sys.stderr,
        )
        return 1

    with open(args.report) as f:
        report = f.read()

    result = {
        "coremark_per_mhz": 1e6 / delta,
        "cycles_2": c2,
        "cycles_3": c3,
        "cycles_per_iteration": delta,
        "build_flags": build_flags(report),
    }

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    print(
        "cm_per_mhz: {:.4f} CoreMark/MHz ({} cycles/iteration)".format(
            result["coremark_per_mhz"], delta
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
