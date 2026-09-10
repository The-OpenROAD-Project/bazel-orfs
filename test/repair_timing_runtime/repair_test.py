#!/usr/bin/env python3
"""Tests for the repair_timing log reader, against log shapes ORFS writes."""

import unittest

import repair

HEADER = (
    "   Iter   | Removed | Resized | Inserted | Cloned |  Pin  |   Area   |"
    "    WNS   |   StTNS    |   EnTNS    |  Viol  |  Worst  \n"
    "          | Buffers |  Gates  | Buffers  |  Gates | Swaps |          |"
    "          |            |            | Endpts | St/EnPt \n"
    "------------------------------------------------------------------\n"
)


def row(it, marker, wns, tns, stamp=None, viol=17228):
    prefix = "[{:9.3f}] ".format(stamp) if stamp is not None else ""
    return "{}{:>9}{} |       0 |       1 |        5 |      0 |     4 |    +0.0% | {} | -6013988.5 | {} |  {} | core/x\n".format(
        prefix, it, marker, wns, tns, viol
    )


UNSTAMPED = (
    "repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose\n"
    "[INFO RSZ-0099] Repairing 17228 out of 17228 (100.00%) violating endpoints...\n"
    + HEADER
    + row(0, "*", -2082.577, -10232514.0)
    + row(10, "*", -2029.806, -10185645.0)
    + row(200, "*", -2017.137, -10173425.0)
    + row(1200, "*", -2017.137, -10173425.0)
    + row(1206, "+", -2015.784, -10172325.0)
    + row("final", "", -2015.784, -10172325.0)
    + "[INFO RSZ-0059] Removed 3 buffers.\n"
    "[WARNING RSZ-0062] Unable to repair all setup violations.\n"
    "[INFO RSZ-0505] Runtime: 634.78s\n"
    "[INFO RSZ-0033] No hold violations found.\n"
    "[INFO RSZ-0506] Runtime: 0.87s\n"
    "Took 636 seconds: repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose\n"
)

STAMPED_GRT = (
    "[  300.000] repair_design -verbose\n"
    "[  337.000] [INFO RSZ-0504] Runtime: 37.02s\n"
    "[  338.000] Took 38 seconds: repair_design -verbose\n"
    "[  347.000] repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose\n"
    "[  347.500] [INFO RSZ-0099] Repairing 100 out of 500 (20.00%) violating endpoints...\n"
    + HEADER
    + row(0, "*", -100.0, -5000.0, stamp=348.0, viol=500)
    + row(10, "*", -90.0, -4000.0, stamp=400.0, viol=400)
    + row(20, "*", -90.0, -4000.0, stamp=900.0, viol=400)
    + row("final", "", -90.0, -4000.0, stamp=900.5, viol=400)
    + "[  901.000] [INFO RSZ-0505] Runtime: 553.00s\n"
    "[  901.000] [INFO RSZ-0032] Inserted 7 hold buffers.\n"
    "[  902.000] [INFO RSZ-0506] Runtime: 1.00s\n"
    "[  903.000] Took 556 seconds: repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose\n"
    '[  950.000] repair_timing -setup -sequence "vt_swap reroute" -skip_last_gasp -repair_tns 0 -verbose\n'
    "[  964.000] [INFO RSZ-0505] Runtime: 13.88s\n"
    '[  964.000] Took 14 seconds: repair_timing -setup -sequence "vt_swap reroute" -skip_last_gasp -repair_tns 0 -verbose\n'
)


class ParseArgs(unittest.TestCase):
    def test_values_and_flags(self):
        got = repair.parse_args(
            ' -setup_margin 0 -repair_tns 100 -skip_last_gasp -sequence "vt_swap reroute" -verbose'
        )
        self.assertEqual(got["setup_margin"], "0")
        self.assertEqual(got["repair_tns"], "100")
        self.assertIs(got["skip_last_gasp"], True)
        self.assertEqual(got["sequence"], "vt_swap reroute")
        self.assertIs(got["verbose"], True)

    def test_negative_margin_is_a_value_not_a_flag(self):
        got = repair.parse_args(" -hold_margin -30 -verbose")
        self.assertEqual(got["hold_margin"], "-30")


class Unstamped(unittest.TestCase):
    def setUp(self):
        self.calls = repair.parse_log(UNSTAMPED)

    def test_one_call_with_both_runtimes(self):
        self.assertEqual(len(self.calls), 1)
        call = self.calls[0]
        self.assertEqual(call["command"], "repair_timing")
        self.assertEqual(call["setup_s"], 634.78)
        self.assertEqual(call["hold_s"], 0.87)
        self.assertEqual(call["took_s"], 636)
        self.assertEqual(call["repairing"], (17228, 17228, 100.0))
        self.assertTrue(call["unrepaired"])
        self.assertEqual(call["hold_buffers"], 0)

    def test_rows_keep_marker_and_final(self):
        rows = self.calls[0]["rows"]
        self.assertEqual([r["iter"] for r in rows], [0, 10, 200, 1200, 1206, "final"])
        self.assertEqual(rows[4]["marker"], "+")
        self.assertIsNone(rows[0]["t_s"])

    def test_useful_prefix_stops_where_wns_stops(self):
        """Iterations 200..1200 bought nothing: the grind's dead share."""
        got = repair.useful_prefix(self.calls[0]["rows"])
        self.assertEqual(got["last_improving_iter"], 200)
        self.assertEqual(got["final_iter"], 1200)
        self.assertEqual(got["wns_end"], -2015.784)

    def test_summary_counts_iterations_not_rows(self):
        got = repair.summarize(self.calls)[0]
        self.assertEqual(got["iterations"], 1206)
        self.assertEqual(got["kind"], "setup_hold")
        self.assertEqual(got["witness"]["repair_tns"], "100")


class Stamped(unittest.TestCase):
    def setUp(self):
        self.calls = repair.parse_log(STAMPED_GRT)

    def test_three_calls_in_order(self):
        kinds = [s["kind"] for s in repair.summarize(self.calls)]
        self.assertEqual(kinds, ["repair_design", "setup_hold", "post_grt_wns"])

    def test_repair_design_runtime_lands_on_its_own_call(self):
        self.assertEqual(self.calls[0]["repair_design_s"], 37.02)
        self.assertIsNone(self.calls[1]["repair_design_s"])

    def test_stamps_make_the_trajectory_a_time_series(self):
        got = repair.useful_prefix(self.calls[1]["rows"])
        self.assertEqual(got["t_last_improvement_s"], 400.0)
        self.assertEqual(got["t_final_s"], 900.5)

    def test_hold_buffers_and_partial_endpoints(self):
        self.assertEqual(self.calls[1]["hold_buffers"], 7)
        self.assertEqual(self.calls[1]["repairing"], (100, 500, 20.0))

    def test_post_grt_call_has_no_hold(self):
        self.assertIsNone(self.calls[2]["hold_s"])
        self.assertEqual(self.calls[2]["setup_s"], 13.88)


if __name__ == "__main__":
    unittest.main()
