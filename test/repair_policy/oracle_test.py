#!/usr/bin/env python3
"""Tests for the oracle: best knob per design, QoR held."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "repair_timing_runtime"))
import oracle  # noqa: E402
import report_test  # noqa: E402


def rec(arm, setup_s, wns=-50.0, tns=-900.0):
    c = report_test.call(setup_s=setup_s, hold_s=0.0, wns_end=wns)
    r = report_test.record("aes", "cts", arm, 1, [c])
    r["substeps"]["4_1_cts"]["repair_rows"][0][-1]["en_tns"] = tns
    return r


class Oracle(unittest.TestCase):
    def test_fastest_arm_with_qor_held_wins(self):
        rows = oracle.oracle_rows([
            rec("base-prof", 100.0), rec("tns5-prof", 60.0, wns=-50.2),
            rec("nogasp-prof", 50.0, tns=-950.0),  # faster but TNS worse: excluded
            rec("noclone-prof", 40.0, wns=-53.0),  # faster but WNS 3 ps worse: excluded
        ])
        self.assertEqual(rows[0]["oracle"], "tns5-prof")
        self.assertAlmostEqual(rows[0]["saving_pct"], 40.0)

    def test_no_safe_knob_means_base_is_the_oracle(self):
        rows = oracle.oracle_rows([rec("base-prof", 100.0), rec("nogasp-prof", 50.0, tns=-950.0)])
        self.assertEqual(rows[0]["oracle"], "base-prof")
        self.assertEqual(rows[0]["saving_pct"], 0.0)

    def test_table_renders(self):
        text = oracle.oracle_table(oracle.oracle_rows([rec("base-prof", 100.0), rec("tns5-prof", 60.0)]))
        self.assertIn("| aes | cts | 100.0 | tns5-prof | 60.0 | 40% |", text)


if __name__ == "__main__":
    unittest.main()
