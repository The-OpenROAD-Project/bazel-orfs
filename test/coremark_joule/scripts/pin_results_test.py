#!/usr/bin/env python3
"""pin_results' placement-seed ensemble: 2σ, and the design's own draw stays the point."""

import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pin_results  # noqa: E402


def _write(d, name, **fields):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        json.dump(fields, f)
    return path


class SeedSamplesTest(unittest.TestCase):
    def test_two_sigma(self):
        self.assertEqual(pin_results.two_sigma([1.0]), 0.0)
        # sample standard deviation of {1, 3} is sqrt(2)
        self.assertAlmostEqual(pin_results.two_sigma([1.0, 3.0]), 2.0 * math.sqrt(2.0))

    def test_attach_samples_keeps_the_design_draw_as_the_point(self):
        point = {
            "core": "ibex",
            "isa": "rv32imc",
            "power_w": 0.020,
            "coremark_per_joule": 100000.0,
        }
        with tempfile.TemporaryDirectory() as d:
            paths = [
                _write(
                    d,
                    "s0.json",
                    core="ibex",
                    isa="rv32imc",
                    power_w=0.021,
                    coremark_per_joule=95000.0,
                ),
                _write(
                    d,
                    "s1.json",
                    core="ibex",
                    isa="rv32imc",
                    power_w=0.019,
                    coremark_per_joule=105000.0,
                ),
            ]
            [out] = pin_results.attach_samples([dict(point)], paths)
        self.assertEqual(out["power_w"], 0.020)
        self.assertEqual(out["seeds"], 3)
        self.assertEqual(len(out["seed_samples"]), 3)
        self.assertAlmostEqual(
            out["power_2sigma_w"], pin_results.two_sigma([0.020, 0.021, 0.019])
        )
        self.assertAlmostEqual(
            out["coremark_per_joule_2sigma"],
            pin_results.two_sigma([100000.0, 95000.0, 105000.0]),
        )

    def test_point_without_samples_is_left_alone(self):
        [out] = pin_results.attach_samples(
            [
                {
                    "core": "serv",
                    "isa": "rv32i",
                    "power_w": 1.0,
                    "coremark_per_joule": 1.0,
                }
            ],
            [],
        )
        self.assertNotIn("seeds", out)
        self.assertNotIn("seed_samples", out)

    def test_sample_for_unknown_core_is_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(
                d,
                "s.json",
                core="nope",
                isa="rv32i",
                power_w=1.0,
                coremark_per_joule=1.0,
            )
            with self.assertRaises(SystemExit):
                pin_results.attach_samples(
                    [
                        {
                            "core": "ibex",
                            "isa": "rv32imc",
                            "power_w": 1.0,
                            "coremark_per_joule": 1.0,
                        }
                    ],
                    [path],
                )


if __name__ == "__main__":
    unittest.main()
