#!/usr/bin/env python3
"""Tests for the phase reader.

The fixtures are real lines from a jpeg 5_1_grt log, because the point
of this reader is to survive what ORFS actually writes -- including a
`Took` line whose command carries a long argument list, and two
`RSZ-0505 Runtime:` lines from two separate repair_timing calls.
"""

import unittest

import phases

# Verbatim from a jpeg 5_1_grt.log, trimmed to the lines that matter.
REAL_GRT = """\
Took 34 seconds: pin_access
[INFO GRT-0020] Min routing layer: M2
global_route -congestion_report_file ./x/congestion.rpt -verbose
Took 13 seconds: global_route -congestion_report_file ./x/congestion.rpt -verbose
repair_design -verbose
[INFO RSZ-0504] Runtime: 3.47s
repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose
[INFO RSZ-0505] Runtime: 119.68s
[INFO RSZ-0033] No hold violations found.
[INFO RSZ-0506] Runtime: 0.22s
Took 120 seconds: repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose
Repair antennas...
[INFO RSZ-0505] Runtime: 1.33s
Elapsed time: 4:03.00[h:]min:sec. CPU time: user 5000.00 sys 100.00 (2000%). Peak memory: 100KB.
"""

# The same shape log_timestamps.py produces: "[{:9.3f}] " per line.
STAMPED = """\
[    0.000] Running cts.tcl, stage 4_1_cts
[   12.500] Took 12 seconds: clock_tree_synthesis
[  100.250] Took 88 seconds: repair_timing -hold -verbose
[  101.000] Elapsed time: 1:41.00[h:]min:sec. CPU time: user 300.00 sys 5.00 (300%). Peak memory: 100KB.
"""

NO_PHASES = """\
[INFO GPL-0002] DBU: 1000
Design area 44 um^2 72% utilization.
Elapsed time: 0:08.91[h:]min:sec. CPU time: user 60.83 sys 16.79 (871%). Peak memory: 437776KB.
"""


class ParsePhases(unittest.TestCase):
    def test_reads_the_real_grt_stack(self):
        got = phases.parse_phases(REAL_GRT)
        took = [p["name"] for p in got["phases"] if p["source"] == "took"]
        self.assertEqual(took, ["pin_access", "global_route", "repair_timing"])

    def test_a_long_argument_list_does_not_swallow_the_name(self):
        """global_route's command line is 200 chars; the name is the
        first token, and the rest is detail."""
        got = phases.parse_phases(REAL_GRT)
        gr = [p for p in got["phases"] if p["name"] == "global_route"][0]
        self.assertIn("congestion_report_file", gr["detail"])
        self.assertAlmostEqual(gr["seconds"], 13.0)

    def test_a_runtime_inside_a_took_span_is_not_double_counted(self):
        """RSZ-0505/0506 sit within `Took ... repair_timing`. Counting
        both would charge the same 120 seconds twice."""
        got = phases.parse_phases(REAL_GRT)
        nested = {(n["tool"] + "-" + n["code"]) for n in got["nested"]}
        self.assertIn("RSZ-0505", nested)
        self.assertIn("RSZ-0506", nested)
        # 34 + 13 + 120 from Took, plus the two uncovered runtimes.
        self.assertAlmostEqual(got["attributed_s"], 167.0 + 3.47 + 1.33)

    def test_repair_design_is_not_filed_under_repair_timing(self):
        """The bug a "next Took wins" rule would introduce: RSZ-0504 is
        repair_design's runtime and has no Took line of its own, but the
        next Took line belongs to repair_timing. Charging it there would
        be the wrong region and so the wrong policy conclusion."""
        got = phases.parse_phases(REAL_GRT)
        by_name = {p["name"]: p for p in got["phases"]}
        self.assertIn("RSZ-0504", by_name)
        self.assertEqual(by_name["RSZ-0504"]["source"], "runtime")
        self.assertAlmostEqual(by_name["RSZ-0504"]["seconds"], 3.47)
        self.assertAlmostEqual(by_name["repair_timing"]["seconds"], 120.0)

    def test_a_log_with_no_took_lines_still_attributes_its_tool_runtimes(self):
        """4_1_cts has no Took lines at all; CTS-0500 is the only
        attribution there is, so it must be counted, not discarded."""
        cts = (
            "[INFO CTS-0500] Runtime: 1.41s\n"
            "[INFO DPL-0500] Runtime: 0.25s\n"
            "Elapsed time: 0:02.48[h:]min:sec. CPU time: user 2.50 "
            "sys 0.10 (104%). Peak memory: 100KB.\n"
        )
        got = phases.parse_phases(cts)
        self.assertEqual(got["nested"], [])
        self.assertAlmostEqual(got["attributed_s"], 1.66)

    def test_repeated_command_names_stay_distinguishable(self):
        text = "Took 5 seconds: repair_timing -setup\nTook 7 seconds: repair_timing -hold\n"
        got = phases.parse_phases(text)
        self.assertEqual([p["order"] for p in got["phases"]], [0, 1])
        self.assertEqual(phases.by_name(got), {"repair_timing": 12.0})

    def test_no_took_lines_degrades_to_unattributed_not_zero(self):
        """A substep with no phase markers must report the whole wall as
        unattributed, never silently as an accounted-for zero."""
        got = phases.parse_phases(NO_PHASES)
        self.assertEqual(got["phases"], [])
        self.assertAlmostEqual(got["attributed_s"], 0.0)
        rec = phases.reconcile(got, wall_s=8.91)
        self.assertAlmostEqual(rec["unattributed_s"], 8.91)


class Stamps(unittest.TestCase):
    def test_detects_stamped_and_unstamped_logs(self):
        self.assertTrue(phases.is_stamped(STAMPED))
        self.assertFalse(phases.is_stamped(REAL_GRT))

    def test_took_lines_parse_behind_a_stamp(self):
        got = phases.parse_phases(STAMPED)
        self.assertEqual(
            [p["name"] for p in got["phases"]],
            ["clock_tree_synthesis", "repair_timing"],
        )

    def test_span_is_the_elapsed_range(self):
        self.assertAlmostEqual(phases.elapsed_span(STAMPED), 101.0)
        self.assertIsNone(phases.elapsed_span(REAL_GRT))


class Reconcile(unittest.TestCase):
    def test_a_stack_that_adds_up_is_ok(self):
        got = phases.parse_phases(REAL_GRT)
        rec = phases.reconcile(got, wall_s=243.0)
        self.assertTrue(rec["ok"])
        self.assertAlmostEqual(rec["unattributed_s"], 243.0 - (167.0 + 3.47 + 1.33))

    def test_over_attribution_is_reported_not_clamped(self):
        """Attributing more than the wall means overlapping phases were
        summed. That is a parser bug and must surface as one."""
        got = phases.parse_phases(REAL_GRT)
        rec = phases.reconcile(got, wall_s=10.0)
        self.assertTrue(rec["over_attributed"])
        self.assertFalse(rec["ok"])
        self.assertLess(rec["unattributed_s"], 0)

    def test_whole_second_rounding_is_tolerated(self):
        """Took reports whole seconds, so k phases can be off by k."""
        got = phases.parse_phases(REAL_GRT)
        rec = phases.reconcile(got, wall_s=166.0)
        self.assertTrue(rec["ok"])


if __name__ == "__main__":
    unittest.main()
