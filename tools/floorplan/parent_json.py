#!/usr/bin/env python3
"""The parent's extract dump (extract_parent.tcl) as parent.json.

The crossings between the parent's blocks, its own logic (the glue) and
its ports, per pair of buses: how many bits of each end take part, how
the parent connects them (a wire, combinational cells, one register) and
the parent's own delay between the two boundaries. Schema:

  parent, identity {dump, tool}
  glue {std_um2}, modules {instance: {module, um2}}
  crossings [{a, a_inst, a_bus, b, b_inst, b_bus, via, a_bits, b_bits,
              bits, depth, glue_ps}]

a and b are block modules or the parent's own name (its ports, instance
"-"). bits is
the wider end. glue_ps: through wires and cells, the arrival at the
bus entering b less the arrival at the bus leaving a, each its worst
bit; through a register, the register's launch to b. Stdlib only.
"""

import argparse
import hashlib
import json
import re
import sys

TOOL = "parent_json 1"


def bus_of(name):
    return re.sub(r"\[[0-9]+\]$", "", name)


def build(lines, dump_hash):
    parent = None
    glue = 0.0
    modules = {}
    cross = {}
    for line in lines:
        f = line.rstrip("\n").split("\t")
        if not f[0]:
            continue
        if f[0] == "parent":
            parent = f[1]
        elif f[0] == "glue":
            glue = float(f[1])
        elif f[0] == "module":
            modules[f[1]] = {"module": f[2], "um2": float(f[3])}
        elif f[0] == "cross":
            a, ai, abit, b, bi, bbit, via, depth, t0, t1 = f[1:11]
            k = (a, ai, bus_of(abit), b, bi, bus_of(bbit), via)
            x = cross.setdefault(
                k, {"a_bits": set(), "b_bits": set(), "depth": 0, "t0": 0.0, "t1": 0.0}
            )
            x["a_bits"].add(abit)
            x["b_bits"].add(bbit)
            x["depth"] = max(x["depth"], int(depth))
            x["t0"] = max(x["t0"], float(t0))
            x["t1"] = max(x["t1"], float(t1))
    crossings = []
    for (a, ai, ab, b, bi, bb, via), x in sorted(cross.items()):
        na, nb = len(x["a_bits"]), len(x["b_bits"])
        glue_ps = 0.0 if via == "wire" else max(0.0, x["t1"] - x["t0"])
        crossings.append(
            {
                "a": a,
                "a_inst": ai,
                "a_bus": ab,
                "b": b,
                "b_inst": bi,
                "b_bus": bb,
                "via": via,
                "a_bits": na,
                "b_bits": nb,
                "bits": max(na, nb),
                "depth": x["depth"],
                "glue_ps": round(glue_ps, 1),
            }
        )
    return {
        "parent": parent,
        "identity": {"dump": "sha256:" + dump_hash, "tool": TOOL},
        "glue": {"std_um2": round(glue, 3)},
        "modules": modules,
        "crossings": crossings,
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump")
    ap.add_argument("out")
    args = ap.parse_args(argv)
    with open(args.dump, "rb") as f:
        raw = f.read()
    out = build(raw.decode().splitlines(), hashlib.sha256(raw).hexdigest())
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
