"""One LEF and one Liberty file of the memories inside the macros a top
level dissolves (parent_macro.bzl): the masters its dissolve copies
cells of, and the timing every stage after reads.

Each flow's memories (ORFS AUTO_MEMORIES, results/memories) are one
.lef and one .lib per memory, file names known only once its RTL is
scanned; the top level takes files whose names Bazel knows. Every
memory's templates and types are named after it, so the merged library
is the first file's header and every memory's groups. A memory two
macros share is one memory, kept once. Two files whose headers differ
stop here: a merged header would describe neither.

    merge_memories.py <out.lef> <out.lib> <file>...
"""

import os
import re
import sys

_LIB_NAME = re.compile(r"^library\s*\(\s*[^)]*\)\s*\{")
_DATE = re.compile(r"^\s*date\s*:.*;$")


def top_statements(body):
    """A Liberty group's body split into its top-level statements."""
    out = []
    depth = 0
    start = 0
    i = 0
    while i < len(body):
        c = body[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                out.append(body[start : i + 1].strip())
                start = i + 1
        elif c == ";" and depth == 0:
            out.append(body[start : i + 1].strip())
            start = i + 1
        elif c == "/" and body[i : i + 2] == "/*":
            i = body.index("*/", i) + 1
        i += 1
    tail = body[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def split_lib(path):
    """(header statements, group statements) of one memory's library."""
    with open(path) as f:
        text = f.read()
    m = _LIB_NAME.search(text)
    if not m:
        sys.exit("merge_memories: %s has no library group" % path)
    body = text[m.end() : text.rindex("}")]
    header, groups = [], []
    for s in top_statements(body):
        head = s.split("(", 1)[0].strip()
        if head in ("lu_table_template", "power_lut_template", "type", "cell"):
            groups.append(s)
        elif not _DATE.match(s):
            header.append(s)
    return header, groups


def split_lef(path):
    """(header lines, MACRO blocks) of one memory's LEF."""
    with open(path) as f:
        lines = f.read().splitlines()
    header, macros, block = [], [], None
    for line in lines:
        if block is None and line.startswith("MACRO "):
            block = [line]
        elif block is not None:
            block.append(line)
            if line.startswith("END ") and line.split()[1] == block[0].split()[1]:
                macros.append("\n".join(block))
                block = None
        elif line.strip() == "END LIBRARY":
            pass
        elif not macros and not line.startswith("#"):
            header.append(line)
    return header, macros


def main(out_lef, out_lib, files):
    views = {}
    for f in files:
        name = os.path.basename(f)
        if name.endswith("_pre_layout.lib") or not name.endswith((".lef", ".lib")):
            continue
        views.setdefault(name, f)
    lefs = sorted(n for n in views if n.endswith(".lef"))
    libs = sorted(n for n in views if n.endswith(".lib"))
    if [n[:-4] for n in lefs] != [n[:-4] for n in libs]:
        sys.exit("merge_memories: the LEFs and the libraries name different memories")

    lef_header, lef_macros = None, []
    for n in lefs:
        header, macros = split_lef(views[n])
        if lef_header is None:
            lef_header = header
        elif header != lef_header:
            sys.exit("merge_memories: %s's LEF header differs from the first's" % n)
        lef_macros += macros
    with open(out_lef, "w") as f:
        f.write("\n".join((lef_header or []) + lef_macros + ["END LIBRARY", ""]))

    lib_header, lib_groups = None, []
    for n in libs:
        header, groups = split_lib(views[n])
        if lib_header is None:
            lib_header = header
        elif header != lib_header:
            sys.exit("merge_memories: %s's library header differs from the first's" % n)
        lib_groups += groups
    with open(out_lib, "w") as f:
        f.write("library(carve_memories) {\n")
        for s in (lib_header or []) + lib_groups:
            f.write("    " + s + "\n")
        f.write("}\n")
    print("merge_memories: %d memories" % len(lefs))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
