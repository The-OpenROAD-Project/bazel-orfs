#!/usr/bin/env python3
"""Unit tests for the SAIF window derivation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


if __name__ == "__main__":
    unittest.main()
