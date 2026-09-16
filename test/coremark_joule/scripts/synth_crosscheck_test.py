#!/usr/bin/env python3
"""synth_crosscheck's arithmetic, over a fixture with known answers."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import synth_crosscheck  # noqa: E402


def report(total, macro, total_leak, macro_leak, clock):
    return {
        "Total": {"total": total, "leakage": total_leak},
        "Macro": {"total": macro, "leakage": macro_leak},
        "Clock": {"total": clock},
    }


class SynthCrosscheckTest(unittest.TestCase):
    def test_core_only_energy(self):
        # 20.6 mW total, 11.9 mW macro -> 8.7 mW core; 407,448 cycles at
        # 1200 ps is 488.9 us, so 4.254 uJ core-only per iteration.
        r = synth_crosscheck.arm_row(
            "grt", 1200, report(0.0206, 0.0119, 0.001, 0.0006, 0.0033), 407448
        )
        self.assertAlmostEqual(r["core_w"], 0.0087)
        self.assertAlmostEqual(r["core_leak_w"], 0.0004)
        self.assertAlmostEqual(r["core_uj"], 0.0087 * 407448 * 1200e-12 * 1e6, places=6)
        self.assertAlmostEqual(
            r["core_dyn_uj"] + r["core_leak_nj"] / 1e3, r["core_uj"], places=9
        )
        self.assertAlmostEqual(r["f_mhz"], 833.333, places=2)

    def test_missing_groups_are_zero(self):
        r = synth_crosscheck.arm_row("synth", 10000, {"Total": {"total": 0.001}}, 100)
        self.assertEqual(r["macro_w"], 0.0)
        self.assertEqual(r["clock_w"], 0.0)
        self.assertAlmostEqual(r["core_w"], 0.001)

    def test_render_lists_every_arm_and_published_row(self):
        rows = [
            synth_crosscheck.arm_row(
                "a", 1200, report(0.02, 0.01, 0.001, 0.0005, 0.003), 1000
            )
        ]
        md = synth_crosscheck.render(rows, 1000, 2.45)
        self.assertIn("| a |", md)
        for p in synth_crosscheck.PUBLISHED:
            self.assertIn(p["label"], md)


if __name__ == "__main__":
    unittest.main()
