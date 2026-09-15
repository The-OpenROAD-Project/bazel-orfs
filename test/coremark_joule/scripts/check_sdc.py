#!/usr/bin/env python3
"""Every design's SDC states an IO budget, and none uses input/output delay.

§3.8 of the study's paper argues the model: a CPU core's frequency is set
by its register-to-register paths and by nothing else, because whatever
is on the other side of its pins -- a clock-crossing bridge, a bus
register, a GPIO pad -- terminates the path rather than continuing it.
Two things follow, and this checks both.

**set_input_delay and set_output_delay must not appear.** Their number is
measured from the clock insertion point, so it cannot be written down
without assuming a clock tree that does not exist yet; and using them
demands hold fixing on every IO path, buying a crop of hold buffers whose
area and leakage the core's real environment never asked for. Both land
in the power this study reports.

**The three budget variables must be set.** ASAP7's platform SDC applies
set_max_delay to in2reg, reg2out and in2out, and defaults each to 80 ps
when the design says nothing -- a figure written for a small macro, and
a twelvefold over-constraint at a 1000 ps period. An optimiser chasing
an impossible target upsizes cells and inserts buffers, and their power
is charged to the core. Silence is the dangerous case, which is why this
checks for presence rather than trusting a comment.

Comments are stripped before matching, so prose that *names*
set_input_delay in order to explain why it is absent does not trip it.
"""

import argparse
import re
import sys

FORBIDDEN = ("set_input_delay", "set_output_delay")
REQUIRED = ("in2reg_max", "reg2out_max", "in2out_max")


def strip_comments(text):
    """Tcl comments: a `#` that starts a line, ignoring leading space.

    Deliberately not a full Tcl parse. A `#` mid-line in Tcl is only a
    comment where a command could start, and a stricter rule here would
    mean either parsing Tcl or silently letting a real constraint hide
    behind one.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def check(path, text):
    """Return a list of complaints about one SDC; empty means it passes."""
    body = strip_comments(text)
    problems = []
    for name in FORBIDDEN:
        if re.search(r"\b{}\b".format(re.escape(name)), body):
            problems.append(
                "{}: uses {}. See §3.8: the delay it takes is measured from "
                "the clock insertion point, and it demands hold fixing on "
                "every IO path.".format(path, name)
            )
    for name in REQUIRED:
        if not re.search(r"\b{}\b".format(re.escape(name)), body):
            problems.append(
                "{}: does not set {}, so the platform's 80 ps default "
                "applies -- an impossible target on every path touching a "
                "port.".format(path, name)
            )
    return problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdc", nargs="+")
    args = parser.parse_args(argv[1:])

    problems = []
    for path in args.sdc:
        with open(path) as f:
            problems.extend(check(path, f.read()))

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("check_sdc: {} constraint file(s) OK".format(len(args.sdc)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
