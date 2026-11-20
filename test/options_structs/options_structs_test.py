"""The dicts of //test/options_structs:OPTIONS reach the commands they are for.

Reads the stage logs: log_cmd prints each command as it ran, -options
dicts and all. OpenROAD applies -options left to right, so the design's
dict is the last one on the line.
"""

import argparse
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


class OptionsStructsTest(unittest.TestCase):
    def test_global_route_takes_the_designs_dict_after_the_flows(self):
        (first,) = [
            c for c in commands(ARGS.grt, "global_route") if "_incremental" not in c
        ]
        self.assertIn("congestion_iterations 30", first)
        self.assertTrue(first.endswith('-options "congestion_iterations 20"'), first)

    def test_repair_design_takes_its_grt_scope_in_grt_alone(self):
        (grt,) = commands(ARGS.grt, "repair_design")
        self.assertTrue(
            grt.endswith('-options "slew_margin 5" -options "slew_margin 10"'), grt
        )
        (place,) = commands(ARGS.place, "repair_design")
        self.assertTrue(place.endswith('-options "slew_margin 5"'), place)

    def test_global_placement_takes_the_embedded_routers_option(self):
        calls = commands(ARGS.place, "global_placement")
        self.assertTrue(calls)
        for call in calls:
            if "-incremental" in call:
                continue
            self.assertIn(
                '-options "routability.global_route.congestion_iterations 5"', call
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--place", nargs="+", required=True)
    parser.add_argument("--grt", nargs="+", required=True)
    ARGS, rest = parser.parse_known_args()
    unittest.main(argv=[__file__] + rest)
