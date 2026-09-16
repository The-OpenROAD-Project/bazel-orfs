#!/usr/bin/env python3
"""Drop SAIF entries whose net name a SAIF cannot carry.

OpenSTA's SAIF lexer defines an identifier as

    ID   ([A-Za-z_])([A-Za-z0-9_$\\[\\]\\\\.])*
    HCHAR "."|"/"

so `/` is the hierarchy separator and cannot appear inside a name. An ID
cannot begin with a backslash either, so escaping does not rescue such a
name -- there is no spelling of it the format accepts.

OpenROAD's hierarchical clock tree synthesis produces exactly that. It
names leaf clock nets after their sink's full path, and that path
contains odb's own `/` separator:

    clknet_1_0__leaf_swerv.ifu.bp/BTB_FLOPS[39].btb_bank1_way1...clkhdr.Q

It affects two constructs, not one. On VeeR EH1 at global route:

  5,284 of 1,002,201 NET entries       (0.53 %)
  3,738 of   211,278 INSTANCE headers  (1.77 %)

`read_saif` stops at the first of either with a parse error and
annotates nothing at all -- so without this the whole measurement is
lost, not degraded.

An INSTANCE cannot be dropped a line at a time: its block carries nested
nets and instances, so the parens are balanced rather than the lines
matched.

**A net dropped here is a net OpenSTA will estimate rather than
measure**, so the classification matters and is checked rather than
assumed:

  - A clock net or clock buffer is benign. §3.5 of the paper establishes that OpenSTA
    gives clock-network pins `2/period` from the SDC exactly, bypassing
    the estimator; being unannotated is the correct state for them, and
    the pin audit classifies them `clock_network`.
  - Anything else is not benign, and `--max-other` defaults to zero so a
    design that drops one has to say so and say why.

The root cause is a net name containing the hierarchy separator, which
is unrepresentable in more formats than this one. Carried here, not
upstreamed, per the moratorium in CLAUDE.md; it retires when a bump
brings a hierarchical CTS that does not compose such names.

Before reporting this upstream, read OpenROAD's own history first: it has
carried fixes in this area before -- name escaping, and the hierarchical
(-hier) flow -- so the fix may already exist. A bump is cheaper than a
report, and is the first thing to try when this workaround is next
touched.
"""

import argparse
import re
import sys

# `  (<name> (T0 ...` -- one net's durations. Anything else (INSTANCE
# headers, the file preamble, closing parens) passes through untouched.
_NET = re.compile(r"^(\s*)\((\S+)\s+\(T0\s")

# `  (INSTANCE <name>` -- a scope header. Its block must go with it.
_INSTANCE = re.compile(r"^\s*\(INSTANCE\s+(\S+)")

# Characters the lexer's ID rule accepts after the first.
_ID_BODY = re.compile(r"^[A-Za-z_][A-Za-z0-9_$\[\]\\.]*$")


def carryable(name):
    """Can a SAIF NET name hold this identifier at all?"""
    return bool(_ID_BODY.match(name))


def is_clock(name):
    """A clock net or buffer by OpenROAD's own naming, not by inference."""
    return name.startswith("clknet") or name.startswith("clkbuf")


def filter_saif(lines):
    """Return (kept_lines, dropped_clock, dropped_other).

    dropped_* are lists of names, so the caller can report and budget
    them separately. An uncarryable INSTANCE takes its whole block with
    it, which is why this tracks parenthesis depth rather than matching
    lines: the block holds nested nets and instances, and half of one
    left behind would be a worse file than the one we started with.
    """
    kept = []
    clock = []
    other = []
    depth = 0
    skip_to = None
    for line in lines:
        delta = line.count("(") - line.count(")")
        if skip_to is not None:
            depth += delta
            if depth <= skip_to:
                skip_to = None
            continue

        m = _INSTANCE.match(line)
        if m and not carryable(m.group(1)):
            (clock if is_clock(m.group(1)) else other).append(m.group(1))
            skip_to = depth
            depth += delta
            continue

        m = _NET.match(line)
        if m and not carryable(m.group(2)):
            (clock if is_clock(m.group(2)) else other).append(m.group(2))
            continue

        depth += delta
        kept.append(line)
    return kept, clock, other


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saif")
    parser.add_argument("out")
    parser.add_argument(
        "--max-other",
        type=int,
        default=0,
        help="how many non-clock nets this design is known to lose. Zero "
        "asserts that everything dropped is a clock net, which §3.5 "
        "establishes needs no annotation.",
    )
    args = parser.parse_args(argv[1:])

    with open(args.saif) as f:
        kept, clock, other = filter_saif(f.readlines())

    with open(args.out, "w") as f:
        f.writelines(kept)

    print(
        "filter_saif: dropped {} clock-network name(s) and {} other "
        "(budget {})".format(len(clock), len(other), args.max_other)
    )
    for name in other[:20]:
        print("filter_saif: not a clock net: {}".format(name), file=sys.stderr)
    if len(other) > args.max_other:
        print(
            "filter_saif: {} non-clock net(s) dropped, over the budget of "
            "{}. These will be estimated rather than measured, which is "
            "the thing the study exists to rule out.".format(
                len(other), args.max_other
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
