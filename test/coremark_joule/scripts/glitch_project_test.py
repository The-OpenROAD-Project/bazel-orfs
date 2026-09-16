"""Tests for glitch_project.py — reweighting a window onto an iteration."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from glitch_project import project, rates  # noqa: E402


def arm(busy_cycles, cycles, busy, idle, bursts):
    return {
        "busy_cycles": busy_cycles,
        "busy_bursts": bursts,
        "busy_fraction": busy_cycles / cycles,
        "cycles": cycles,
        "transitions_subtree_busy": busy,
        "transitions_subtree_idle": idle,
    }


class TestRates(unittest.TestCase):
    def test_rates_are_per_cycle_of_the_right_kind(self):
        r = rates(arm(100, 1000, 500, 900, 25))
        self.assertAlmostEqual(r["busy"], 5.0)
        self.assertAlmostEqual(r["idle"], 1.0)

    def test_a_window_with_no_idle_cycles_is_refused(self):
        with self.assertRaises(ValueError):
            rates(arm(1000, 1000, 500, 0, 25))


class TestProject(unittest.TestCase):
    def test_arms_must_agree_on_the_operation_count(self):
        """A different instruction stream is a broken run, not a result."""
        z = arm(100, 1000, 500, 900, 25)
        s = arm(100, 1000, 700, 1800, 24)
        with self.assertRaises(ValueError):
            project(z, s, 0.05, 1000)

    def test_zero_glitch_when_the_arms_match(self):
        z = arm(100, 1000, 500, 900, 25)
        r = project(z, dict(z), 0.05, 100000)
        self.assertAlmostEqual(r["glitch_per_iteration"], 0.0)
        self.assertAlmostEqual(r["glitch_fraction"], 0.0)
        self.assertAlmostEqual(r["glitch_ratio"], 1.0)

    def test_the_iteration_duty_reweights_the_window(self):
        """A window measured hot must not be read as the whole run.

        Busy cycles glitch at 5/cycle here and idle cycles at 1/cycle.
        The window is 10 % busy; the iteration is 1 %. Projecting must
        use the iteration's mix, so the answer is 0.01*5 + 0.99*1 per
        cycle, not the window's 0.1*5 + 0.9*1.
        """
        z = arm(100, 1000, 0, 0, 25)
        s = arm(100, 1000, 500, 900, 25)
        r = project(z, s, 0.01, 10000)
        self.assertAlmostEqual(r["glitch_per_iteration"], 10000 * (0.01 * 5 + 0.99 * 1))

    def test_per_operation_and_per_idle_cycle_are_reported_separately(self):
        """The two figures that carry to another workload unchanged."""
        z = arm(100, 1000, 100, 900, 25)
        s = arm(100, 1000, 350, 2700, 25)
        r = project(z, s, 0.05, 1000)
        self.assertAlmostEqual(r["glitch_per_operation"], (350 - 100) / 25)
        self.assertAlmostEqual(r["glitch_per_idle_cycle"], (2700 - 900) / 900)

    def test_power_is_the_measured_share_scaled_by_the_measured_ratio(self):
        z = arm(100, 1000, 100, 900, 25)
        s = arm(100, 1000, 200, 1800, 25)
        r = project(z, s, 0.1, 1000, unit_dynamic_w=0.000265, core_power_w=0.019)
        # Every rate doubles, so the glitch equals the useful switching.
        self.assertAlmostEqual(r["unit_glitch_w"], 0.000265)
        self.assertAlmostEqual(r["glitch_share_of_core"], 0.000265 / 0.019)
        self.assertAlmostEqual(r["glitch_fraction"], 0.5)


if __name__ == "__main__":
    unittest.main()
