"""The report must never make a partial campaign look complete."""

import json
import os
import shutil
import tempfile
import unittest

import report


def sample(design, rung, density, converged, estimate=0.664, uniform=0.2109):
    """One ladder sample, shaped the way campaign.py writes it."""
    return arm_sample(
        design,
        "t{:02d}".format(rung),
        density,
        converged,
        estimate=estimate,
        uniform=uniform,
        addon=rung / 32.0,
    )


def arm_sample(
    design,
    variant,
    density,
    converged,
    estimate=0.664,
    uniform=0.2109,
    addon=None,
    first_overflow=0.9,
    search_converged=True,
    wirelength=None,
    slack=None,
):
    record = {
        "design": design,
        "variant": variant,
        "repeat": 0,
        "wall_s": 12.0,
        "loadavg_at_start": 0.4,
        "threads": 16,
        "started_utc": "2026-09-12T10:00:00Z",
        "context": {
            "design": design,
            "uniform_density": uniform,
            "place_density": "",
            "place_density_lb_addon": "0.25",
            "command_available": 1,
        },
        "estimates": {
            "0.1": {
                "overflow": 0.1,
                "estimated_density": estimate,
                "elapsed_s": 0.4,
                "search_converged": search_converged,
            }
        },
        "gp": {
            "converged": converged,
            "final_overflow": 0.09 if converged else 0.31,
            "final_hpwl": 12345.0,
            "iterations": 40,
            "hit_max_iter": not converged,
            "diverged": False,
            "trajectory": [
                {"iter": 0, "overflow": first_overflow, "hpwl": 12345.0},
                {"iter": 40, "overflow": 0.09 if converged else 0.31, "hpwl": 12000.0},
            ],
        },
    }
    if wirelength is not None:
        record["metrics"] = {
            "globalplace__route__wirelength__estimated": wirelength,
            "globalplace__timing__setup__ws": slack,
        }
    if addon is None:
        # The ship and est arms go through PLACE_DENSITY, which ORFS does
        # not echo -- exactly like the real logs.
        record["driven_density"] = density
    else:
        record["orfs_density"] = {
            "density": density,
            "addon": addon,
            "uniform_density": uniform,
        }
    return record


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, records):
        for index, record in enumerate(records):
            path = os.path.join(self.dir, "s{}.json".format(index))
            with open(path, "w") as handle:
                json.dump(record, handle)

    def test_no_results_directory_tells_you_to_run_the_campaign(self):
        with self.assertRaises(SystemExit) as caught:
            report.load(os.path.join(self.dir, "absent"))
        self.assertIn("run the campaign first", str(caught.exception))

    def test_empty_results_render_as_not_measured(self):
        self.assertEqual(report.render([]), report.NOT_MEASURED)

    def test_bracket_is_the_pair_that_flips(self):
        self.write(
            [
                sample("gcd", 0, 0.221, False),
                sample("gcd", 8, 0.413, False),
                sample("gcd", 12, 0.510, True),
                sample("gcd", 16, 0.616, True),
            ]
        )
        rows = report.table_estimate_vs_actual(report.by_design(report.load(self.dir)))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(row["miss"], 0.413)
        self.assertAlmostEqual(row["hit"], 0.510)
        self.assertIn("(0.413, 0.510]", report.render(rows))

    def test_a_design_that_converges_at_the_bottom_says_so(self):
        self.write([sample("uart", 0, 0.221, True)])
        rows = report.table_estimate_vs_actual(report.by_design(report.load(self.dir)))
        self.assertIsNone(rows[0]["miss"])
        self.assertIn("hit at the bottom rung", report.render(rows))

    def test_a_design_that_never_converges_is_not_reported_as_bracketed(self):
        self.write([sample("jpeg", 0, 0.5, False), sample("jpeg", 31, 0.99, False)])
        rows = report.table_estimate_vs_actual(report.by_design(report.load(self.dir)))
        self.assertIsNone(rows[0]["hit"])
        self.assertIn("no rung converged", report.render(rows))

    def test_error_column_is_the_estimate_against_the_measured_hit(self):
        self.write(
            [
                sample("gcd", 8, 0.413, False),
                sample("gcd", 12, 0.510, True, estimate=0.664),
            ]
        )
        rows = report.table_estimate_vs_actual(report.by_design(report.load(self.dir)))
        self.assertIn("+0.154", report.render(rows))

    def test_arms_table_reports_the_first_iteration_overflow(self):
        self.write(
            [
                arm_sample("gcd", "ship", 0.35, True, first_overflow=0.95),
                arm_sample("gcd", "est", 0.834, True, first_overflow=0.31),
            ]
        )
        rows = report.table_arms(report.by_design(report.load(self.dir)))
        self.assertAlmostEqual(rows[0]["est_first_overflow"], 0.31)
        self.assertAlmostEqual(rows[0]["ship_density"], 0.35)
        self.assertIn("0.310", report.render_arms(rows))

    def test_arms_table_is_not_confused_by_ladder_samples(self):
        self.write([sample("gcd", 8, 0.413, False)])
        self.assertEqual(report.table_arms(report.by_design(report.load(self.dir))), [])
        self.assertEqual(report.render_arms([]), report.NOT_MEASURED)

    def test_ladder_table_ignores_the_named_arms(self):
        # `est` runs at a density of its own choosing; counting it as a
        # rung would invent a threshold nothing measured.
        self.write(
            [
                sample("gcd", 8, 0.413, False),
                arm_sample("gcd", "est", 0.834, True),
            ]
        )
        rows = report.table_estimate_vs_actual(report.by_design(report.load(self.dir)))
        self.assertIsNone(rows[0]["hit"])

    def test_a_disowned_estimate_is_called_out(self):
        # GPL-0186: gpl's search ran out of iterations and returned its
        # best guess. The table has to say so where the number is
        # quoted, or the number reads as an answer.
        self.write(
            [
                arm_sample("gcd", "est", 0.78, True, search_converged=False),
            ]
        )
        rendered = report.render_arms(
            report.table_arms(report.by_design(report.load(self.dir)))
        )
        self.assertIn("GPL-0186", rendered)

    def test_knob_table_needs_two_rungs_before_it_says_anything(self):
        self.write([sample("gcd", 8, 0.413, True)])
        self.assertEqual(
            report.table_knob_sensitivity(report.by_design(report.load(self.dir))), []
        )
        self.assertEqual(report.render_knob([]), report.NOT_MEASURED)

    def test_knob_table_reports_the_spread_over_the_ladder(self):
        self.write(
            [
                arm_sample(
                    "gcd", "t00", 0.30, True, addon=0.0, wirelength=100.0, slack=-1.0
                ),
                arm_sample(
                    "gcd", "t16", 0.60, True, addon=0.5, wirelength=110.0, slack=-2.0
                ),
            ]
        )
        rows = report.table_knob_sensitivity(report.by_design(report.load(self.dir)))
        self.assertAlmostEqual(rows[0]["wirelength_spread_pct"], 10.0)
        self.assertAlmostEqual(rows[0]["density_low"], 0.30)
        # The rung with the shortest wirelength, so the table can say
        # whether following the estimate would have landed near it.
        self.assertAlmostEqual(rows[0]["best_density"], 0.30)
        self.assertIn("10.0%", report.render_knob(rows))

    def test_declared_designs_with_no_samples_are_named(self):
        self.write([sample("gcd", 8, 0.413, True)])
        designs = report.by_design(report.load(self.dir))
        names = report.missing(designs)
        self.assertNotIn("gcd", names)
        self.assertIn("ethmac", names)
        self.assertIn(report.NOT_MEASURED, report.render_missing(names))

    def test_shipped_column_is_what_the_ship_arm_placed_at(self):
        # A design can set PLACE_DENSITY and PLACE_DENSITY_LB_ADDON both;
        # ORFS uses the addon, so the variable is not the density.
        record = arm_sample("riscv32i", "ship", 0.749, True, addon=0.10)
        record["context"]["place_density"] = "0.60"
        self.write([record])
        rows = report.table_estimate_vs_actual(report.by_design(report.load(self.dir)))
        self.assertAlmostEqual(rows[0]["shipped_density"], 0.749)

    def test_csv_carries_every_sample(self):
        self.write([sample("gcd", 8, 0.413, False), sample("gcd", 12, 0.51, True)])
        lines = report.csv(report.load(self.dir)).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("design,variant,repeat,density"))


if __name__ == "__main__":
    unittest.main()
