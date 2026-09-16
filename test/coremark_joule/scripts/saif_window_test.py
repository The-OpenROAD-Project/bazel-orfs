#!/usr/bin/env python3
"""Unit tests for the SAIF window derivation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import saif_window  # noqa: E402
from saif_window import window  # noqa: E402


class SaifWindowTest(unittest.TestCase):
    def test_window_is_exactly_one_iteration_ending_at_the_report(self):
        # picorv32 rv32im, measured.
        self.assertEqual((3693242, 5501131), window(3723728, 5531617, 5501131))

    def test_window_length_equals_the_cycle_delta(self):
        start, end = window(100, 150, 140)
        self.assertEqual(50, end - start)

    def test_equal_runs_are_rejected(self):
        """A zero delta means the two runs are not what they claim to be."""
        with self.assertRaises(ValueError):
            window(100, 100, 90)

    def test_missing_first_output_is_rejected(self):
        """Without it the end of the benchmark loop is unknown."""
        with self.assertRaises(ValueError):
            window(100, 150, None)

    def test_loop_shorter_than_an_iteration_is_rejected(self):
        with self.assertRaises(ValueError):
            window(100, 150, 20)


class ClkPeriodFromSdcTest(unittest.TestCase):
    def test_reads_the_set_line(self):
        sdc = "# comment\nset clk_name clk\nset clk_period 1282\nset x [expr { $clk_period * 0.8 }]\n"
        self.assertEqual(saif_window.read_clk_period(sdc), 1282)

    def test_ignores_expr_uses_and_requires_a_literal(self):
        with self.assertRaises(ValueError):
            saif_window.read_clk_period("set clk_period [expr { 1000 + 200 }]\n")


if __name__ == "__main__":
    unittest.main()
