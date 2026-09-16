#!/usr/bin/env python3
"""Unit tests for the SDC constraint check."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_sdc import check, strip_comments  # noqa: E402

GOOD = """\
set clk_period 1000
set in2reg_max  [expr { $clk_period * 0.8 }]
set reg2out_max [expr { $clk_period * 0.8 }]
set in2out_max  [expr { $clk_period * 0.6 }]
source $::env(PLATFORM_DIR)/constraints.sdc
"""


class StripCommentsTest(unittest.TestCase):
    def test_a_leading_hash_is_a_comment(self):
        self.assertEqual("", strip_comments("# set_input_delay 200"))

    def test_indentation_does_not_hide_a_comment(self):
        self.assertEqual("", strip_comments("    # set_input_delay 200"))

    def test_a_real_command_survives(self):
        self.assertIn("set_input_delay", strip_comments("set_input_delay 200"))


class CheckTest(unittest.TestCase):
    def test_a_budgeted_sdc_passes(self):
        self.assertEqual([], check("x.sdc", GOOD))

    def test_set_input_delay_fails(self):
        problems = check("x.sdc", GOOD + "set_input_delay 200 -clock clk [all_inputs]\n")
        self.assertEqual(1, len(problems))
        self.assertIn("set_input_delay", problems[0])

    def test_set_output_delay_fails(self):
        problems = check("x.sdc", GOOD + "set_output_delay 200 -clock clk [all_outputs]\n")
        self.assertEqual(1, len(problems))

    def test_naming_it_in_a_comment_does_not_fail(self):
        """The design SDCs explain why it is absent; saying so is not using it."""
        self.assertEqual(
            [],
            check("x.sdc", "# set_input_delay is deliberately not used\n" + GOOD),
        )

    def test_a_missing_budget_fails(self):
        """Silence is the dangerous case: the platform then applies 80 ps."""
        problems = check("x.sdc", "set clk_period 1000\n")
        self.assertEqual(3, len(problems))

    def test_each_missing_budget_is_named(self):
        without = GOOD.replace("set in2out_max  [expr { $clk_period * 0.6 }]\n", "")
        problems = check("x.sdc", without)
        self.assertEqual(1, len(problems))
        self.assertIn("in2out_max", problems[0])


if __name__ == "__main__":
    unittest.main()
