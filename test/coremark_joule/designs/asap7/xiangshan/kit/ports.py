#!/usr/bin/env python3
"""A module's ports, from its header in a Verilog or SystemVerilog file.

  ports.py --module XSTile --out ports.json [--refuse <regex>] <file.sv>

Writes [{"name", "dir", "width"}] in header order. firtool declares
ports of one direction and width together (`input clock,` then `reset,`
on the next line): a line with a name alone continues the declaration
above it. Reads the file a line at a time and stops at the header's end,
so a 150 MB core costs seconds.

--refuse stops with the ports whose names match: test-mode pins (scan,
BIST, DFT controls) a place-and-route tool would have to be told to tie
off, kept out of the kit's top level. Python 3.6.
"""

import argparse
import json
import re

_DECL = re.compile(
    r"^\s*(input|output|inout)\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[(\d+):(\d+)\]\s*)?([A-Za-z_][A-Za-z_0-9$]*)\s*(?:[,)]|$)"
)
_MORE = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9$]*)\s*(?:[,)]|$)")


def ports(path, module):
    start = re.compile(r"^\s*module\s+%s\s*\(" % re.escape(module))
    out = []
    inside = False
    current = None
    with open(path) as f:
        for line in f:
            if not inside:
                inside = bool(start.match(line))
                if not inside:
                    continue
                line = line[line.index("(") + 1 :]
            code = line.split("//", 1)[0]
            m = _DECL.match(code)
            if m:
                width = abs(int(m.group(2)) - int(m.group(3))) + 1 if m.group(2) else 1
                current = (m.group(1), width)
                out.append({"name": m.group(4), "dir": current[0], "width": width})
            else:
                more = _MORE.match(code)
                if more and current:
                    out.append(
                        {"name": more.group(1), "dir": current[0], "width": current[1]}
                    )
            if re.search(r"\)\s*;", code):
                break
    if not inside:
        raise SystemExit("ports: no module %s in %s" % (module, path))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--module", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--refuse")
    p.add_argument("verilog")
    a = p.parse_args(argv)
    found = ports(a.verilog, a.module)
    if a.refuse:
        bad = [q["name"] for q in found if re.search(a.refuse, q["name"], re.I)]
        if bad:
            raise SystemExit(
                "ports: %s has test-mode ports to tie off: %s"
                % (a.module, ", ".join(bad))
            )
    with open(a.out, "w") as f:
        json.dump(found, f, indent=0)
        f.write("\n")


if __name__ == "__main__":
    main()
