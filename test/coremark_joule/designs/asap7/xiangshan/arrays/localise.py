"""Where an extraction differs from its block: check.py's miter, one per
group of outputs of the cut designs (a register's D, enable or reset, or
a port, with the entry numbers in its name folded into #), so a
NOT equivalent names the arrays and ports to look at.

    bazelisk run //test/coremark_joule/designs/asap7/xiangshan/arrays:localise -- \\
        <yosys> <proc.json> <extracted.json> <module>

Paths absolute: bazel run starts in the runfiles. Scratch files go
beside the extracted JSON.
"""

import collections
import json
import os
import re
import subprocess
import sys

import check


def main(argv):
    yosys, orig, extracted, module = argv[1:5]
    work = os.path.dirname(os.path.abspath(extracted))
    flat = os.path.join(work, "localise_flat.json")
    rc, log = check.run(
        yosys,
        f"read_json {extracted}; hierarchy -top {module}; "
        f"setattr -mod -unset keep_hierarchy {module}Entry; flatten; write_json {flat}",
    )
    if rc:
        sys.exit(log[-3000:])
    renames = json.load(open(extracted + ".renames"))
    gold = check.cut(json.load(open(orig))["modules"][module], {}, "gold")
    gate = check.cut(json.load(open(flat))["modules"][module], renames, "gate")
    groups = collections.defaultdict(list)
    for p, v in gold["ports"].items():
        if v["direction"] == "output":
            groups[re.sub(r"_\d+(?=_|$)", "_#", p)].append(p)
    abc = os.path.join(os.path.dirname(yosys), "yosys-abc")
    both = os.path.join(work, "localise_both.json")
    aig = os.path.join(work, "localise.aig")
    differing = []
    for group, ports in sorted(groups.items()):

        def only(mod):
            return dict(
                mod,
                ports={
                    k: v
                    for k, v in mod["ports"].items()
                    if v["direction"] == "input" or k in ports
                },
            )

        json.dump(
            {"modules": {"gold": only(gold), "gate": only(gate)}}, open(both, "w")
        )
        rc, log = check.run(
            yosys,
            f"read_json {both}; miter -equiv -flatten gold gate miter; hierarchy -top miter; "
            f"opt -fast; techmap; opt -fast; setundef -zero; aigmap; write_aiger -zinit {aig}",
        )
        if rc:
            sys.exit(f"localise: the miter of {group} failed\n" + log[-2000:])
        out = subprocess.run(
            [abc, "-c", f"read_aiger {aig}; strash; iprove"],
            capture_output=True,
            text=True,
        ).stdout
        if "UNSATISFIABLE" not in out and "Networks are equivalent" not in out:
            differing.append(group)
            print(
                f"localise: DIFFERS {group} ({len(ports)} ports, e.g. {ports[0]})",
                flush=True,
            )
    print(f"localise: {len(groups)} groups, {len(differing)} differing")
    sys.exit(1 if differing else 0)


if __name__ == "__main__":
    main(sys.argv)
