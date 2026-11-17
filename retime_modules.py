#!/usr/bin/env python3
"""Check SYNTH_RETIME_MODULES against the modules a parallel synthesis keeps.

Retiming runs in each partition after flattening, on the one module the
partition synthesises: the top or a kept module. ORFS's synth.tcl skips an
entry that matches no module in a partition, because it may name another
partition's module, so this check over all partitions at once is what stops
an entry that matches no partition's module. An entry is a glob, as
synth.tcl's `lsearch -glob`.

The spec is JSON: {"groups": [{"patterns": [...], "names": [...],
"name_files": [...], "kept_json": [...]}]}. A group is one
SYNTH_RETIME_MODULES value and the modules of the partitions it reaches:
named directly, by a partition's canonical-name sidecar, or by
kept_modules.json. The stamp is written when every entry matches.

Usage: retime_modules.py SPEC STAMP
"""

import fnmatch
import json
import sys


def unmatched(patterns, modules):
    """The patterns that match none of the modules."""
    return [p for p in patterns if not any(fnmatch.fnmatchcase(m, p) for m in modules)]


def group_modules(group):
    """A group's module names, read from its sidecars and kept lists."""
    modules = list(group.get("names", []))
    for path in group.get("name_files", []):
        with open(path) as f:
            modules.append(f.read().strip().removeprefix("\\"))
    for path in group.get("kept_json", []):
        with open(path) as f:
            modules.extend(json.load(f)["modules"])
    return modules


def check(spec):
    """Error messages, one for each group with an entry that matches nothing."""
    errors = []
    for group in spec["groups"]:
        modules = group_modules(group)
        missing = unmatched(group["patterns"], modules)
        if missing:
            errors.append(
                "SYNTH_RETIME_MODULES: {} matches none of the {} modules its "
                "partitions synthesise; retiming runs on the top and the kept "
                "modules only, and the slang frontend names a kept module "
                "Name$<path>, matched by Name*".format(", ".join(missing), len(modules))
            )
    return errors


def main():
    spec_path, stamp = sys.argv[1:]
    with open(spec_path) as f:
        errors = check(json.load(f))
    if errors:
        sys.exit("\n".join(errors))
    with open(stamp, "w") as f:
        f.write("ok\n")


if __name__ == "__main__":
    main()
