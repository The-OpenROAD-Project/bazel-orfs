"""The kept-module tree of a partitioned synthesis, from its partition netlists.

    tree.py <top> <out.json> <partition.v>...

Each partition netlist defines its kept module(s) and the modules flattened
into them, and instantiates the kept modules below as references only. The
tree is {"top": top, "modules": {module: {"file": partition, "children":
[kept module, ...]}}}: a module's children are the kept modules its
partition instantiates, each listed once. A module defined by two partitions
is an error, as is a top that no partition defines.
"""

import json
import re
import sys

_MODULE = re.compile(r"^\s*module\s+(\\\S+|[A-Za-z_][\w$]*)")
_INSTANCE = re.compile(r"^\s*(\\\S+|[A-Za-z_][\w$]*)\s+(\\\S+|[A-Za-z_][\w$]*)\s*\(")
_KEYWORDS = {"module", "input", "output", "inout", "wire", "reg", "assign", "endmodule"}


def name(token):
    """A Verilog identifier with an escaped identifier's backslash dropped."""
    return token[1:] if token.startswith("\\") else token


def scan(path):
    """{module defined in path: {instantiated module names}}."""
    defined = {}
    current = None
    with open(path) as f:
        for line in f:
            m = _MODULE.match(line)
            if m:
                current = name(m.group(1))
                defined[current] = set()
                continue
            if current is None:
                continue
            m = _INSTANCE.match(line)
            if m and m.group(1) not in _KEYWORDS:
                defined[current].add(name(m.group(1)))
    return defined


def tree(top, paths):
    defined = {}
    owner = {}
    for path in paths:
        for module, refs in scan(path).items():
            if module in owner:
                raise ValueError(
                    "%s is defined by both %s and %s" % (module, owner[module], path)
                )
            owner[module] = path
            defined[module] = refs
    if top not in owner:
        raise ValueError("no partition defines the top, %s" % top)
    kept = {}
    for path in paths:
        local = {m for m, p in owner.items() if p == path}
        # a partition's kept modules are those no module of its own file
        # instantiates; the others were flattened into them
        inner = set().union(*(defined[m] for m in local)) & local
        for module in sorted(local - inner):
            kept[module] = path

    def reach(module, seen):
        out = set()
        for ref in defined.get(module, ()):
            if ref in kept and owner[ref] != owner[module]:
                out.add(ref)
            elif ref in defined and owner[ref] == owner[module] and ref not in seen:
                seen.add(ref)
                out |= reach(ref, seen)
        return out

    return {
        "top": top,
        "modules": {
            m: {"file": kept[m], "children": sorted(reach(m, {m}))}
            for m in sorted(kept)
        },
    }


def main(argv):
    top, out, paths = argv[0], argv[1], argv[2:]
    with open(out, "w") as f:
        json.dump(tree(top, paths), f, indent=1, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
