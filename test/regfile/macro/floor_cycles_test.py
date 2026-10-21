"""The one-flop-loop floor reported at the end of the RegFile's global route
(tools/headroom/report_floor_cycles.tcl): what it promises, not its value."""

import json
import re
import sys
import unittest


def find(paths, name):
    for p in paths:
        if p.endswith(name):
            return p
    raise AssertionError("%s not among %s" % (name, paths))


class FloorCyclesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = sys.argv[1:]
        with open(find(paths, "5_1_grt.log")) as f:
            cls.log = f.read()
        with open(find(paths, "5_1_grt.json")) as f:
            cls.metrics = json.load(f)

    def test_the_log_names_the_register(self):
        m = re.search(
            r"One-flop-loop floor: ([0-9.]+) at (\S+) "
            r"\((\d+) stages, (\d+) buffers; (\d+) loops",
            self.log,
        )
        self.assertIsNotNone(m, "no floor line in the grt log")
        self.assertGreater(int(m.group(5)), 0)
        self.assertTrue(m.group(2))

    def test_the_floor_is_not_above_the_minimum_period(self):
        floor = self.metrics["globalroute__timing__floor_cycles"]
        self.assertGreater(floor, 0)
        fmax = [
            v
            for k, v in self.metrics.items()
            if k.startswith("globalroute__timing__fmax") and v
        ]
        self.assertTrue(fmax, "no fmax metric at grt")
        # the metric is in the liberty's time unit, ps on asap7
        min_period_ps = 1e12 / max(fmax)
        self.assertLessEqual(floor, min_period_ps * 1.001)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
