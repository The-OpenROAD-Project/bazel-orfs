#!/usr/bin/env python3
"""Unit tests for the example-SDC check."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_examples_sdc as c  # noqa: E402

GOOD = """
create_clock -period 1000 -name clk [get_ports clk]
set non_clk_inputs [all_inputs -no_clocks]
set_max_delay -ignore_clock_latency 800 -from $non_clk_inputs -to [all_registers]
set_max_delay -ignore_clock_latency 800 -from [all_registers] -to [all_outputs]
set_max_delay 600 -from $non_clk_inputs -to [all_outputs]
group_path -name in2reg -from $non_clk_inputs -to [all_registers]
group_path -name reg2out -from [all_registers] -to [all_outputs]
group_path -name reg2reg -from [all_registers] -to [all_registers]
group_path -name in2out -from $non_clk_inputs -to [all_outputs]
"""


class CheckTest(unittest.TestCase):
    def test_good_sdc_passes(self):
        self.assertEqual([], c.check(GOOD))

    def test_set_input_delay_fails(self):
        bad = GOOD + "set_input_delay 200 -clock clk [all_inputs -no_clocks]\n"
        problems = c.check(bad)
        self.assertEqual(1, len(problems))
        self.assertIn("set_input_delay", problems[0])

    def test_set_output_delay_fails(self):
        bad = GOOD + "set_output_delay 200 -clock clk [all_outputs]\n"
        self.assertTrue(any("set_output_delay" in p for p in c.check(bad)))

    def test_the_word_in_a_comment_is_not_a_use(self):
        """The file explains why it does not use set_input_delay.

        A check that matched the raw text would fail on its own
        explanation, and a test that fails on the thing it documents
        gets deleted rather than fixed.
        """
        commented = GOOD + "# Two reasons not to reach for set_input_delay here.\n"
        self.assertEqual([], c.check(commented))

    def test_a_missing_path_group_fails(self):
        without = "\n".join(
            l for l in GOOD.splitlines() if "-name reg2reg" not in l
        )
        problems = c.check(without)
        self.assertEqual(1, len(problems))
        self.assertIn("reg2reg", problems[0])

    def test_no_budget_at_all_fails(self):
        """Deleting the delays without replacing them is not the fix."""
        bare = "create_clock -period 1000 -name clk [get_ports clk]\n"
        problems = c.check(bare)
        self.assertTrue(any("no set_max_delay" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
