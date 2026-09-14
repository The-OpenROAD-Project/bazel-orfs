#!/usr/bin/env python3
"""Unit tests for the CoreMark/Joule arithmetic."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cm_per_joule import combine  # noqa: E402


class CmPerJouleTest(unittest.TestCase):
    def test_measured_picorv32_point(self):
        r = combine(0.5531, 1000.0, 0.00658)
        self.assertAlmostEqual(553.1, r["coremark_score"], places=1)
        self.assertAlmostEqual(84057.8, r["coremark_per_joule"], places=0)

    def test_frequency_cancels_for_fixed_energy_per_cycle(self):
        """Doubling f at doubled power leaves CoreMark/Joule unchanged.

        Dynamic power is proportional to frequency, so the y-axis is close
        to a pure architecture metric and the plot is not merely a
        restatement of the x-axis. Leakage is what breaks the identity,
        which is why it is worth stating that it holds exactly only here.
        """
        a = combine(2.0, 500.0, 0.010)
        b = combine(2.0, 1000.0, 0.020)
        self.assertAlmostEqual(
            a["coremark_per_joule"], b["coremark_per_joule"], places=6
        )

    def test_joule_per_iteration_is_the_reciprocal(self):
        r = combine(1.0, 1000.0, 0.5)
        self.assertAlmostEqual(
            1.0 / r["coremark_per_joule"], r["joule_per_iteration"], places=12
        )


if __name__ == "__main__":
    unittest.main()
