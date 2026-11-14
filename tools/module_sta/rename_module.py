"""Rename the module a synthesised netlist defines, so a new version of a
module can be read beside the old one and swapped in (iterate.tcl).

    rename_module.py <netlist.v> <new name> <out.v>

The netlist is a partition's: one module definition. Its name, escaped or
not, is replaced in the definition only; nothing in it instantiates
itself.
"""

import re
import sys

MODULE = re.compile(r"^module\s+(\\\S+\s|[A-Za-z_][\w$]*)", re.M)


def rename(text, new):
    found = MODULE.findall(text)
    if len(found) != 1:
        raise ValueError("expected one module definition, found %d" % len(found))
    return MODULE.sub("module %s " % new, text, count=1)


def main(argv):
    if len(argv) != 4:
        sys.exit(__doc__)
    with open(argv[1]) as f:
        text = f.read()
    with open(argv[3], "w") as f:
        f.write(rename(text, argv[2]))


if __name__ == "__main__":
    main(sys.argv)
