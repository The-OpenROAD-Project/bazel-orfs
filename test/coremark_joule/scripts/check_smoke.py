#!/usr/bin/env python3
"""Check a smoke run's captured stdout.

Two independent signals, so a failure says which half broke:

  HELLO   the core fetched, decoded and executed a string loop, and the
          sim-control character register is wired up.
  M       a load/store loop read back the right sum, so the data path and
          the byte enables work. An X here means the core ran but the
          memory adapter is wrong -- the case that is otherwise invisible,
          because writing a constant string exercises no read-back.

Usage: check_smoke.py <stdout-file>
"""

import argparse
import sys

EXPECTED = "HELLO\nM\n"


def check(text):
    """Return a list of problems; empty means the run is good."""
    if text == EXPECTED:
        return []

    problems = []
    if "!" in text:
        problems.append(
            "the trap marker '!' is present: the core took an exception and "
            "crt0.S's vector stopped the run"
        )
    if "HELLO" not in text:
        problems.append(
            "no HELLO: the core never executed the string loop, so it did "
            "not boot, or the character register is not wired up"
        )
    if "X" in text:
        problems.append(
            "X: the load/store loop read back the wrong sum, so the core "
            "ran but the data path or the byte enables are wrong"
        )
    if not problems:
        problems.append("unexpected output {!r}, wanted {!r}".format(text, EXPECTED))
    return problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stdout_file")
    args = parser.parse_args(argv[1:])

    with open(args.stdout_file) as f:
        problems = check(f.read())

    if problems:
        print("smoke run FAILED:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1

    print("smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
