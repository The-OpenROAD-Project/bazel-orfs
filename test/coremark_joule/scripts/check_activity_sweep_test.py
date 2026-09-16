#!/usr/bin/env python3
"""Unit tests for the activity sweep bound.

The sweep's whole value is that it can fail. Two ways of passing it
without having measured anything are what these tests rule out: a SAIF
arm that is flat because the design is flat rather than because it was
annotated, and a control arm that moved because the sweep was compared
against the wrong baseline.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_activity_sweep import (  # noqa: E402
    evaluate,
    group_totals,
    parse_point,
    spread,
)


def power_json(total, internal=None, switching=None, leakage=None):
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(
        {
            "Total": {
                "internal": internal if internal is not None else total * 0.5,
                "switching": switching if switching is not None else total * 0.4,
                "leakage": leakage if leakage is not None else total * 0.1,
                "total": total,
            }
        },
        handle,
    )
    handle.close()
    return handle.name


def points(vectorless, saif):
    out = []
    for activity, total in vectorless:
        out.append(("vectorless", activity, power_json(total)))
    for activity, total in saif:
        out.append(("saif", activity, power_json(total)))
    return out


class ParsePointTest(unittest.TestCase):
    def test_a_point_names_its_arm_and_its_activity(self):
        self.assertEqual(("saif", 0.1, "/x/y.json"), parse_point("saif:0.1:/x/y.json"))

    def test_a_malformed_point_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_point("saif:0.1")


class GroupTotalsTest(unittest.TestCase):
    def test_the_four_power_groups_are_read(self):
        groups = group_totals(power_json(1.0, 0.5, 0.4, 0.1))
        self.assertEqual(1.0, groups["total"])
        self.assertEqual(0.1, groups["leakage"])

    def test_a_report_without_a_total_group_is_an_error(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"Combinational": {"total": 1.0}}, handle)
        handle.close()
        with self.assertRaises(ValueError):
            group_totals(handle.name)


class SpreadTest(unittest.TestCase):
    def test_a_flat_arm_has_no_spread(self):
        self.assertEqual(0.0, spread([2.0, 2.0, 2.0]))

    def test_spread_is_peak_to_peak_over_the_mean(self):
        self.assertAlmostEqual(1.0, spread([1.0, 2.0, 3.0]))


class EvaluateTest(unittest.TestCase):
    FLAT = [(0.0, 2.0), (0.1, 2.0), (1.0, 2.0), (2.0, 2.0)]
    MOVES = [(0.0, 1.0), (0.1, 1.5), (1.0, 3.0), (2.0, 5.0)]

    def test_a_flat_saif_arm_with_a_moving_control_passes(self):
        result = evaluate(points(self.MOVES, self.FLAT), 0.005, 0.05)
        self.assertEqual("pass", result["verdict"])

    def test_a_saif_arm_that_moves_fails(self):
        """Pins OpenSTA estimated are contributing to the reported power."""
        result = evaluate(points(self.MOVES, self.MOVES), 0.005, 0.05)
        self.assertEqual("fail", result["verdict"])

    def test_a_flat_control_arm_fails_even_though_the_saif_arm_is_flat(self):
        """Without a working knob a flat SAIF arm proves nothing."""
        result = evaluate(points(self.FLAT, self.FLAT), 0.005, 0.05)
        self.assertEqual("fail", result["verdict"])
        self.assertTrue(any("positive control" not in f for f in result["failures"]))

    def test_a_missing_saif_arm_fails(self):
        result = evaluate(points(self.MOVES, []), 0.005, 0.05)
        self.assertEqual("fail", result["verdict"])

    def test_a_missing_control_arm_fails(self):
        result = evaluate(points([], self.FLAT), 0.005, 0.05)
        self.assertEqual("fail", result["verdict"])

    def test_the_control_ratio_says_how_much_measuring_bought(self):
        drifts = [(0.0, 2.0), (0.1, 2.0), (1.0, 2.0), (2.0, 2.002)]
        result = evaluate(points(self.MOVES, drifts), 0.005, 0.05)
        self.assertEqual("pass", result["verdict"])
        self.assertGreater(result["control_ratio"], 100.0)

    def test_the_points_are_ordered_by_activity_in_the_output(self):
        result = evaluate(points(self.MOVES, self.FLAT), 0.005, 0.05)
        activities = [p["activity"] for p in result["arms"]["saif"]["points"]]
        self.assertEqual(sorted(activities), activities)

    def test_the_result_is_json_serialisable(self):
        result = evaluate(points(self.MOVES, self.FLAT), 0.005, 0.05)
        json.loads(json.dumps(result))


if __name__ == "__main__":
    unittest.main()
