"""What an edit did to reg2reg timing: two ends files compared.

    ab.py <a.ends> <b.ends> <ab.txt> [--top N]

Writes the worst slack, total negative slack, violating endpoints and
endpoint count of A and B and their change, and the endpoints that
started or stopped violating, the worst first, at most N of each (20).
"""

import argparse
import os
import sys

# ends.py sits beside this script; the python wrapper runs a script with
# runpy, which does not put its directory on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ends import read_ends, summary  # noqa: E402


def fmt(x):
    if x is None:
        return "-"
    if isinstance(x, int):
        return str(x)
    return "%.1f" % x


def delta(a, b):
    if a is None or b is None:
        return "-"
    d = b - a
    return ("%+d" % d) if isinstance(d, int) else ("%+.1f" % d)


def table(rows):
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(
            c.ljust(w) if i == 0 else c.rjust(w)
            for i, (c, w) in enumerate(zip(r, widths))
        )
        for r in rows
    )


def report(ea, eb, top=20):
    a, b = summary(ea), summary(eb)
    rows = [["", "A", "B", "B - A"]]
    for key, name in [
        ("wns", "worst slack"),
        ("tns", "total negative slack"),
        ("violating", "violating endpoints"),
        ("endpoints", "endpoints"),
    ]:
        rows.append([name, fmt(a[key]), fmt(b[key]), delta(a[key], b[key])])
    out = [table(rows)]
    new = sorted((s, p) for p, s in eb.items() if s < 0 and ea.get(p, 0) >= 0)
    gone = sorted((s, p) for p, s in ea.items() if s < 0 and eb.get(p, 0) >= 0)
    for title, items in [
        ("Started violating in B", new),
        ("Stopped violating in B", gone),
    ]:
        out.append("")
        out.append("%s: %d" % (title, len(items)))
        for _, p in items[:top]:
            out.append("  %s  %s -> %s" % (p, fmt(ea.get(p)), fmt(eb.get(p))))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("a_ends")
    ap.add_argument("b_ends")
    ap.add_argument("out")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)
    with open(args.out, "w") as f:
        f.write(report(read_ends(args.a_ends), read_ends(args.b_ends), args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
