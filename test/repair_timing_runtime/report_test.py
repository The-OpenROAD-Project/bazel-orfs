#!/usr/bin/env python3
"""Tests for the report generator: statistics, discovery, honesty."""

import json
import os
import tempfile
import unittest

import report


def call(kind="setup_hold", setup_s=100.0, hold_s=1.0, iters=1000, last=200,
         t_last=250.0, t_final=1050.0, wns_end=-50.0, start_s=50.0):
    return {
        "kind": kind,
        "command": "repair_timing",
        "setup_s": setup_s,
        "hold_s": hold_s,
        "repair_design_s": None,
        "iterations": iters,
        "final_iter": iters,
        "last_improving_iter": last,
        "t_last_improvement_s": t_last,
        "t_final_s": t_final,
        "start_s": start_s,
        "wns_start": -100.0,
        "wns_end": wns_end,
        "endpoints": 500,
        "unrepaired": True,
        "witness": {},
    }


def record(design, stage, arm, repeat, calls, wall=200.0, sha="abc"):
    step = {"cts": "4_1_cts", "grt": "5_1_grt"}[stage]
    return {
        "design": design,
        "stage": stage,
        "arm": arm,
        "repeat": repeat,
        "substeps": {
            step: {
                "wall_s": wall,
                "result_sha1": sha,
                "repair": calls,
                "repair_rows": [[
                    {"iter": 0, "marker": "*", "wns": -100.0, "t_s": 50.0},
                    {"iter": 10, "marker": "*", "wns": -60.0, "t_s": 300.0},
                    {"iter": "final", "marker": "", "wns": -50.0, "t_s": 1050.0},
                ]],
            }
        },
    }


class Statistics(unittest.TestCase):
    def test_two_sigma_of_one_run_is_zero(self):
        """Which is honest: one run has no measured spread."""
        self.assertEqual(report.two_sigma([31.1]), 0.0)

    def test_resolution_shrinks_with_repeats(self):
        self.assertAlmostEqual(report.resolution(2.0, 2), 2.0)
        self.assertLess(report.resolution(2.0, 8), report.resolution(2.0, 2))


class Discovery(unittest.TestCase):
    def test_missing_results_directory_says_run_the_campaign(self):
        with self.assertRaises(SystemExit) as ctx:
            report.load_results(os.path.join(tempfile.mkdtemp(), "nope"))
        self.assertIn("run the campaign first", str(ctx.exception))

    def test_sections_without_data_say_not_yet_measured(self):
        """A partial study must not read as a complete one."""
        text = report.render([record("aes", "cts", "base", 1, [call()])])
        self.assertIn("## Arms\n", text)
        self.assertIn("Not yet measured", text)
        # The census, which does have data, renders a row.
        self.assertIn("| aes | cts | setup+hold |", text)


