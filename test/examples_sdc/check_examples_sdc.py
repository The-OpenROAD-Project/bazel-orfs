#!/usr/bin/env python3
"""The shipped example SDC constrains I/O as targets, not as delays.

examples/constraints.sdc is the file a reader copies before writing
constraints of their own, so what it demonstrates propagates. It
demonstrates the asap7 model: register-to-register is the only path that
can fail closure, and everything touching a port is an optimization
target expressed with set_max_delay.

Two things this asserts, and both are about what a copy of the file
would inherit:

  no set_input_delay / set_output_delay
      The number either takes is measured from the clock insertion
      point, so writing one means assuming a clock tree that does not
      exist yet. It also demands hold fixing on every I/O path, which
      buys hold buffers -- area and leakage -- for a constraint the
      environment may not impose at all.

  the four path groups
      Without them a timing report says a path is tight without saying
      which kind, and the kinds are not equally interesting: reg2reg is
      the one that can fail.

Comments are stripped first. The file explains at length why it does not
use set_input_delay, so a check that matched the raw text would fail on
the explanation -- which is the sort of test that gets deleted rather
than fixed.
"""

import argparse
import re
import sys

FORBIDDEN = ("set_input_delay", "set_output_delay")
REQUIRED_GROUPS = ("in2reg", "reg2out", "reg2reg", "in2out")


def strip_comments(text):
    """Tcl comments, which start at an unquoted # and run to end of line."""
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


def check(text):
    """Return a list of problems; empty means the example is well formed."""
    code = strip_comments(text)
    problems = []

    for name in FORBIDDEN:
        if re.search(r"\b%s\b" % re.escape(name), code):
            problems.append(
                "{} is used. The example is what a reader copies, and this "
                "one constrains I/O with set_max_delay targets instead -- "
                "see the comment in the file for why.".format(name)
            )

    if "set_max_delay" not in code:
        problems.append(
            "no set_max_delay: the I/O budget is what replaces the delays"
        )

    groups = set(re.findall(r"group_path\s+-name\s+(\S+)", code))
    for want in REQUIRED_GROUPS:
        if want not in groups:
            problems.append(
                "no '{}' path group, so a report cannot say which kind of "
                "path is tight; found {}".format(want, sorted(groups) or "none")
            )
    return problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdc", nargs="+")
    args = parser.parse_args(argv[1:])

    failed = False
    for path in args.sdc:
        with open(path) as f:
            problems = check(f.read())
        if problems:
            failed = True
            print("{}: FAILED".format(path), file=sys.stderr)
            for p in problems:
                print("  " + p, file=sys.stderr)
        else:
            print("{}: OK".format(path))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
