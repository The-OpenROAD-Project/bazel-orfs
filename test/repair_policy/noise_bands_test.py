"""Unit tests for noise_bands.py over synthetic data; no git involved."""

import unittest

import noise_bands as nb


class DepadTest(unittest.TestCase):
    def test_invert_padding_roundtrip(self):
        golden = 2639.14
        padded = round(golden * 1.15)
        self.assertAlmostEqual(nb.invert_padding(padded, 15.0), golden, delta=0.5)

    def test_invert_period_padding_negative(self):
        # genRuleFile: value = min(g, 0) - period*p/100
        golden, period = -64.3, 1000.0
        padded = golden - period * 5.0 / 100.0
        self.assertAlmostEqual(
            nb.invert_period_padding(padded, period, 5.0), golden, places=9
        )

    def test_invert_period_padding_met(self):
        # golden >= 0 collapses to neg = 0, so the threshold is -period*p/100
        period = 1000.0
        self.assertEqual(nb.invert_period_padding(-50.0, period, 5.0), "met")
        self.assertEqual(nb.invert_period_padding(-40.0, period, 5.0), "met")

    def test_depad_rules(self):
        rules = {
            "finish__design__instance__area": {"value": 2761, "compare": "<="},
            "detailedroute__route__wirelength": {"value": 98982, "compare": "<="},
            "detailedroute__route__drc_errors": {"value": 0, "compare": "<="},
            "finish__timing__setup__ws": {"value": -50.0, "compare": ">="},
            "finish__timing__setup__tns": {"value": -436.0, "compare": ">="},
            "cts__timing__setup__ws": {"value": -50.0, "compare": ">="},
        }
        g = nb.depad_rules(rules, 1000.0)
        self.assertAlmostEqual(g["finish__design__instance__area"], 2761 / 1.15)
        self.assertAlmostEqual(g["detailedroute__route__wirelength"], 98982 / 1.15)
        self.assertEqual(g["detailedroute__route__drc_errors"], 0.0)
        self.assertEqual(g["finish__timing__setup__ws"], "met")
        self.assertAlmostEqual(g["finish__timing__setup__tns"], -236.0)
        self.assertNotIn("cts__timing__setup__ws", g)

    def test_depad_rules_without_period_skips_timing(self):
        rules = {"finish__timing__setup__ws": {"value": -50.0, "compare": ">="}}
        self.assertEqual(nb.depad_rules(rules, None), {})


class PeriodTest(unittest.TestCase):
    def test_period_from_metadata(self):
        meta = {"constraints__clocks__details": ["core_clock: 1300.0", "x: 5"]}
        self.assertEqual(nb.period_from_metadata(meta), 1300.0)
        self.assertIsNone(nb.period_from_metadata({}))

    def test_period_from_sdc(self):
        self.assertEqual(
            nb.period_from_sdc("create_clock -period 1300 [get_ports clk]"), 1300.0
        )
        self.assertEqual(
            nb.period_from_sdc("set clk_period 3.6\ncreate_clock -period $clk_period"),
            3.6,
        )
        self.assertIsNone(nb.period_from_sdc("create_clock -period [expr 1 + 2]"))


class SeriesTest(unittest.TestCase):
    def test_merge_two_sources_drops_non_numeric_and_sorts(self):
        a = [("2024-03-01", 3.0), ("2024-01-01", "1"), ("2024-02-01", "met")]
        b = [("2023-12-01", 0.5), ("2024-04-01", None), ("2024-05-01", float("nan"))]
        self.assertEqual(
            nb.merge_series(a, b),
            [("2023-12-01", 0.5), ("2024-01-01", 1.0), ("2024-03-01", 3.0)],
        )

    def test_linear_trend_exact_line_has_zero_residuals(self):
        slope, intercept, res = nb.linear_trend([1.0, 3.0, 5.0, 7.0])
        self.assertAlmostEqual(slope, 2.0)
        self.assertAlmostEqual(intercept, 1.0)
        self.assertTrue(all(abs(r) < 1e-12 for r in res))

    def test_summarize_band_and_step(self):
        # symmetric about the mean: slope 0, residuals +-1 -> pstdev 1, band 2
        pts = [("d%d" % i, v) for i, v in enumerate([11.0, 9.0, 9.0, 11.0])]
        rec = nb.summarize(pts, "ps")
        self.assertEqual(rec["n"], 4)
        self.assertEqual((rec["first_date"], rec["last_date"]), ("d0", "d3"))
        self.assertEqual(rec["last"], 11.0)
        self.assertAlmostEqual(rec["band_2sigma"], 2.0)
        self.assertEqual(rec["max_step"], 2.0)
        self.assertEqual(rec["unit_note"], "ps")
        self.assertFalse(rec["insufficient"])

    def test_summarize_insufficient(self):
        rec = nb.summarize([("a", 1.0), ("b", 5.0)])
        self.assertTrue(rec["insufficient"])
        self.assertEqual(rec["band_2sigma"], 0.0)
        self.assertEqual(rec["max_step"], 4.0)
        empty = nb.summarize([])
        self.assertTrue(empty["insufficient"])
        self.assertIsNone(empty["last"])

    def test_band_accessor(self):
        results = {"asap7/ibex": {"m": {"band_2sigma": 3.0, "insufficient": False}}}
        self.assertEqual(nb.band(results, "asap7/ibex", "m"), 3.0)
        self.assertIsNone(nb.band(results, "asap7/ibex", "missing"))
        self.assertIsNone(nb.band(results, "nope", "m"))
        results["asap7/ibex"]["m"]["insufficient"] = True
        self.assertIsNone(nb.band(results, "asap7/ibex", "m"))


if __name__ == "__main__":
    unittest.main()
