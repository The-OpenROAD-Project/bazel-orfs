"""Tests for sdc_period.py — the one reader of the design's period."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sdc_period  # noqa: E402

SDC = """\
# A starting period, not a result.
set clk_name clk
set clk_port_name clk
set clk_period 1591

set in2reg_max [expr { $clk_period * 0.8 }]
"""


class TestPeriod(unittest.TestCase):
    def test_reads_it(self):
        self.assertEqual(sdc_period.period_ps(SDC), 1591)

    def test_frequency_follows(self):
        self.assertAlmostEqual(sdc_period.frequency_mhz(SDC), 628.5355122564425)

    def test_missing_is_an_error_not_a_default(self):
        """A default would be a period nothing in the design agrees with."""
        with self.assertRaises(sdc_period.NoPeriod):
            sdc_period.period_ps("set clk_name clk\n")

    def test_does_not_match_the_expression_that_uses_it(self):
        """`$clk_period * 0.8` is a use, not a definition."""
        self.assertEqual(sdc_period.period_ps(SDC), 1591)


class TestRewrite(unittest.TestCase):
    def test_round_trip(self):
        out = sdc_period.set_period_ps(SDC, 438)
        self.assertEqual(sdc_period.period_ps(out), 438)

    def test_only_the_period_line_changes(self):
        out = sdc_period.set_period_ps(SDC, 438)
        self.assertEqual(
            [l for l in SDC.splitlines() if "set clk_period" not in l],
            [l for l in out.splitlines() if "set clk_period" not in l],
        )

    def test_refuses_a_nonpositive_period(self):
        with self.assertRaises(sdc_period.NoPeriod):
            sdc_period.set_period_ps(SDC, 0)

    def test_refuses_when_there_is_nothing_to_rewrite(self):
        with self.assertRaises(sdc_period.NoPeriod):
            sdc_period.set_period_ps("set clk_name clk\n", 438)


if __name__ == "__main__":
    unittest.main()
