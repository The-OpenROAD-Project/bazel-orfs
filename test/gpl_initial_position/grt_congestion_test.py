"""Unit tests for the GRT-0096 congestion report parser."""

import unittest

import grt_congestion

REPORT = """
[INFO GRT-0018] Total wirelength: 12123 um
[INFO GRT-0096] Final congestion report:
Layer         Resource        Demand        Usage (%)    Max H / Max V / Total Congestion
----------------------------------------------------------------------------------------
M1                   0             0            0.00%             0 /  0 /  0
M2                2041           467           22.88%             0 /  0 /  0
M3                2453           462           18.83%             0 /  0 /  0
M4                1886            61            3.23%             0 /  0 /  0
----------------------------------------------------------------------------------------
Total            10625          1286           12.10%             0 /  0 /  0
"""

CONGESTED = """
[INFO GRT-0096] Final congestion report:
Layer         Resource        Demand        Usage (%)    Max H / Max V / Total Overflow
---------------------------------------------------------------------------------------
met1             30211         25809           85.43%             4 /  1 / 799
met2             38127         36714           96.29%             0 / 10 / 3532
---------------------------------------------------------------------------------------
Total           120706        107330           88.92%            10 / 17 / 6655
"""


class SummarizeTest(unittest.TestCase):
    def test_totals(self):
        out = grt_congestion.summarize(REPORT)
        self.assertEqual(out["total_resource"], 10625)
        self.assertEqual(out["total_demand"], 1286)
        self.assertAlmostEqual(out["total_usage_pct"], 12.10)
        self.assertEqual(out["total_overflow"], 0)

    def test_the_worst_layer_is_kept_because_the_total_hides_it(self):
        out = grt_congestion.summarize(REPORT)
        self.assertEqual(out["max_layer"], "M2")
        self.assertAlmostEqual(out["max_layer_usage_pct"], 22.88)

    def test_a_layer_with_no_resource_is_not_the_worst(self):
        # M1 has zero resource and zero usage; picking it as the worst
        # layer would report 0.00% for every design that does not route
        # on its first metal.
        self.assertNotEqual(grt_congestion.summarize(REPORT)["max_layer"], "M1")

    def test_clean_design_is_not_congested(self):
        self.assertFalse(grt_congestion.summarize(REPORT)["congested"])

    def test_congested_design_is_flagged_with_its_overflow(self):
        out = grt_congestion.summarize(CONGESTED)
        self.assertTrue(out["congested"])
        self.assertEqual(out["total_overflow"], 6655)
        self.assertAlmostEqual(out["total_usage_pct"], 88.92)
        self.assertEqual(out["max_layer"], "met2")

    def test_both_header_wordings_parse(self):
        # "Total Congestion" and "Total Overflow" appear in different
        # versions; the numbers are in the same columns, so the header
        # wording is deliberately not part of the match.
        self.assertIsNotNone(grt_congestion.summarize(REPORT))
        self.assertIsNotNone(grt_congestion.summarize(CONGESTED))

    def test_only_the_last_report_is_read(self):
        # Global route prints one report per extra pass when it runs
        # iterations to remove overflow. The first describes the problem
        # it then fixed; reading it would report a failure that did not
        # happen.
        out = grt_congestion.summarize(CONGESTED + REPORT)
        self.assertEqual(out["total_overflow"], 0)
        self.assertAlmostEqual(out["total_usage_pct"], 12.10)

    def test_a_run_without_the_report_is_none_not_zero(self):
        self.assertIsNone(grt_congestion.summarize("global route did not finish"))


if __name__ == "__main__":
    unittest.main()
