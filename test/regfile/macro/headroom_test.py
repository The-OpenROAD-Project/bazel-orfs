"""orfs_headroom on wide_top and its RegFile block: what the measurements
promise, not their values (.claude/skills/repair-headroom)."""

import json
import sys
import unittest


class HeadroomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(sys.argv[1]) as f:
            cls.r = json.load(f)
        with open(sys.argv[2]) as f:
            cls.nowire = json.load(f)
        cls.period = cls.r["period"]["period"]
        cls.eps = 1e-3 * cls.period

    def test_stitched_with_the_block(self):
        self.assertEqual(self.r["wires"], 1)
        self.assertEqual(self.r["blocks"], 1)
        self.assertGreater(self.r["period"]["endpoints"], 0)

    def test_every_what_if_is_undone(self):
        for name in ("skew", "vt", "vt_parent_only"):
            self.assertAlmostEqual(
                self.r[name]["restored"], self.period, delta=self.eps, msg=name
            )

    def test_no_floor_or_ceiling_above_the_period(self):
        self.assertLessEqual(self.r["skew"]["skew"], self.period + self.eps)
        self.assertLessEqual(self.r["vt"]["vt"], self.period + self.eps)
        self.assertLessEqual(self.nowire["period"]["period"], self.period + self.eps)
        if self.r["floor_cycles"]["loops"]:
            self.assertLessEqual(
                self.r["floor_cycles"]["floor"], self.period + self.eps
            )

    def test_skew_keeps_hold(self):
        hold = self.r["skew"]["hold_slack"]
        if hold != "":
            self.assertGreaterEqual(hold, -self.eps)

    def test_skew_reaches_into_the_block(self):
        # the worst paths end in the RegFile's storage flops: the stitched
        # view moves their clock arrivals and counts them as the block's,
        # what the parent's abstract alone could never do
        s = self.r["skew"]
        self.assertGreater(s["moved_block"], 0)
        self.assertLessEqual(s["moved_parent"] + s["moved_block"], s["flops"])
        self.assertEqual(self.r["vt_parent_only"]["swapped_block"], 0)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
