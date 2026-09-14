"""Unit tests for the Nesterov progress-table parser."""

import os
import unittest

import gpl_progress

HERE = os.path.dirname(os.path.abspath(__file__))


def fixture(name):
    with open(os.path.join(HERE, "testdata", name), errors="replace") as handle:
        return handle.read()


SYNTHETIC = """
[INFO GPL-0084] ---- Execute Nesterov Global Placement.
Iteration | Overflow |     HPWL (um) |  HPWL(%) |   Penalty | Group
---------------------------------------------------------------
        0 |   0.5767 |  4.030260e+02 |   +0.00% |  3.82e-11 |
       10 |   0.6024 |  4.329450e+02 |   +7.42% |  6.22e-11 |
[INFO GPL-0100] Timing-driven iteration 1/2, virtual: false.
Iteration | Overflow |     HPWL (um) |  HPWL(%) |   Penalty | Group
---------------------------------------------------------------
       20 |   0.3011 |  4.510000e+02 |   +4.17% |  9.10e-11 |
       30 |   0.0980 |  4.612000e+02 |   +2.26% |  1.10e-10 |
"""


class RowsTest(unittest.TestCase):
    def test_reads_rows_from_every_segment(self):
        rows = gpl_progress.rows(SYNTHETIC)
        self.assertEqual([row["iteration"] for row in rows], [0, 10, 20, 30])
        self.assertAlmostEqual(rows[-1]["hpwl"], 461.2, places=4)
        self.assertAlmostEqual(rows[-1]["overflow"], 0.0980, places=6)

    def test_no_table_yields_nothing(self):
        self.assertEqual(gpl_progress.rows("no placement"), [])


class SegmentsTest(unittest.TestCase):
    def test_counts_the_tables_not_the_interruptions(self):
        self.assertEqual(gpl_progress.segments(SYNTHETIC), 2)

    def test_a_real_log_has_at_least_one(self):
        self.assertGreaterEqual(
            gpl_progress.segments(fixture("place_gp_anchored.log")), 1
        )


class SummarizeTest(unittest.TestCase):
    def test_endpoint_is_the_last_row_of_the_last_segment(self):
        out = gpl_progress.summarize(SYNTHETIC)
        self.assertEqual(out["iterations"], 30)
        self.assertAlmostEqual(out["hpwl_final"], 461.2, places=4)
        self.assertAlmostEqual(out["hpwl_first"], 403.026, places=4)
        self.assertEqual(out["rows"], 4)
        self.assertEqual(out["segments"], 2)
        self.assertTrue(out["ran"])

    def test_divergence_flags_default_false(self):
        out = gpl_progress.summarize(SYNTHETIC)
        self.assertFalse(out["diverge_revert"])
        self.assertFalse(out["diverge_fatal"])

    def test_divergence_is_reported_when_the_placer_says_so(self):
        out = gpl_progress.summarize(
            SYNTHETIC + "\nDivergence detected, reverting to snapshot\n"
        )
        self.assertTrue(out["diverge_revert"])

    def test_real_log_parses(self):
        out = gpl_progress.summarize(fixture("place_gp_anchored.log"))
        self.assertIsNotNone(out)
        self.assertTrue(out["ran"])
        self.assertGreater(out["hpwl_final"], 0)

    def test_no_table_returns_none(self):
        # -skip_nesterov_place, or a run that died first. None rather than
        # a zero-filled record, so a failed arm is visible as missing
        # instead of arriving in the tables as a very good result.
        self.assertIsNone(gpl_progress.summarize("nothing here"))


if __name__ == "__main__":
    unittest.main()
