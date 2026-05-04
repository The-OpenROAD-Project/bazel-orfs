"""Asserts JSON files produced by orfs_arguments(...) have expected keys.

Used by `counter_computed_arguments_test` to validate the shipped
compute_floorplan_shape.tcl and compute_slack_margin.tcl scripts.
"""

import json
import sys


def fail(msg):
    print("FAIL:", msg, file=sys.stderr)
    sys.exit(1)


def main(argv):
    if len(argv) != 3:
        fail(
            "expected 2 args (shape_json, slack_json), got {}".format(len(argv) - 1)
        )

    shape_path, slack_path = argv[1], argv[2]

    try:
        with open(shape_path) as f:
            shape = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        fail("could not read/parse {}: {}".format(shape_path, e))

    try:
        with open(slack_path) as f:
            slack = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        fail("could not read/parse {}: {}".format(slack_path, e))

    print("floorplan_shape JSON:", shape)
    print("slack_margin   JSON:", slack)

    for key in ("CORE_UTILIZATION", "CORE_MARGIN"):
        if key not in shape:
            fail("{} missing from {}".format(key, shape_path))

    for key in ("SETUP_SLACK_MARGIN", "HOLD_SLACK_MARGIN"):
        if key not in slack:
            fail("{} missing from {}".format(key, slack_path))

    try:
        util = float(shape["CORE_UTILIZATION"])
    except ValueError:
        fail("CORE_UTILIZATION not numeric: {!r}".format(shape["CORE_UTILIZATION"]))

    if not (5.0 <= util <= 50.0):
        fail("CORE_UTILIZATION={} outside documented [5, 50] clamp".format(util))

    print("OK: computed-arguments JSON files have all expected keys.")


if __name__ == "__main__":
    main(sys.argv)
