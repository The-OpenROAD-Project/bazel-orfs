"""What peeling Src's output flops must do to the miniature's parent.

The base parent hardens Src whole, so it has no flops of its own; the
peeled one places Src's 32 output flops itself, away from Src along the
crossing to Dst, and its period is shorter for it.
"""

import json
import os
import sys
import unittest


def load(tag):
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "peel_report_%s.json" % tag
    )
    with open(path) as f:
        return json.load(f)


class PeelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load("base")
        cls.peel = load("peel")

    def test_flops_move_to_the_parent(self):
        self.assertEqual(self.base["parent_flops"], 0)
        self.assertEqual(self.peel["parent_flops"], 32)

    def test_flops_leave_src(self):
        # 0 is Src's centre, 1 Dst's; Src's edge is about 0.1 on the diagonal
        self.assertGreater(self.peel["flop_t_mean"], 0.1, self.peel)

    def test_period_shorter(self):
        self.assertLess(
            self.peel["period_ps"],
            0.95 * self.base["period_ps"],
            (self.base, self.peel),
        )


if __name__ == "__main__":
    sys.exit(unittest.main())
