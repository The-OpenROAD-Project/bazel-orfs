#!/usr/bin/env python3
"""Tests for the dominance verdict over full-flow arms."""

import unittest

import verdict


def record(design, ws, tns, area, wl, drc, walls, sha, power=0.01, period="clk: 1000.0"):
    steps = {
        "6_report": {
            "finish__timing__setup__ws": ws,
            "finish__timing__setup__tns": tns,
            "finish__timing__hold__ws": 10.0,
            "finish__design__instance__area": area,
            "finish__power__total": power,
            "constraints__clocks__details": [period],
        },
        "5_2_route": {
            "detailedroute__route__wirelength": wl,
            "detailedroute__route__drc_errors": drc,
            "detailedroute__antenna__violating__nets": 0,
        },
    }
    substeps = {"2_1_floorplan": {"wall_s": walls[0]}, "4_1_cts": {"wall_s": walls[1]},
                "5_1_grt": {"wall_s": walls[2]}, "_metrics": steps, "_final_sha1": sha}
    return {"design": design, "stage": "full", "arm": "x", "repeat": 1, "substeps": substeps}


BANDS = {"asap7/ibex": {"min_period_ps": {"band_2sigma": 60.0, "insufficient": False},
                        "finish__timing__setup__tns": {"band_2sigma": 500.0, "insufficient": False},
                        "finish__design__instance__area": {"band_2sigma": 30.0, "insufficient": False},
                        "finish__power__total": {"insufficient": True},
                        "detailedroute__route__wirelength": {"band_2sigma": 2000.0, "insufficient": False}}}


class Judge(unittest.TestCase):
    def test_signs_and_bands(self):
        # Larger-is-better axis (TNS): -100 -> -50 is better.
        self.assertEqual(verdict.judge(-100.0, -50.0, +1, 10.0)[1], "better")
        # Smaller-is-better axis (area): 100 -> 105 with band 10 is noise, 120 is worse.
        self.assertEqual(verdict.judge(100.0, 105.0, -1, 10.0)[1], "within noise")
        self.assertEqual(verdict.judge(100.0, 120.0, -1, 10.0)[1], "WORSE")
        self.assertEqual(verdict.judge(100.0, 100.0, -1, None)[1], "same")
        self.assertEqual(verdict.judge(None, 1.0, -1, None)[1], "no data")


class ClockPeriodFallback(unittest.TestCase):
    def test_period_from_bands_when_metrics_lack_it(self):
        r = record("ibex", -20.0, -300.0, 2700, 90000, 0, (80, 60, 130), "a")
        del r["substeps"]["_metrics"]["6_report"]["constraints__clocks__details"]
        self.assertIsNone(verdict.kpis(r)["min_period"])
        bands = dict(BANDS); bands["asap7/ibex"] = dict(BANDS["asap7/ibex"], _sources={"period": 1260.0})
        self.assertAlmostEqual(verdict.kpis(r, bands)["min_period"], 1280.0)


class Design(unittest.TestCase):
    def test_identical_flow_faster_passes(self):
        base = record("ibex", -20.0, -300.0, 2700, 90000, 0, (80, 60, 130), "abc")
        pol = record("ibex", -20.0, -300.0, 2700, 90000, 0, (40, 30, 70), "abc")
        v = verdict.design_verdict(base, pol, BANDS)
        self.assertTrue(v["dominated_or_tied"])
        self.assertTrue(v["same_odb"])
        self.assertAlmostEqual(v["wall_pct"], -100 * 130 / 270)

    def test_min_period_inside_band_passes_outside_fails(self):
        base = record("ibex", -20.0, -300.0, 2700, 90000, 0, (80, 60, 130), "a")
        inside = record("ibex", -60.0, -300.0, 2700, 90000, 0, (70, 60, 130), "b")
        outside = record("ibex", -100.0, -300.0, 2700, 90000, 0, (70, 60, 130), "c")
        self.assertTrue(verdict.design_verdict(base, inside, BANDS)["dominated_or_tied"])
        self.assertFalse(verdict.design_verdict(base, outside, BANDS)["dominated_or_tied"])

    def test_one_drc_error_fails_regardless_of_band(self):
        base = record("ibex", -20.0, -300.0, 2700, 90000, 0, (80, 60, 130), "a")
        pol = record("ibex", -20.0, -300.0, 2700, 90000, 1, (40, 30, 70), "b")
        self.assertFalse(verdict.design_verdict(base, pol, BANDS)["dominated_or_tied"])

    def test_slower_with_different_odb_fails(self):
        base = record("ibex", -20.0, -300.0, 2700, 90000, 0, (80, 60, 130), "a")
        pol = record("ibex", -20.0, -300.0, 2700, 90000, 0, (80, 60, 160), "b")
        self.assertFalse(verdict.design_verdict(base, pol, BANDS)["dominated_or_tied"])

    def test_table_counts_passes(self):
        base = record("ibex", -20.0, -300.0, 2700, 90000, 0, (80, 60, 130), "a")
        pol = record("ibex", -20.0, -300.0, 2700, 90000, 0, (40, 30, 70), "a")
        text = verdict.suite_table([verdict.design_verdict(base, pol, BANDS)])
        self.assertIn("1 of 1 designs pass", text)
        self.assertIn("| ibex | 270 | 140 | -130 (-48%) |", text)


if __name__ == "__main__":
    unittest.main()
