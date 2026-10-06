#!/usr/bin/env python3
"""Compare two Verilog modules token for token, layout aside.

Usage: tokdiff.py A.sv B.sv [MODULE]: exit 0 when the token streams are
equal (comments kept, whitespace collapsed), else print the first
difference with context. With MODULE, only that module of each file.
"""
import re
import sys


def tokens(path, module=None):
    text = open(path).read()
    if module:
        m = re.search(r"^module\s+%s\b.*?^endmodule\b" % re.escape(module), text, re.S | re.M)
        if not m:
            sys.exit("%s: no module %s" % (path, module))
        text = m.group(0)
    return re.findall(r"//[^\n]*|\d+'[bhd][0-9a-fA-F_]+|[A-Za-z_$][A-Za-z0-9_$]*|\d+|\S", text)


def main():
    a = tokens(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else None)
    b = tokens(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            print("first difference at token %d: %r vs %r" % (i, x, y))
            print("A:", " ".join(a[max(0, i - 12): i + 8]))
            print("B:", " ".join(b[max(0, i - 12): i + 8]))
            return 1
    if len(a) != len(b):
        print("one is a prefix of the other: %d vs %d tokens" % (len(a), len(b)))
        return 1
    print("identical: %d tokens" % len(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
