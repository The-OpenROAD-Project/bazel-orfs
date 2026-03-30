#!/usr/bin/env python3
"""Extract kept module names from a post-keep_hierarchy RTLIL file.

Reads the RTLIL and outputs a JSON file with modules that have
the keep_hierarchy attribute set.

Usage: rtlil_kept_modules.py <input.rtlil> <output.json>
"""
import json
import re
import sys


def extract_kept_modules(rtlil_path):
    """Parse RTLIL and return list of module names with keep_hierarchy=1."""
    kept = []
    has_keep = False
    with open(rtlil_path) as f:
        for line in f:
            # Attributes appear before the module declaration
            if line.startswith("attribute \\keep_hierarchy 1"):
                has_keep = True
            elif line.startswith("module \\"):
                m = re.match(r"^module \\(\S+)", line)
                if m and has_keep:
                    kept.append(m.group(1))
                has_keep = False
    return kept


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.rtlil> <output.json>", file=sys.stderr)
        sys.exit(1)

    modules = extract_kept_modules(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump({"modules": modules}, f)

    print(f"Wrote {len(modules)} kept modules to {sys.argv[2]}")


if __name__ == "__main__":
    main()
