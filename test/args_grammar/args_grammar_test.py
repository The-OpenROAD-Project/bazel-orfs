"""The edits of //test/args_grammar:ARGS reach the commands they are for.

Reads the stage logs: log_cmd prints each command as it ran, and the
grammar names the call, the edit and the variable before it.
"""

import argparse
import re
import unittest

ARGS = None


def commands(paths, command):
    lines = []
    for path in paths:
        if not path.endswith(".log"):
            continue
        with open(path) as f:
            lines += [l.rstrip("\n") for l in f if l.startswith(command + " ")]
    return lines


class ArgsGrammarTest(unittest.TestCase):
    def test_grt_repair_timing_takes_its_scoped_margin(self):
        calls = commands(ARGS.grt, "repair_timing")
        self.assertTrue(calls)
        for call in calls:
            self.assertRegex(call, r"-setup_margin 0\.1\b")

    def test_global_route_takes_the_edit_over_the_flows_default(self):
        (first,) = [
            c for c in commands(ARGS.grt, "global_route") if "_incremental" not in c
        ]
        self.assertEqual(["20"], re.findall(r"-congestion_iterations (\S+)", first))

    def test_floorplan_runs_no_repair_timing(self):
        self.assertEqual([], commands(ARGS.floorplan, "repair_timing"))
        self.assertTrue(commands(ARGS.floorplan, "initialize_floorplan"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--floorplan", nargs="+", required=True)
    parser.add_argument("--grt", nargs="+", required=True)
    ARGS, rest = parser.parse_known_args()
    unittest.main(argv=[__file__] + rest)
