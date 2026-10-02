"""What the four arms of the multiplier example must show.

The design's period is the larger of the parent's and the macro's.
Retiming alone fixes the macro and hurts the parent (ABC moves the
output flops into the multiply, it never sees the wire after the port);
peeling alone cannot help while the unretimed multiply sets the period;
together they beat both.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, "mul_report_%s.json" % name)) as f:
        return json.load(f)


ARMS = {
    "base": ("mul_top", "mul"),
    "retime": ("mul_top_retime", "mul_retime"),
    "peel": ("mul_top_peel", "mul_core"),
    "retime_peel": ("mul_top_retime_peel", "mul_core_retime"),
}


class MulTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = {a: load(p) for a, (p, _) in ARMS.items()}
        cls.macro = {a: load(m) for a, (_, m) in ARMS.items()}
        cls.period = {
            a: max(cls.parent[a]["period_ps"], cls.macro[a]["period_ps"]) for a in ARMS
        }

    def test_peeled_flops_in_the_parent(self):
        # 4 x 64 product bits and the one valid_out the parent reads
        for arm in ("peel", "retime_peel"):
            self.assertEqual(self.parent[arm]["peeled_flops"], 257)
        for arm in ("base", "retime"):
            self.assertEqual(self.parent[arm]["peeled_flops"], 0)

    def test_retime_alone_moves_the_problem_to_the_parent(self):
        self.assertLess(
            self.macro["retime"]["period_ps"], self.macro["base"]["period_ps"]
        )
        self.assertGreater(
            self.parent["retime"]["period_ps"], self.parent["base"]["period_ps"]
        )

    def test_retime_and_peel_beat_both(self):
        self.assertLess(
            self.period["retime_peel"], 0.9 * self.period["retime"], self.period
        )
        self.assertLess(self.period["retime"], self.period["base"], self.period)


if __name__ == "__main__":
    sys.exit(unittest.main())
