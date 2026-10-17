"""Prefix a block netlist's modules with the block's name, its top excepted.

    sta_prefix.py <block> <in.v> <out.v>

Every block is written hierarchically (sta_part.tcl) so its names agree
with its SPEF, and the same RTL module synthesised in two blocks is two
different netlists under one name. Read together, they collide; with each
block's modules renamed <block>__<module>, they do not. The block's own
module keeps its name: the parent instantiates it by that name.
"""

import re
import sys

MODULE = re.compile(r"^module\s+(\\\S+|[A-Za-z_][\w$]*)")
INSTANCE = re.compile(r"^(\s*)(\\\S+|[A-Za-z_][\w$]*)(\s+)")


def rename(name, block):
    if name.startswith("\\"):
        return "\\%s__%s" % (block, name[1:])
    return "%s__%s" % (block, name)


def main(block, src, dst):
    with open(src) as f:
        lines = f.readlines()
    defined = {m.group(1) for m in map(MODULE.match, lines) if m}
    defined.discard(block)
    with open(dst, "w") as out:
        for line in lines:
            m = MODULE.match(line)
            if m and m.group(1) in defined:
                line = "module " + rename(m.group(1), block) + line[m.end() :]
            else:
                m = INSTANCE.match(line)
                if m and m.group(2) in defined:
                    line = (
                        m.group(1)
                        + rename(m.group(2), block)
                        + m.group(3)
                        + line[m.end() :]
                    )
            out.write(line)


if __name__ == "__main__":
    main(*sys.argv[1:])
