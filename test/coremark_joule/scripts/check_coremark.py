#!/usr/bin/env python3
"""Decide whether a CoreMark run computed the right answer.

The gate is the three CRCs CoreMark prints, not its own error count and
not the exit status.

CoreMark's total_errors is unusable here on purpose: the port stubs the
timer to a constant so the two iteration counts produce byte-identical
output, which means time_in_secs() is always below ten and core_main.c
unconditionally prints "Must execute for at least 10 secs for a valid
result!" and increments the count. A run can be perfectly correct and
still report errors.

The CRCs are the real check, and they are independent of the iteration
count by construction: core_main.c captures crclist on the first
iteration (`if (i == 0)`), and core_list_join.c captures crcmatrix and
crcstate on their first call (`if (res->crcmatrix == 0)`). So one
expected triple validates both the two- and three-iteration runs, and a
core that miscomputes on any iteration still fails.

The stack high-water mark is checked here too, and for a related
reason. §4.2 moved the program out of a 128 KiB simulation array
and into an 8 KiB data memory that is hardened with the core, which
makes the headroom above .bss small enough to be worth measuring rather
than assuming. crt0.S paints the region above _end before anything uses
the stack and portable_fini reports how much of the paint is gone, so
every run carries its own evidence that the memory it was measured in
was big enough. A run whose mark reaches the budget below fails here
rather than corrupting .bss somewhere subtler.

Usage: check_coremark.py <stdout-file> [--profile 2k-performance]
"""

import argparse
import re
import sys

# Keyed by CoreMark's own seedcrc, which identifies the run profile, so a
# changed TOTAL_DATA_SIZE cannot silently be checked against the wrong
# expectations. Values are core_main.c's known-CRC tables.
_PROFILES = {
    # TOTAL_DATA_SIZE=2000, seeds 0/0/0x66 -> 666 bytes per algorithm.
    "0xe9f5": {
        "name": "2K performance",
        "crclist": "0xe714",
        "crcmatrix": "0x1fd7",
        "crcstate": "0x8e3a",
    },
}

_FIELD = re.compile(r"^\[\d+\](crc\w+)\s*:\s*(0x[0-9a-f]+)\s*$")
_SEEDCRC = re.compile(r"^seedcrc\s*:\s*(0x[0-9a-f]+)\s*$")
_STACK = re.compile(r"^stack-used\s+(\d+)\s+of\s+(\d+)\s*$")

# How much of the headroom above .bss the stack may use before the run
# is called unsafe. Not 100%: by the time the paint is gone all the way
# down to _end the stack has already written past it, so the failure
# would be a corrupted .bss rather than a reported overflow. Half leaves
# room for a compiler that inlines differently without turning a healthy
# margin into a warning nobody reads. The measured mark across every
# core and march in the study is 388 B of 4,604, which is 8%.
_STACK_BUDGET = 0.5


def parse(text):
    """Return (seedcrc, {field: value}) from a CoreMark report."""
    seedcrc = None
    fields = {}
    for line in text.splitlines():
        line = line.strip()
        m = _SEEDCRC.match(line)
        if m:
            seedcrc = m.group(1)
            continue
        m = _FIELD.match(line)
        if m:
            fields[m.group(1)] = m.group(2)
    return seedcrc, fields


def check_stack(text):
    """Return problems with the reported stack high-water mark."""
    m = None
    for line in text.splitlines():
        found = _STACK.match(line.strip())
        if found:
            m = found
    if m is None:
        return [
            "no stack-used line in the output: portable_fini did not report "
            "the stack high-water mark, so nothing shows the data memory was "
            "big enough for this run"
        ]

    used, headroom = int(m.group(1)), int(m.group(2))
    if headroom <= 0:
        return ["stack-used reports a headroom of {}; .bss already fills the "
                "data memory".format(headroom)]
    if used > headroom * _STACK_BUDGET:
        return [
            "stack high-water mark {} B of {} B of headroom ({:.0%}), over the "
            "{:.0%} budget: the data memory in cmj_progmem.sv is too small for "
            "this image".format(used, headroom, used / headroom, _STACK_BUDGET)
        ]
    return []


def check(text):
    """Return a list of human-readable problems; empty means the run is good."""
    seedcrc, fields = parse(text)

    if seedcrc is None:
        return [
            "no seedcrc line in the output: the run did not reach CoreMark's "
            "report, so it crashed, trapped or was cut off by the cycle budget"
        ]

    profile = _PROFILES.get(seedcrc)
    if profile is None:
        return [
            "seedcrc {} is not a profile this study knows; expected one of "
            "{}".format(seedcrc, ", ".join(sorted(_PROFILES)))
        ]

    problems = []
    problems.extend(check_stack(text))
    for key in ("crclist", "crcmatrix", "crcstate"):
        want = profile[key]
        got = fields.get(key)
        if got is None:
            problems.append("{} missing from the report".format(key))
        elif got != want:
            problems.append(
                "{}: got {}, expected {} for the {} profile".format(
                    key, got, want, profile["name"]
                )
            )
    return problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stdout_file")
    args = parser.parse_args(argv[1:])

    with open(args.stdout_file) as f:
        text = f.read()

    problems = check(text)
    if problems:
        print("CoreMark run FAILED:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1

    print("CoreMark CRCs OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