class Census(unittest.TestCase):
    def test_dead_share_uses_stamps_when_present(self):
        """800 of 1000 elapsed seconds bought nothing."""
        row = report.census_rows([record("aes", "cts", "base", 1, [call()])])[0]
        self.assertAlmostEqual(row["dead_share"], 0.8)
        self.assertAlmostEqual(row["share"], 101.0 / 200.0)

    def test_dead_share_falls_back_to_iterations(self):
        row = report.census_rows(
            [record("aes", "cts", "base", 1, [call(t_last=None, t_final=None)])]
        )[0]
        self.assertAlmostEqual(row["dead_share"], 0.8)

    def test_only_the_first_repeat_of_the_census_arm(self):
        rows = report.census_rows([
            record("aes", "cts", "base", 2, [call(setup_s=999.0)]),
            record("aes", "cts", "base", 1, [call(setup_s=100.0)]),
            record("aes", "cts", "tns20", 1, [call(setup_s=5.0)]),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["setup_s"], 100.0)


class Attribution(unittest.TestCase):
    def test_profiled_call_becomes_a_row_with_shares(self):
        c = call(setup_s=100.0)
        c["profile"] = {
            "LEGACY*": {"passes": 10, "sta_s": 50.0, "progress_s": 30.0, "journal_s": 5.0,
                        "repair_path_s": 5.0, "parasitics_s": 0.0, "collect_s": 0.0,
                        "tns_s": 0.0, "accepted": 3, "attempts": 9},
            "LAST_GASP+": {"passes": 12, "sta_s": 55.0, "progress_s": 30.0, "journal_s": 5.0,
                           "repair_path_s": 5.0, "parasitics_s": 0.0, "collect_s": 0.0,
                           "tns_s": 0.0, "accepted": 3, "attempts": 9},
        }
        rows = report.attribution_rows([record("aes", "cts", "base-prof", 1, [c])])
        self.assertEqual(rows[0]["passes"], 12)
        self.assertAlmostEqual(rows[0]["other_s"], 5.0)
        text = report.attribution_table(rows)
        self.assertIn("| 55.0 (55%) | 30.0 (30%) |", text)
        self.assertIn("| 3 / 9 |", text)

    def test_unprofiled_results_say_not_yet_measured(self):
        text = report.attribution_table(report.attribution_rows(
            [record("aes", "cts", "base", 1, [call()])]))
        self.assertTrue(text.startswith("Not yet measured"))


class Arms(unittest.TestCase):
    def records(self):
        return [
            record("aes", "cts", "base", 1, [call(setup_s=100.0)]),
            record("aes", "cts", "base", 2, [call(setup_s=104.0)]),
            record("aes", "cts", "tns20", 1, [call(setup_s=60.0, wns_end=-55.0)], sha="def"),
            record("aes", "cts", "tns20", 2, [call(setup_s=62.0, wns_end=-55.0)], sha="def"),
            record("aes", "cts", "nogasp", 1, [call(setup_s=101.0)]),
            record("aes", "cts", "nogasp", 2, [call(setup_s=102.0)]),
        ]

    def test_a_real_win_resolves_and_costs_are_shown(self):
        text = report.arms_table(self.records(), "aes", "cts")
        self.assertIn("| tns20 | 61.0, 63.0 | 62.0 | -41.0 |", text)
        self.assertIn("| faster | -5.0 | no |", text)

    def test_inside_the_resolution_does_not_resolve(self):
        """2σ of base is 4.0 and k=2, so ±4.0 does not resolve."""
        text = report.arms_table(self.records(), "aes", "cts")
        self.assertIn("| nogasp | 102.0, 103.0 | 102.5 | -0.5 |", text)
        self.assertIn("did not resolve", text)
        self.assertIn("| 0.0 | yes |", text)

    def test_profiled_base_is_the_control_when_present(self):
        recs = self.records() + [
            record("aes", "cts", "base-prof", 1, [call(setup_s=110.0)]),
            record("aes", "cts", "base-prof", 2, [call(setup_s=112.0)]),
        ]
        text = report.arms_table(recs, "aes", "cts")
        self.assertIn("| base-prof | 111.0, 113.0 | 112.0 | – |", text)
        self.assertIn("| base | 101.0, 105.0 | 103.0 | -9.0 |", text)

    def test_base_alone_is_not_an_arms_table(self):
        text = report.arms_table(self.records()[:2], "aes", "cts")
        self.assertTrue(text.startswith("Not yet measured"))


class Csv(unittest.TestCase):
    def test_one_row_per_repair_call_with_header(self):
        text = report.samples_csv([record("aes", "cts", "base", 1, [call()])])
        lines = text.strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("design,stage,substep,arm,repeat,call,setup_s"))
        self.assertTrue(lines[1].startswith("aes,cts,4_1_cts,base,1,setup_hold,100.0,1.0,1000"))


class Chart(unittest.TestCase):
    def test_trajectory_is_a_mermaid_block_in_seconds(self):
        text = report.trajectory_chart(record("aes", "cts", "base", 1, [call()]), "4_1_cts")
        self.assertTrue(text.startswith("```mermaid\nxychart-beta"))
        self.assertIn('x-axis "elapsed s" [0, 250]', text)
        self.assertIn("line [-100.0, -60.0]", text)


if __name__ == "__main__":
    unittest.main()
