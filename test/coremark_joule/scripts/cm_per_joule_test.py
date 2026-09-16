#!/usr/bin/env python3
"""Unit tests for the CoreMark/Joule arithmetic."""

import os
import sys
import unittest
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cm_per_joule import combine, frequency_mhz_from_sdc, power_groups  # noqa: E402


class CmPerJouleTest(unittest.TestCase):
    def test_measured_picorv32_point(self):
        r = combine(0.5531, 1000.0, 0.00658)
        self.assertAlmostEqual(553.1, r["coremark_score"], places=1)
        self.assertAlmostEqual(84057.8, r["coremark_per_joule"], places=0)

    def test_power_groups_carry_every_cell_kind(self):
        report = {
            "Sequential": {
                "internal": 0.002,
                "switching": 0.0001,
                "leakage": 1e-7,
                "total": 0.0021,
            },
            "Combinational": {
                "internal": 0.007,
                "switching": 0.011,
                "leakage": 1e-6,
                "total": 0.018,
            },
            "Clock": {
                "internal": 0.0015,
                "switching": 0.0012,
                "leakage": 1e-8,
                "total": 0.0027,
            },
            "Macro": {
                "internal": 0.015,
                "switching": 0.0,
                "leakage": 0.0,
                "total": 0.015,
            },
            "Pad": {"internal": 0.0, "switching": 0.0, "leakage": 0.0, "total": 0.0},
            "Total": {
                "internal": 0.0255,
                "switching": 0.0123,
                "leakage": 1.1e-6,
                "total": 0.0378,
            },
        }
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            with open(path, "w") as f:
                json.dump(report, f)
            g = power_groups(path)
        self.assertEqual(g["macro"], 0.015)
        self.assertAlmostEqual(g["dynamic"], 0.0378)
        # Every cell-kind group, Pad and Total left out: §4.7 renders these.
        self.assertEqual(
            g["groups"],
            {
                "Sequential": 0.0021,
                "Combinational": 0.018,
                "Clock": 0.0027,
                "Macro": 0.015,
            },
        )

    def test_frequency_cancels_for_fixed_energy_per_cycle(self):
        """Doubling f at doubled power leaves CoreMark/Joule unchanged.

        This is §2.3's identity, pinned in the arithmetic: dynamic power
        is proportional to frequency, so the f cancels and energy per
        unit of work does not depend on the clock. Leakage is what breaks
        it in a real design -- leakage energy per operation falls as 1/f
        -- which is why the cancellation holds exactly only here, where
        the power is supplied rather than measured.
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


class TestFrequencyFromSdc(unittest.TestCase):
    """The reported frequency and the built period are one fact.

    They were two: a literal in sim/BUILD.bazel and a period in the
    design's constraints.sdc, maintained alongside each other. They
    drifted, and the study reported ibex at 833 MHz on a netlist that
    missed its 1200 ps period by 74 ps.
    """

    def test_reads_the_period(self):
        self.assertAlmostEqual(
            frequency_mhz_from_sdc("set clk_period 1591\n"),
            628.5355122564425,
        )

    def test_ignores_other_settings(self):
        sdc = "set clk_name clk\nset clk_period 438\nset foo 12\n"
        self.assertAlmostEqual(frequency_mhz_from_sdc(sdc), 2283.10502283105)

    def test_a_missing_period_is_fatal(self):
        with self.assertRaises(SystemExit):
            frequency_mhz_from_sdc("set clk_name clk\n")


if __name__ == "__main__":
    unittest.main()
