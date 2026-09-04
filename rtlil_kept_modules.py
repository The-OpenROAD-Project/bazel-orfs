#!/usr/bin/env python3
"""Extract kept module names from a post-keep_hierarchy RTLIL file.

Reads the RTLIL and outputs a JSON file with modules that have
the keep_hierarchy attribute set.

The top module is excluded when named with --top. yosys's keep_hierarchy
marks it like any other module, but for partition synthesis it is not a
kept *sub*module: it is synthesized by the dedicated top partition with
every kept module blackboxed. Listing it too made a regular partition
synthesize the top as well, and the top partition blackbox itself.

Usage: rtlil_kept_modules.py [--top DESIGN_NAME] <input.rtlil> <output.json>
"""

import argparse
import json
import re
import sys


def extract_kept_modules(rtlil_path, top=None):
    """Parse RTLIL and return list of module names with keep_hierarchy=1.

    `top`, if given, is dropped from the list; see the module docstring.
    """
    kept = []
    has_keep = False
    with open(rtlil_path) as f:
        for line in f:
            # Attributes appear before the module declaration
            if line.startswith("attribute \\keep_hierarchy 1"):
                has_keep = True
            elif line.startswith("module \\"):
                m = re.match(r"^module \\(\S+)", line)
                if m and has_keep and m.group(1) != top:
                    kept.append(m.group(1))
                has_keep = False
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--top", help="DESIGN_NAME; excluded from the list")
    parser.add_argument("rtlil")
    parser.add_argument("json")
    args = parser.parse_args()

    modules = extract_kept_modules(args.rtlil, top=args.top)
    with open(args.json, "w") as f:
        json.dump({"modules": modules}, f)

    print(f"Wrote {len(modules)} kept modules to {args.json}")


if __name__ == "__main__":
    main()
