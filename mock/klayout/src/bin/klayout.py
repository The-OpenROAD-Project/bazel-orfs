#!/usr/bin/env python3
"""Mock klayout binary for testing the ORFS Bazel rules.

Creates dummy GDS files by parsing -rd key=value arguments to find
output file paths.
"""

import os
import sys

# Minimal GDS II file: HEADER(v7) + BGNLIB + ENDLIB
GDS_HEADER = (
    b"\x00\x06\x00\x02\x00\x07"  # HEADER record, version 7
    b"\x00\x1c\x01\x02"  # BGNLIB record
    b"\x00\x01\x00\x01\x00\x01\x00\x01\x00\x00"  # mod time
    b"\x00\x01\x00\x01\x00\x01\x00\x01\x00\x00"  # access time
    b"\x00\x04\x04\x00"  # ENDLIB record
)


def parse_rd_args(argv):
    """Parse -rd key=value arguments, return dict of key->value."""
    rd_args = {}
    i = 0
    while i < len(argv):
        if argv[i] == "-rd" and i + 1 < len(argv):
            i += 1
            if "=" in argv[i]:
                key, value = argv[i].split("=", 1)
                rd_args[key] = value
        i += 1
    return rd_args


def create_gds(output_path):
    """Create a minimal dummy GDS II file at output_path."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(GDS_HEADER)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "-v":
        print("KLayout 0.0.0 (mock)")
        return 0

    rd_args = parse_rd_args(argv)

    for key in ("out", "out_file"):
        if key in rd_args:
            create_gds(rd_args[key])

    print("mock klayout (CI stub)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
