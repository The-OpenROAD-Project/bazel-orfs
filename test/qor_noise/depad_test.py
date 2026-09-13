#!/usr/bin/env python3

"""Tests for depad.py.

The interesting cases are the ones that would silently produce confident
nonsense: a metric whose rule is computed from a different metric, a
timing rule for a design that met its constraint, and the round trip that
the whole study rests on.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import depad


class RoundTrip(unittest.TestCase):
    def test_padding_inverts_genrulefile(self):
        # genRuleFile.py: rule = measured * (1 + padding/100), rounded.
        for measured in (1610.0, 162505.0, 7.0, 1234567.0):
            rule = int(round(measured * 1.15))
            back = depad.depad("finish__design__instance__area", rule)
            self.assertAlmostEqual(back, measured, delta=max(1.0, measured * 1e-6))

    def test_antenna_uses_its_own_thirty_percent(self):
        rule = int(round(40 * 1.30))
        self.assertAlmostEqual(
            depad.depad("detailedroute__antenna__violating__nets", rule), 40, delta=1.0
        )

    def test_direct_metrics_carry_no_margin(self):
        self.assertEqual(depad.depad("detailedroute__route__drc_errors", 0), 0.0)
        self.assertEqual(depad.depad("detailedplace__design__violations", 3), 3.0)


class Timing(unittest.TestCase):
    PERIOD = 4.5

    def rule_for(self, measured, padding=5):
        negative = min(measured, 0.0)
        return negative - max(negative * padding / 100.0, self.PERIOD * padding / 100.0)

    def test_failing_slack_is_recoverable(self):
        measured = -0.603
        rule = self.rule_for(measured)
        back = depad.depad("finish__timing__setup__ws", rule, period=self.PERIOD)
        self.assertAlmostEqual(back, measured, places=6)

    def test_met_constraint_carries_no_measurement(self):
        # Every passing run produces the identical rule, so nothing about
        # the slack survives. This is the censoring the study reports.
        for measured in (0.0, 0.001, 1.0, 1e6):
            rule = self.rule_for(measured)
            self.assertIsNone(
                depad.depad("finish__timing__setup__ws", rule, period=self.PERIOD),
                f"slack {measured} should be censored",
            )

    def test_passing_runs_are_indistinguishable(self):
        self.assertEqual(self.rule_for(0.0), self.rule_for(999.0))

    def test_period_is_required(self):
        with self.assertRaises(depad.NotDepaddable):
            depad.depad("finish__timing__setup__ws", -0.3)


class Refusals(unittest.TestCase):
    def test_metric_computed_from_another_metric_is_refused(self):
        # This rule is 10% of the placeopt stdcell count; it says nothing
        # about the buffer count it is named after.
        for metric in depad.NOT_ABOUT_ITSELF:
            with self.assertRaises(depad.NotDepaddable):
                depad.depad(metric, 1234)

    def test_unknown_metric_is_refused_not_guessed(self):
        with self.assertRaises(depad.NotDepaddable):
            depad.depad("some__future__metric", 1.0)

    def test_high_resolution_metrics_are_all_padding_and_rounded(self):
        for metric in depad.HIGH_RESOLUTION:
            mode, _pad, round_value = depad.PADDING[metric]
            self.assertEqual(mode, "padding", metric)
            self.assertTrue(round_value, metric)
            self.assertEqual(depad.resolution(metric), 0.0)

    def test_three_significant_digit_metrics_declare_their_resolution(self):
        self.assertEqual(
            depad.resolution("synth__design__instance__area__stdcell"), 0.01
        )


class Direction(unittest.TestCase):
    def test_timing_metrics_are_not_lower_is_better(self):
        for metric in depad.PADDING:
            if "timing" in metric:
                self.assertNotIn(metric, depad.LOWER_IS_BETTER, metric)

    def test_area_and_wirelength_are_lower_is_better(self):
        for metric in depad.HIGH_RESOLUTION:
            self.assertIn(metric, depad.LOWER_IS_BETTER, metric)


if __name__ == "__main__":
    unittest.main()
