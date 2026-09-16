"""Tests for fit_results.py — the paper's fitted figures."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fit_results import figures, fit  # noqa: E402


def point(core, per_mhz, per_joule, f_mhz=1000.0, power_w=0.01):
    return {
        "core": core,
        "coremark_per_mhz": per_mhz,
        "coremark_per_joule": per_joule,
        "frequency_mhz": f_mhz,
        "power_w": power_w,
    }


class TestFit(unittest.TestCase):
    def test_exact_power_law_is_recovered(self):
        """y = 10 * x^2 has slope 2 and fits perfectly."""
        pts = [(x, 10 * x**2) for x in (1.0, 2.0, 4.0)]
        slope, intercept, r2 = fit(pts)
        self.assertAlmostEqual(slope, 2.0)
        self.assertAlmostEqual(intercept, 1.0)
        self.assertAlmostEqual(r2, 1.0)

    def test_two_points_always_fit_exactly(self):
        _, _, r2 = fit([(1.0, 1.0), (10.0, 100.0)])
        self.assertAlmostEqual(r2, 1.0)

    def test_one_point_is_refused(self):
        with self.assertRaises(SystemExit):
            fit([(1.0, 1.0)])

    def test_identical_x_is_refused(self):
        """A vertical fit is undefined, not slope-infinity."""
        with self.assertRaises(SystemExit):
            fit([(2.0, 1.0), (2.0, 5.0)])


class TestFigures(unittest.TestCase):
    def _points(self):
        # A clean power law through the three, with the compliant core
        # deliberately a factor of 4 below the line it predicts.
        pts = [
            point("serv", 1.0, 100.0, f_mhz=1000.0, power_w=0.010),
            point("picorv32", 10.0, 1000.0, f_mhz=1000.0, power_w=0.010),
            point("ibex", 100.0, 10000.0, f_mhz=1000.0, power_w=0.010),
            point("veer", 1000.0, 25000.0, f_mhz=1000.0, power_w=0.010),
        ]
        return pts

    def test_slope_and_overprediction(self):
        f = figures(self._points())
        self.assertAlmostEqual(f["slope_cacheless"], 1.0)
        self.assertAlmostEqual(f["r2_cacheless"], 1.0)
        # the line predicts 100000 at x=1000; the point is 25000
        self.assertAlmostEqual(f["overpredicts_compliant_by"], 4.0)

    def test_spreads_are_over_the_cacheless_three_only(self):
        pts = self._points()
        pts[0]["power_w"] = 0.020  # serv draws twice picorv32/ibex
        pts[3]["power_w"] = 0.500  # the compliant core must not count
        f = figures(pts)
        self.assertAlmostEqual(f["power_spread_cacheless"], 2.0)
        self.assertAlmostEqual(f["f_over_p_spread_cacheless"], 2.0)

    def test_a_missing_core_is_fatal(self):
        pts = [p for p in self._points() if p["core"] != "ibex"]
        with self.assertRaises(SystemExit) as e:
            figures(pts)
        self.assertIn("ibex", str(e.exception))


if __name__ == "__main__":
    unittest.main()
