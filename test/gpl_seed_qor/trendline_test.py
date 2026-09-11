"""The censored fit, against data whose answer is known in advance.

A Tobit fit is easy to write and easy to get quietly wrong: drop the
censored rows and the slope biases one way, impute them at the limit and
it biases the other. So the test generates data from known coefficients,
censors it, and requires the fit to come back near the truth while the
two wrong ways visibly do not.
"""

import math
import unittest

import numpy as np

import trendline


def synthetic(n=400, slope=0.08, intercept=-0.30, sigma=0.10, limit=0.0, seed=7):
    """Right-censored data from a known line."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(2.0, 5.0, n)
    latent = intercept + slope * x + rng.normal(0.0, sigma, n)
    censored = latent >= limit
    observed = np.where(censored, limit, latent)
    matrix = np.column_stack([np.ones(n), x])
    return matrix, observed, censored, latent


class TobitFit(unittest.TestCase):
    def test_recovers_the_coefficients(self):
        matrix, observed, censored, _ = synthetic()
        beta, sigma, iterations = trendline.tobit_fit(matrix, observed, censored)
        self.assertAlmostEqual(beta[0], -0.30, delta=0.05)
        self.assertAlmostEqual(beta[1], 0.08, delta=0.02)
        self.assertAlmostEqual(sigma, 0.10, delta=0.02)
        self.assertLess(iterations, trendline.MAX_ITERATIONS)

    def test_beats_dropping_the_censored_rows(self):
        matrix, observed, censored, _ = synthetic()
        beta, _, _ = trendline.tobit_fit(matrix, observed, censored)
        kept = ~censored
        naive, *_ = np.linalg.lstsq(matrix[kept], observed[kept], rcond=None)
        self.assertLess(abs(beta[1] - 0.08), abs(naive[1] - 0.08))

    def test_beats_imputing_at_the_limit(self):
        matrix, observed, censored, _ = synthetic()
        beta, _, _ = trendline.tobit_fit(matrix, observed, censored)
        naive, *_ = np.linalg.lstsq(matrix, observed, rcond=None)
        self.assertLess(abs(beta[1] - 0.08), abs(naive[1] - 0.08))

    def test_all_censored_is_refused(self):
        matrix, observed, censored, _ = synthetic()
        with self.assertRaises(ValueError):
            trendline.tobit_fit(matrix, observed, np.ones_like(censored, dtype=bool))


class DesignMatrix(unittest.TestCase):
    def test_first_platform_is_the_reference_level(self):
        rows = [
            {"platform": "asap7", "size": 100},
            {"platform": "nangate45", "size": 1000},
        ]
        matrix, names = trendline.build_design_matrix(rows, ["asap7", "nangate45"])
        self.assertEqual(names, ["intercept", "log10_instances", "platform:nangate45"])
        self.assertEqual(list(matrix[0]), [1.0, 2.0, 0.0])
        self.assertEqual(list(matrix[1]), [1.0, 3.0, 1.0])


class Residuals(unittest.TestCase):
    def test_censored_designs_report_a_bound_not_a_number(self):
        rows = [
            {"platform": "asap7", "design": "a", "size": 1000, "f": -0.2, "censored": False},
            {"platform": "asap7", "design": "b", "size": 2000, "f": -0.1, "censored": False},
            {"platform": "asap7", "design": "c", "size": 4000, "f": None, "censored": True},
        ]
        result = trendline.fit(rows)
        closed = [d for d in result["designs"] if d["design"] == "c"][0]
        self.assertNotIn("residual", closed)
        self.assertIn("residual_bound", closed)

    def test_robust_sigma_ignores_one_wild_value(self):
        clean = [0.01, -0.02, 0.015, -0.005, 0.0]
        self.assertAlmostEqual(
            trendline.robust_sigma(clean),
            trendline.robust_sigma(clean + [50.0]),
            delta=0.01,
        )


if __name__ == "__main__":
    unittest.main()
