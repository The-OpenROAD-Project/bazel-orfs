#!/usr/bin/env python3
"""Resolve SYNTH_KEEP_MODULES' design names to the modules of an RTLIL
checkpoint, for synth_partition.sh's top partition to blackbox.

yosys spells a module three ways and a design can contain all three:

  \\Foo                  unparameterized
  $paramod\\Foo\\W=1      parameterized, named form
  $paramod$<hash>\\Foo   parameterized, hashed form

plus \\Foo$Top.path.to.inst for an instance slang uniquified. The design's
name is the component after the first backslash in every form. A name
resolves to the first module whose design name it is, else to the first
uniquified instance of it, else to nothing. Same algorithm as
synth_canonicalize_module.tcl.

One pass over the checkpoint's modules however many names are asked
for: slang writes a module per instance, so a whole core's checkpoint
has hundreds of thousands of them, and the shell loop this replaces
forked per module per name and took hours on one.

  rtlil_names.py <checkpoint.rtlil> <name>...

prints each name's module, one per line in the order asked; a name that
resolves to nothing stops with every such name and the modules there are.
"""

import sys


def base_name(module):
    """The design's name for an RTLIL module name, or ''."""
    if module.startswith("\\"):
        return module[1:]
    parts = module.split("\\")
    return parts[1] if len(parts) >= 2 else ""


def checkpoint_modules(lines):
    """The modules an RTLIL text declares, in order."""
    out = []
    for line in lines:
        if line.startswith("module "):
            words = line.split()
            if len(words) >= 2:
                out.append(words[1])
    return out


def resolve(names, modules):
    """{name: module or None} for each name, by the rules above."""
    exact = {}
    uniquified = {}
    for module in modules:
        base = base_name(module)
        if not base:
            continue
        exact.setdefault(base, module)
        # every prefix that ends where a `$` starts: Foo$Top.a names Foo,
        # and a name with a `$` of its own still finds its instances
        i = base.find("$", 1)
        while i > 0:
            uniquified.setdefault(base[:i], module)
            i = base.find("$", i + 1)
    return {n: exact.get(n, uniquified.get(n)) for n in names}


def main(argv):
    if len(argv) < 2:
        sys.exit("usage: rtlil_names.py <checkpoint.rtlil> <name>...")
    with open(argv[1]) as f:
        modules = checkpoint_modules(f)
    found = resolve(argv[2:], modules)
    missing = [n for n in argv[2:] if found[n] is None]
    if missing:
        for n in missing:
            sys.stderr.write(
                "ERROR: SYNTH_KEEP_MODULES lists '%s' but it does not exist in the design.\n"
                % n
            )
        names = sorted({base_name(m) for m in modules} - {""})
        sys.stderr.write("Available modules: %s\n" % " ".join(names))
        sys.exit(1)
    for n in argv[2:]:
        print(found[n])


if __name__ == "__main__":
    main(sys.argv)
