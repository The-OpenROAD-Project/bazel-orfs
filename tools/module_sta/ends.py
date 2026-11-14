"""Endpoint slack files: read, summarise, compare.

    ends.py compare <ends> <reference.ends> [--tolerance PS] [--diff FILE]
                    [--expect-differences]

An ends file has one "<pin> <slack>" line per reg2reg endpoint, slack in
picoseconds. compare checks every endpoint of the first file against the
reference (a flat timing of the whole design): it fails when one differs
by more than the tolerance (0.001 ps, the precision of the files) or is
missing from the reference, or, with --expect-differences, when none
does: the negative control, that the comparison can fail.
"""

import argparse
import sys


def read_ends(path):
    """{pin: slack}; a hierarchical name's escapes dropped, so the
    timer's escaped and unescaped spellings of one pin agree."""
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            pin, slack = line.rsplit(" ", 1)
            out[pin.replace("\\", "")] = float(slack)
    return out


def summary(slacks):
    values = list(slacks.values())
    return {
        "endpoints": len(values),
        "wns": min(values) if values else None,
        "tns": sum(s for s in values if s < 0),
        "violating": sum(1 for s in values if s < 0),
    }


def compare(slacks, reference, tolerance):
    """The lines that differ: a slack off by more than the tolerance, or
    an endpoint the reference does not have."""
    lines = []
    for pin in sorted(slacks):
        a, b = slacks[pin], reference.get(pin)
        if b is None:
            lines.append("%s %s missing from the reference" % (pin, a))
        elif abs(a - b) > tolerance:
            lines.append("%s %s reference %s delta %.6f" % (pin, a, b, a - b))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("ends")
    c.add_argument("reference")
    c.add_argument("--tolerance", type=float, default=0.001)
    c.add_argument("--diff")
    c.add_argument("--expect-differences", action="store_true")
    args = ap.parse_args(argv)
    slacks = read_ends(args.ends)
    diff = compare(slacks, read_ends(args.reference), args.tolerance)
    if args.diff:
        with open(args.diff, "w") as f:
            f.write("".join(l + "\n" for l in diff))
    print("%d endpoints compared, %d differ" % (len(slacks), len(diff)))
    for l in diff[:10]:
        print("  " + l)
    if not slacks:
        print("FAIL: no endpoint to compare")
        return 1
    if args.expect_differences:
        return 0 if diff else 1
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
