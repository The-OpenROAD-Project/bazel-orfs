"""Tests for the silicon extraction arithmetic.

The properties worth pinning are the ones the chapter's argument rests
on: that the slope estimator is immune to a constant meter offset,
which is the whole reason it is preferred over the spreadsheet's
idle-subtraction, and that the two estimators agree when the data is
clean, so a disagreement in the real data means something.
"""

import os
import sys
import unittest

# Same preamble as parsers_test.py: under bazel the test runs from a
# runfiles tree where its siblings are not importable by bare name.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract_silicon as es  # noqa: E402


def line(slope, intercept, ns, iterations=10000.0):
    """A synthetic sweep on a perfect line, at fixed throughput."""
    return [(n, slope * n + intercept, iterations) for n in ns]


class SlopeTest(unittest.TestCase):
    def test_recovers_an_exact_slope(self):
        rows = line(3.0, 167.0, range(1, 11))
        slope, intercept, resid = es.slope_watts_per_core(rows, (1, 10))
        self.assertAlmostEqual(slope, 3.0)
        self.assertAlmostEqual(intercept, 167.0)
        self.assertAlmostEqual(resid, 0.0)

    def test_constant_offset_cancels(self):
        # The reason this estimator exists: a meter reading 100 W high
        # changes the intercept and not the slope, so per-core power
        # survives an error that would swamp an idle subtraction.
        base = es.slope_watts_per_core(line(3.0, 167.0, range(1, 11)), (1, 10))
        offset = es.slope_watts_per_core(line(3.0, 267.0, range(1, 11)), (1, 10))
        self.assertAlmostEqual(base[0], offset[0])
        self.assertNotAlmostEqual(base[1], offset[1])

    def test_fit_range_excludes_the_throttled_tail(self):
        # Flat to 5, then the part gives up power per core. Fitting the
        # whole sweep would report a slope that is neither regime.
        rows = line(3.0, 10.0, range(1, 6)) + [
            (n, 25.0 + 1.0 * n, 8000.0) for n in range(6, 11)
        ]
        inside, _, _ = es.slope_watts_per_core(rows, (1, 5))
        whole, _, _ = es.slope_watts_per_core(rows, (1, 10))
        self.assertAlmostEqual(inside, 3.0)
        self.assertNotAlmostEqual(whole, 3.0, places=1)

    def test_residual_reports_a_bent_region(self):
        rows = line(3.0, 10.0, range(1, 5)) + [(5, 40.0, 10000.0)]
        _, _, resid = es.slope_watts_per_core(rows, (1, 5))
        self.assertGreater(resid, 1.0)

    def test_too_few_points_is_an_error(self):
        with self.assertRaises(SystemExit):
            es.slope_watts_per_core(line(3.0, 10.0, [1]), (1, 1))


class ThroughputTest(unittest.TestCase):
    def test_takes_the_unthrottled_maximum_in_range(self):
        rows = [(1, 10.0, 28800.0), (2, 13.0, 28000.0), (40, 100.0, 22000.0)]
        self.assertEqual(es.unthrottled_throughput(rows, (1, 2)), 28800.0)


class BuildPartTest(unittest.TestCase):
    def meta(self, **kw):
        base = {
            "vendor": "V",
            "part": "P",
            "microarchitecture": "U",
            "cores": 8,
            "threads": 8,
            "smt": False,
            "clock_mhz": 1000,
            "node": "N",
            "node_note": "",
            "tdp_w": None,
            "workload": "W",
            "fit_range": (1, 8),
            "header_row": 1,
        }
        base.update(kw)
        return base

    def test_energy_arithmetic(self):
        # 2 W per core at 10 000 iterations/s is 200 uJ per iteration.
        rows = line(2.0, 100.0, range(1, 9), iterations=10000.0)
        part = es.build_part(self.meta(), 100.0, rows)
        self.assertAlmostEqual(part["slope_w_per_core"], 2.0)
        self.assertAlmostEqual(part["uj_per_iteration_slope"], 200.0)
        self.assertAlmostEqual(part["coremark_per_mj_slope"], 5.0)
        self.assertAlmostEqual(part["coremark_per_mhz"], 10.0)

    def test_estimators_agree_when_idle_is_the_intercept(self):
        # With a perfectly linear sweep whose intercept is the measured
        # idle, subtracting idle and fitting a slope are the same
        # operation. They diverge in the real data because the intercept
        # is not the idle reading -- which is the finding.
        rows = line(2.0, 100.0, range(1, 9), iterations=10000.0)
        part = es.build_part(self.meta(), 100.0, rows)
        for point in part["sweep"]:
            self.assertAlmostEqual(
                point["uj_per_iteration_delta"],
                point["uj_per_iteration_slope"],
                places=6,
            )

    def test_estimators_disagree_when_idle_is_not_the_intercept(self):
        # A platform that wakes shared logic on the first core: the
        # intercept sits above idle, so idle-subtraction attributes that
        # one-off to the cores and the slope does not.
        rows = line(2.0, 110.0, range(1, 9), iterations=10000.0)
        part = es.build_part(self.meta(), 100.0, rows)
        first = part["sweep"][0]
        self.assertGreater(
            first["uj_per_iteration_delta"], first["uj_per_iteration_slope"]
        )

    def test_relative_throughput_is_against_the_sweep_peak(self):
        rows = [(1, 10.0, 1000.0), (2, 12.0, 500.0)]
        part = es.build_part(self.meta(fit_range=(1, 2)), 8.0, rows)
        self.assertAlmostEqual(part["sweep"][0]["relative_throughput"], 1.0)
        self.assertAlmostEqual(part["sweep"][1]["relative_throughput"], 0.5)


if __name__ == "__main__":
    unittest.main()
