"""The pathology stand-in, from its records: B1 (the Frontend block's
settings), S0 (the kept modules stated with SYNTH_HIERARCHICAL=0) and P3
(S0 with repair_design repeated, ORFS patch 0088)."""

import json
import sys
import unittest

B1, S0, P3 = (json.load(open(p)) for p in sys.argv[1:4])


class PathologyTest(unittest.TestCase):
    def test_kept_modules_are_the_stated_ones(self):
        for r in (B1, S0):
            self.assertEqual(sorted(r["kept"]), sorted(r["kept_expected"]))

    def test_stating_the_list_changes_nothing_else(self):
        self.assertEqual(S0["period_ps"], B1["period_ps"])

    def test_one_repair_design_call_leaves_violations(self):
        # The pathology: with the Frontend block's settings as they were.
        self.assertGreater(B1["slew_viol"], 100)

    def test_repeated_repair_design_removes_what_one_call_leaves(self):
        # Repeated, repair_design converges at the resize step (0 on the
        # stand-in's 3_4 ODB); the place stage is read after detailed
        # placement, whose moves bring back a few (49 of 1,117), which the
        # global-route stage's repair_design sees.
        self.assertLessEqual(P3["slew_viol"], 0.05 * B1["slew_viol"])

    def test_repeated_repair_design_period_no_worse(self):
        self.assertLessEqual(P3["period_ps"], B1["period_ps"] * 1.02)

    def test_placement_legal(self):
        for r in (B1, S0, P3):
            self.assertTrue(r["placement_ok"])


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
