#!/usr/bin/env python3
"""Reverse the bits on one input port of one instance in a yosys JSON.

A negative control's break: every register stays read, so the proof sees
the same registers on both sides and must find the difference in the
logic, not stop at a boundary that no longer matches.
"""

import argparse
import json
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", required=True)
    parser.add_argument("--top", required=True)
    parser.add_argument("--port", required=True, help="INSTANCE.PORT, two bits or more")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.json) as f:
        design = json.load(f)
    instance, port = args.port.split(".", 1)
    cell = design["modules"][args.top]["cells"].get(instance)
    if (
        cell is None
        or port not in cell["connections"]
        or cell["port_directions"][port] != "input"
    ):
        print("break_port: %s has no input %s" % (instance, port), file=sys.stderr)
        return 1
    bits = cell["connections"][port]
    if len(bits) < 2:
        print(
            "break_port: %s.%s has one bit; reversing it breaks nothing"
            % (instance, port),
            file=sys.stderr,
        )
        return 1
    cell["connections"][port] = bits[::-1]
    with open(args.out, "w") as f:
        json.dump(design, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
