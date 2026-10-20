"""Prefix a block netlist's modules with the block's name, its top excepted.

    sta_prefix.py <block> <in.v> <out.v>

Every block is written hierarchically (sta_part.tcl) so its names agree
with its SPEF, and the same RTL module synthesised in two blocks is two
different netlists under one name. Read together, they collide; with each
block's modules renamed <block>__<module>, they do not. The block's own
module keeps its name: the parent instantiates it by that name.

It also gives back the local names of nets repair made inside a submodule:
the hierarchical writer declares such a net in the module at instance
path P as the escaped name `\\P/x`, while the SPEF names it P/x, which
OpenSTA reads as net x in the instance at P. Inside each module, a local
name that begins with the module's own instance path loses that prefix,
so the netlist and the SPEF agree.
"""

import re
import sys

MODULE = re.compile(r"^module\s+(\\\S+|[A-Za-z_][\w$]*)")
INSTANCE = re.compile(r"^(\s*)(\\\S+|[A-Za-z_][\w$]*)(\s+)")


def rename(name, block):
    if name.startswith("\\"):
        return "\\%s__%s" % (block, name[1:])
    return "%s__%s" % (block, name)


ESCAPED = re.compile(r"\\(\S+) ")
SIMPLE = re.compile(r"^[A-Za-z_][\w$]*$")


def paths(lines, top):
    """Each module's instance path below `top`: one per module, as the
    hierarchical writer uniquifies a module per instance."""
    body, cur = {}, None
    for line in lines:
        m = MODULE.match(line)
        if m:
            cur = m.group(1)
            body[cur] = []
        elif cur is not None:
            m = INSTANCE.match(line)
            if m and m.group(2) != "module":
                inst = re.match(
                    r"\s*(?:\\\S+|[A-Za-z_][\w$]*)\s+(\\\S+|[A-Za-z_][\w$]*)", line
                )
                if inst:
                    body[cur].append((m.group(2), inst.group(1)))
    found = {top: ""}
    todo = [top]
    while todo:
        mod = todo.pop()
        for sub, inst in body.get(mod, []):
            if sub in body and sub not in found:
                name = inst[1:] if inst.startswith("\\") else inst
                found[sub] = found[mod] + name + "/"
                todo.append(sub)
    return found


def localize(lines, top):
    """Strip a module's own instance path from the escaped local names in it."""
    where = paths(lines, top)
    out, prefix = [], ""
    for line in lines:
        m = MODULE.match(line)
        if m:
            prefix = where.get(m.group(1), "")
        if prefix and "\\" + prefix in line:

            def local(e):
                name = e.group(1)
                if not name.startswith(prefix):
                    return e.group(0)
                rest = name[len(prefix) :]
                return (rest if SIMPLE.match(rest) else "\\" + rest) + " "

            line = ESCAPED.sub(local, line)
        out.append(line)
    return out


def main(block, src, dst):
    with open(src) as f:
        lines = localize(f.readlines(), block)
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
