#!/usr/bin/env python3
"""pin_results: the placement-seed ensemble (2σ, the design's own draw stays the point) and the literature table (one schema, every derived number its own formula)."""

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
                    "point_ibex_rv32imc_seed11.json",
                    core="ibex",
                    isa="rv32imc",
                    power_w=0.021,
                    coremark_per_joule=95000.0,
                ),
                _write(
                    d,
                    "point_ibex_rv32imc_seed12.json",
                    core="ibex",
                    isa="rv32imc",
                    power_w=0.019,
                    coremark_per_joule=105000.0,
                ),
            ]
            [out] = pin_results.attach_samples([dict(point)], paths)
        self.assertEqual(out["power_w"], 0.020)
        self.assertEqual(out["seeds"], 3)
        # The design's own draw is labelled as such; the rest by their seed.
        self.assertEqual([x["seed"] for x in out["seed_samples"]], ["own", "11", "12"])
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
def row(**kw):
    base = dict(
        name="X",
        source="paper",
        cite="[1]",
        locator="Table 1",
        process="22 nm",
        boundary="core",
        confidence="stated",
    )
    base.update(kw)
    return pin_results._row({}, **base)


class LiteratureSchemaTest(unittest.TestCase):
    def test_pinned_table_is_consistent(self):
        self.assertEqual(pin_results.check_literature(pin_results.LITERATURE), [])

    def test_every_row_has_every_field(self):
        for r in pin_results.LITERATURE:
            for k in pin_results.LITERATURE_FIELDS:
                self.assertIn(k, r, r["name"])

    def test_missing_locator_is_a_problem(self):
        problems = pin_results.check_literature([row(locator="")])
        self.assertTrue(any("locator" in p for p in problems))

    def test_confidence_is_one_of_three(self):
        problems = pin_results.check_literature([row(confidence="probably")])
        self.assertTrue(any("confidence" in p for p in problems))

    def test_fmax_needs_its_kind(self):
        problems = pin_results.check_literature([row(fmax_mhz=1000.0)])
        self.assertTrue(any("fmax_kind" in p for p in problems))
        problems = pin_results.check_literature(
            [row(fmax_mhz=1000.0, fmax_kind="synthesis")]
        )
        self.assertEqual(problems, [])

    def test_derived_coremark_per_joule_must_match(self):
        good = row(
            coremark_per_mhz=2.0,
            frequency_mhz=1000.0,
            power_w=0.1,
            coremark_per_joule=20000.0,
        )
        self.assertEqual(pin_results.check_literature([good]), [])
        bad = row(
            coremark_per_mhz=2.0,
            frequency_mhz=1000.0,
            power_w=0.1,
            coremark_per_joule=21000.0,
        )
        problems = pin_results.check_literature([bad])
        self.assertTrue(any("CoreMark/Joule" in p for p in problems))

    def test_duplicate_names_are_a_problem(self):
        problems = pin_results.check_literature([row(), row()])
        self.assertTrue(any("duplicate" in p for p in problems))


class PhysicalTest(unittest.TestCase):
    def test_probe_output_is_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.txt")
            with open(path, "w") as f:
                f.write(
                    "stage 5_1_grt\n"
                    "design cmj_ibex\n"
                    "stdcell_count 12345\n"
                    "stdcell_um2 1234.500\n"
                    "nand2_um2 0.058320\n"
                    "kge 21.2\n"
                    "period_ps 1200\n"
                    "wns_reg2reg_ps none\n"
                    "macro fakeram7_256x34 2 1234.5000\n"
                )
            phys = pin_results.load_physical(["ibex:" + path])
        p = phys["ibex"]
        self.assertEqual(p["stdcell_count"], 12345)
        self.assertAlmostEqual(p["stdcell_um2"], 1234.5)
        self.assertEqual(p["wns_reg2reg_ps"], "none")
        self.assertEqual(
            p["macros"], [{"master": "fakeram7_256x34", "count": 2, "um2": 1234.5}]
        )

    def test_table_renders_measured_then_literature(self):
        points = [
            {
                "core": "ibex",
                "isa": "rv32imc",
                "frequency_mhz": 833.333,
                "coremark_per_mhz": 2.4543,
                "coremark_per_joule": 99283.9,
                "physical": {"kge": 21.2},
            }
        ]
        table = pin_results.literature_table(points, pin_results.LITERATURE)
        lines = table.splitlines()
        self.assertTrue(
            lines[2].startswith("| ibex (rv32imc) | this study, grt | asap7 | 21.2 |")
        )
        self.assertEqual(len(lines), 2 + len(points) + len(pin_results.LITERATURE))
        self.assertIn(
            "| CVA6 | [5] | GF 22 FDX | 730.0 | 1083 (signoff) | 2.19 | 28205 |", table
        )

    def test_missing_physical_renders_as_dash(self):
        points = [{"core": "serv", "isa": "rv32i", "frequency_mhz": 1428.571}]
        table = pin_results.literature_table(points, [])
        self.assertIn(
            "| serv (rv32i) | this study, grt | asap7 | -- | 1429 (SDC) | -- | -- |",
            table,
        )


if __name__ == "__main__":
    unittest.main()
