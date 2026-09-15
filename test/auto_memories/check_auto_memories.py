#!/usr/bin/env python3
"""Assert what AUTO_MEMORIES did to //test/auto_memories:am_top.

Three things, each of which was a bug that completed successfully and
produced a plausible wrong answer rather than an error:

1. The module-boundary memory was converted and the inline array was
   not. Converting an inline array generates a macro nothing can
   instantiate -- blackboxing needs a module of that name and there is
   none -- so the design synthesizes to flip-flops while memories.json
   reports the memory as converted. The inventory and the netlist
   disagree and the area looks reasonable.

2. The generated macro is not a sliver. FakeRAM folds an array by
   column_mux_factor; with the factor pinned at 1 a 2048-deep memory
   comes out 4.18 x 663.60 um, an aspect ratio of 159:1 that no
   floorplan can place. The bound here is 8, which is the worst ratio
   among the fakeram7_* views ASAP7 ships.

3. The views the generator wrote actually exist where later stages glob
   for them. That one is mostly proved by the flow reaching floorplan
   at all, but checking the files are here makes a missing one say so.

Usage: check_auto_memories.py --out <report> <path> [<path> ...]

The paths are whatever the synth target declares; this picks out
memories.json and the generated LEFs by name rather than searching, so
it never walks a tree it was not handed.
"""

import argparse
import json
import os
import re
import sys

# Above the worst aspect ratio among ASAP7's own fakeram7_* views --
# fakeram7_2048x39, 20.33 x 166.60 um, which is 8.2:1 -- with room to
# spare, because the bound must never fail the reference it is
# calibrated against. The failure it exists to catch is not a tall
# memory but an unfolded one, and that is 159:1 for a 2048-deep array
# and 635:1 for an 8192-deep one. Anywhere in between separates them.
MAX_ASPECT = 12.0

_SIZE_RE = re.compile(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)")


def collect(paths):
    """Return (memories_json_path, {macro_name: lef_path}).

    A directory among the paths is the generated views tree, which holds
    a handful of files; listing it is bounded and is not a search.
    """
    memories_json = None
    lefs = {}
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith(".lef"):
                    lefs[name[: -len(".lef")]] = os.path.join(p, name)
            continue
        if os.path.basename(p) == "memories.json":
            memories_json = p
    return memories_json, lefs


def check_inventory(doc):
    """The convertible memory converted, the inline array did not."""
    problems = []
    by_name = {m["name"]: m for m in doc.get("memories", [])}

    ram = by_name.get("am_ram_2048x32")
    if ram is None:
        problems.append(
            "am_ram_2048x32 is not in memories.json: the .memories override "
            "was not read, so nothing was converted"
        )
    elif not ram.get("idiomatic"):
        problems.append(
            "am_ram_2048x32 was not converted: {}".format(
                ram.get("reason", "no reason given")
            )
        )

    # The inline array is reported under whatever name yosys inferred it
    # as; what matters is that *something* was refused and said why, and
    # that it is not the module-boundary memory.
    refused = [
        m for m in doc.get("memories", []) if not m.get("idiomatic")
    ]
    if not refused:
        problems.append(
            "no memory was refused: am_regs holds an inline array, which is "
            "the design asking for flip-flops, and converting it produces a "
            "macro nothing can instantiate"
        )
    for m in refused:
        if not m.get("reason"):
            problems.append(
                "{} was refused without a reason; the reason is what tells a "
                "user how to get the other answer".format(m["name"])
            )
    return problems


def check_geometry(lefs):
    """No generated macro is a sliver."""
    problems = []
    if not lefs:
        problems.append("no generated .lef among the declared outputs")
    for name, path in sorted(lefs.items()):
        with open(path) as f:
            m = _SIZE_RE.search(f.read())
        if m is None:
            problems.append("{}: no SIZE in the LEF".format(name))
            continue
        w, h = float(m.group(1)), float(m.group(2))
        aspect = max(w, h) / min(w, h)
        if aspect > MAX_ASPECT:
            problems.append(
                "{}: {:.2f} x {:.2f} um is an aspect ratio of {:.0f}:1, past "
                "the {:.0f}:1 bound -- the array is not being folded".format(
                    name, w, h, aspect, MAX_ASPECT
                )
            )
    return problems


def check(paths):
    memories_json, lefs = collect(paths)
    if memories_json is None:
        return ["no memories.json among the declared outputs"]
    with open(memories_json) as f:
        doc = json.load(f)
    return check_inventory(doc) + check_geometry(lefs)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv[1:])

    problems = check(args.paths)
    with open(args.out, "w") as f:
        if problems:
            f.write("FAILED\n")
            for p in problems:
                f.write("  " + p + "\n")
        else:
            f.write("AUTO_MEMORIES inventory and geometry OK\n")

    if problems:
        print("AUTO_MEMORIES check FAILED:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print("AUTO_MEMORIES inventory and geometry OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
