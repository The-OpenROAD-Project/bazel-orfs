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

a and b are block modules (by instance) or the parent's own name: its
ports (instance "-") or its registers (instance "reg", no bus). bits is
the wider end. glue_ps: through cells, the arrival at the bus entering b
less the arrival at the bus leaving a, each its worst bit; from a
register, the register's launch to b. Stdlib only.
"""

import argparse
import hashlib
import json
import sys

TOOL = "parent_json 1"


def build(lines, dump_hash):
    parent = None
    glue = 0.0
    modules = {}
    crossings = []
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
            a, ai, ab, na, b, bi, bb, nb, via, depth, ps = f[1:12]
            crossings.append(
                {
                    "a": a,
                    "a_inst": ai,
                    "a_bus": ab,
                    "b": b,
                    "b_inst": bi,
                    "b_bus": bb,
                    "via": via,
                    "a_bits": int(na),
                    "b_bits": int(nb),
                    "bits": max(int(na), int(nb)),
                    "depth": int(depth),
                    "glue_ps": float(ps),
                }
            )
    crossings.sort(
        key=lambda x: (
            x["a"],
            x["a_inst"],
            x["a_bus"],
            x["b"],
            x["b_inst"],
            x["b_bus"],
            x["via"],
        )
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
