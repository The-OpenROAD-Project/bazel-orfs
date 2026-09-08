"""Tests for the write-up generator.

The generator's job is to be honest about what was measured, so what is
pinned here is mostly that: a missing input has to produce a visible
"not measured" section rather than a silently shorter document, and the
one derived number in the ladder has to be right.
"""

import unittest

import report


class TableTest(unittest.TestCase):
    def test_no_rows_is_empty_not_a_header(self):
        # A header with no rows reads as "we measured this and found
        # nothing", which is the opposite of the truth.
        self.assertEqual(report.table(["a", "b"], []), "")

    def test_rows_render(self):
        got = report.table(["a", "b"], [[1, 2]])
        self.assertEqual(
            got.splitlines(),
            ["| a | b |", "| --- | --- |", "| 1 | 2 |"],
        )


class MissingInputTest(unittest.TestCase):
    """Absent campaigns must announce themselves."""

    def test_size_section_says_not_measured(self):
        self.assertIn("Not yet measured", report.section_size({}))

    def test_ladder_section_says_not_measured(self):
        self.assertIn("Not yet measured", report.section_ladder({}))

    def test_layer_section_says_unsupported(self):
        got = report.section_layers(None)
        self.assertIn("Not yet measured", got)
        self.assertIn("unsupported", got)


class MispricingPickerTest(unittest.TestCase):
    RC = {
        "wire_rc": [
            {"signal": False, "clock": True,
             "mispricing": {"times_more_resistive_than_least": 9.0,
                            "least_resistive_routable_layer": "M8"}},
            {"signal": True, "clock": False,
             "mispricing": {"times_more_resistive_than_least": 3.0,
                            "least_resistive_routable_layer": "M8"}},
        ]
    }

    def test_signal_entry_is_chosen_regardless_of_order(self):
        # The clock entry comes first in the fixture on purpose: a
        # picker taking the first entry would report the clock number
        # under a signal heading, which no reader could detect.
        got = report.signal_mispricing(self.RC)
        self.assertEqual(got["times_more_resistive_than_least"], 3.0)

    def test_absent_rc_is_none_not_zero(self):
        self.assertIsNone(report.signal_mispricing(None))
        self.assertIsNone(report.signal_mispricing({"wire_rc": []}))


class LadderTest(unittest.TestCase):
    def _rung(self, stage, min_period, parasitics, propagated=0):
        return {
            "stage": stage,
            "design_stage": 3,
            "parasitics": parasitics,
            "propagated_clock": propagated,
            "time_unit": "ps",
            "clock_period": 1000.0,
            "wns": 1000.0 - min_period,
            "min_period": min_period,
        }

    def test_rungs_render_in_flow_order_not_dict_order(self):
        ladder = {
            "5_1_grt": self._rung("5_1_grt", 1000.0, "global_routing", 1),
            "2_floorplan": self._rung("2_floorplan", 800.0, "set_wire_rc"),
            "3_place": self._rung("3_place", 1400.0, "placement"),
        }
        got = report.section_ladder(ladder)
        order = [
            got.index("`2_floorplan`"),
            got.index("`3_place`"),
            got.index("`5_1_grt`"),
        ]
        self.assertEqual(order, sorted(order))

    def test_place_to_grt_gap_percentage(self):
        ladder = {
            "3_place": self._rung("3_place", 1400.0, "placement"),
            "5_1_grt": self._rung("5_1_grt", 1000.0, "global_routing", 1),
        }
        got = report.section_ladder(ladder)
        # 1400 against 1000 is 40% higher, and the direction matters:
        # reporting a pessimistic estimate as optimistic inverts the
        # study's conclusion.
        self.assertIn("40.0%", got)
        self.assertIn("higher", got)

    def test_gap_direction_is_reported_not_assumed(self):
        ladder = {
            "3_place": self._rung("3_place", 800.0, "placement"),
            "5_1_grt": self._rung("5_1_grt", 1000.0, "global_routing", 1),
        }
        self.assertIn("lower", report.section_ladder(ladder))

    def test_parasitics_branch_is_spelled_out(self):
        ladder = {"2_floorplan": self._rung("2_floorplan", 800.0, "set_wire_rc")}
        got = report.section_ladder(ladder)
        self.assertIn("one RC constant for every net", got)


if __name__ == "__main__":
    unittest.main()


class OneClockTest(unittest.TestCase):
    """A ladder read under two constraints is not a comparison."""

    def _rung(self, period):
        return {"clock_period": period, "wns": -1.0, "min_period": period + 1.0,
                "stage": "3_place", "parasitics": "placement",
                "propagated_clock": 0, "time_unit": "ps"}

    def test_one_period_passes(self):
        got = report.assert_one_clock(
            [self._rung(1000.0), self._rung(1000.0)], "test"
        )
        self.assertEqual(got, 1000.0)

    def test_mixed_periods_raise(self):
        with self.assertRaises(SystemExit):
            report.assert_one_clock(
                [self._rung(1000.0), self._rung(300.0)], "test"
            )

    def test_empty_is_none_not_an_error(self):
        self.assertIsNone(report.assert_one_clock([], "test"))


class ClosureWarningTest(unittest.TestCase):
    def _rungs(self, wns):
        return {
            "3_place": {"clock_period": 1000.0, "wns": wns,
                        "min_period": 1000.0 - wns, "stage": "3_place"},
        }

    def test_closing_shape_is_called_out(self):
        got = report._closure_warning({"u55": self._rungs(700.0)})
        self.assertIn("closes at every stage", got)
        self.assertIn("`u55`", got)
        # The point is not that it closed, but that the closure makes the
        # policy arms unreadable -- asserted on the substance rather than
        # on one word, so rewording the prose does not fail the test.
        # The mechanism, not the wording: repair stopping at zero is why
        # the period column cannot separate the settings.
        self.assertIn("stops at WNS zero", got)
        self.assertIn("runtime", got)

    def test_failing_shape_is_usable(self):
        got = report._closure_warning({"u55": self._rungs(-20.0)})
        self.assertIn("something to act on", got)

    def test_counts_multiple_closing_shapes(self):
        got = report._closure_warning(
            {"a": self._rungs(5.0), "b": self._rungs(9.0)}
        )
        self.assertIn("2 shapes", got)


class ShapeOfTest(unittest.TestCase):
    """The stem-vs-key mismatch that produced a one-row matrix."""

    def test_recovers_shape_with_underscores(self):
        self.assertEqual(report.shape_of("u12_tight_place", "3_place"), "u12_tight")

    def test_recovers_simple_shape(self):
        self.assertEqual(report.shape_of("u55_grt", "5_1_grt"), "u55")

    def test_unknown_suffix_raises_rather_than_guessing(self):
        with self.assertRaises(SystemExit):
            report.shape_of("u55_place", "5_1_grt")
