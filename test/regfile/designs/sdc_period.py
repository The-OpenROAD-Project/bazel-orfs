"""A design's SDC with its clock period changed.

    sdc_period.py --period 850 in.sdc out.sdc

Rewrites the one `set clk_period <n>` line, or where there is none the one
literal `-period <n>` of a create_clock, to the given period in ps. An SDC
with neither, or with more than one, stops: the period it would set is
not known.
"""

import argparse
import re
import sys

SET = re.compile(r"^(\s*set\s+clk_period\s+)([0-9.]+)(\s*(?:#.*)?)$", re.M)
LITERAL = re.compile(r"^(\s*create_clock\b.*-period\s+)([0-9.]+)(\b.*)$", re.M)


def with_period(text, period):
    for pattern in (SET, LITERAL):
        hits = pattern.findall(text)
        if len(hits) == 1:
            return pattern.sub(lambda m: m.group(1) + period + m.group(3), text)
        if len(hits) > 1:
            raise ValueError("%d clock periods, not one" % len(hits))
    raise ValueError("no `set clk_period` and no create_clock -period")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--period", required=True)
    p.add_argument("src")
    p.add_argument("dst")
    a = p.parse_args(argv)
    with open(a.src) as f:
        text = f.read()
    try:
        text = with_period(text, a.period)
    except ValueError as e:
        sys.exit("sdc_period: %s: %s" % (a.src, e))
    with open(a.dst, "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
