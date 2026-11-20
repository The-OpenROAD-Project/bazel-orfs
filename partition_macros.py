#!/usr/bin/env python3
"""Stage the macros a partition's slices reach, and nothing else.

A slice (verilog_slice.py) holds each macro it reaches as a stub under
the macro's own name. This copies the liberty view of every macro whose
stub is in one of the partition's slices into OUT_DIR and writes
OUT_DIR/macros.mk, which adds the copies to ADDITIONAL_LIBS and the
macros' own paths to ADDITIONAL_LEFS and ADDITIONAL_GDS, and
OUT_DIR/libs.txt, the copies alone, which the slice's canonicalize
takes for ADDITIONAL_LIBS. The
partition reads OUT_DIR in place of the design's whole macro set, so
its key moves only when a macro its slices reach does.

MACROS_JSON maps each macro's module name to
{"lib": path, "lefs": [path...], "gds": [path...]}.

Usage: partition_macros.py --macros-json MACROS_JSON --out-dir OUT_DIR
           SLICE...
"""

import argparse
import json
import os
import re
import shutil

_MODULE = re.compile(
    r"^(?:\(\*.*\*\)\s*)?(?:macro)?module\s+(?:(?:static|automatic)\s+)?"
    r"(\\\S+|[A-Za-z_][A-Za-z0-9_$]*)"
)


def slice_modules(text):
    """The names of the modules a slice defines, stubs included."""
    names = set()
    for line in text.splitlines():
        match = _MODULE.match(line)
        if match:
            names.add(match.group(1).lstrip("\\"))
    return names


def reached(macros, slices):
    """The macros whose module one of the slices defines, sorted."""
    defined = set()
    for text in slices:
        defined |= slice_modules(text)
    return sorted(name for name in macros if name in defined)


def write_macros(macros, names, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    libs, lefs, gds = [], [], []
    for name in names:
        macro = macros[name]
        if macro.get("lib"):
            own = os.path.join(out_dir, name)
            os.makedirs(own, exist_ok=True)
            copy = os.path.join(own, os.path.basename(macro["lib"]))
            shutil.copyfile(macro["lib"], copy)
            libs.append(copy)
        lefs.extend(macro.get("lefs", []))
        gds.extend(macro.get("gds", []))
    with open(os.path.join(out_dir, "libs.txt"), "w") as out:
        out.write(" ".join(sorted(libs)))
    with open(os.path.join(out_dir, "macros.mk"), "w") as out:
        for var, paths in [
            ("ADDITIONAL_GDS", gds),
            ("ADDITIONAL_LEFS", lefs),
            ("ADDITIONAL_LIBS", libs),
        ]:
            if paths:
                out.write("export {} += {}\n".format(var, " ".join(sorted(set(paths)))))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--macros-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("slices", nargs="+")
    args = parser.parse_args(argv)
    with open(args.macros_json) as f:
        macros = json.load(f)
    texts = []
    for path in args.slices:
        with open(path) as f:
            texts.append(f.read())
    write_macros(macros, reached(macros, texts), args.out_dir)


if __name__ == "__main__":
    main()
