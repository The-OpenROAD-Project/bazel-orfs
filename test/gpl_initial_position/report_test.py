"""Unit tests for the report generator's discovery and honesty rules."""

import json
import os
import shutil
import tempfile
import unittest

import report


def sample(design="gcd", arm="shipped", seed=1, **fields):
    record = {
        "platform": "asap7",
        "design": design,
        "arm": arm,
        "seed": seed,
        "arm_witnessed": "shipped" if arm == "shipped" else arm,
    }
    record.update(fields)
    return record


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def write(self, name, record):
        with open(os.path.join(self.root, name), "w") as handle:
            json.dump(record, handle)

    def test_an_empty_directory_says_run_the_campaign(self):
        with self.assertRaises(SystemExit) as caught:
            report.load(self.root)
        self.assertIn("run the campaign first", str(caught.exception))

    def test_a_missing_directory_says_the_same(self):
        with self.assertRaises(SystemExit):
            report.load(os.path.join(self.root, "nope"))

    def test_a_sample_whose_log_disagrees_is_dropped(self):
        # The failure this guards against: a mode flag that never reached
        # the command line produces a normal run whose numbers match the
        # default's exactly, which would read as "this arm does nothing".
        self.write("a.json", sample(arm="spread", arm_witnessed="shipped"))
        samples, dropped = report.load(self.root)
        self.assertEqual(samples, [])
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0][1], "spread")
        self.assertEqual(dropped[0][3], "shipped")

    def test_the_baseline_is_witnessed_as_shipped(self):
        self.write("a.json", sample(arm="shipped", arm_witnessed="shipped"))
        samples, dropped = report.load(self.root)
        self.assertEqual(len(samples), 1)
        self.assertEqual(dropped, [])

    def test_a_matching_mode_arm_is_kept(self):
        self.write("a.json", sample(arm="anchored", arm_witnessed="anchored"))
        samples, _ = report.load(self.root)
        self.assertEqual(len(samples), 1)


class GroupingTest(unittest.TestCase):
    def test_none_endpoints_are_skipped_not_zeroed(self):
        samples = [
            sample(seed=1, gp_hpwl_final=100.0),
            sample(seed=2, gp_hpwl_final=None),
        ]
        grouped = report.by_design_arm(samples, "gp_hpwl_final")
        self.assertEqual(grouped["asap7/gcd"]["shipped"], [100.0])


class SectionTest(unittest.TestCase):
    def test_an_endpoint_with_no_data_says_not_yet_measured(self):
        text = report.endpoint_section([sample()], "wirelength", "wirelength", True)
        self.assertIn("Not yet measured", text)

    def test_initial_place_with_no_trajectory_says_not_yet_measured(self):
        self.assertIn("Not yet measured", report.initial_place_table([sample()]))

    def test_a_single_sample_arm_cannot_produce_a_verdict(self):
        # One run per arm has no spread, so nothing may resolve. The
        # section must still render, saying so.
        samples = [
            sample(arm="shipped", seed=1, gp_hpwl_final=100.0),
            sample(arm="spread", seed=1, gp_hpwl_final=500.0),
        ]
        text = report.endpoint_section(samples, "gp_hpwl_final", "HPWL", True)
        self.assertIn("nothing can be compared yet", text)

    def test_a_real_comparison_renders_a_verdict_table(self):
        samples = [
            sample(arm="shipped", seed=s, gp_hpwl_final=100.0 + s) for s in range(1, 5)
        ] + [
            sample(arm="spread", seed=s, gp_hpwl_final=900.0 + s) for s in range(1, 5)
        ]
        text = report.endpoint_section(samples, "gp_hpwl_final", "HPWL", True)
        self.assertIn("Pooled verdict", text)
        self.assertIn("resolved", text)

    def test_position_sources_needs_a_baseline_sample(self):
        text = report.position_source_table(
            [sample(arm="spread", arm_witnessed="spread")]
        )
        self.assertIn("Not yet measured", text)


class SummaryTest(unittest.TestCase):
    def test_no_data_says_not_yet_measured(self):
        self.assertIn("Not yet measured", report.summary_table([]))

    def test_one_row_per_arm_with_the_winning_design_count(self):
        samples = [
            sample(arm="shipped", seed=s, gp_hpwl_final=100.0 + s) for s in range(1, 5)
        ] + [
            sample(arm="spread", seed=s, gp_hpwl_final=900.0 + s) for s in range(1, 5)
        ]
        text = report.summary_table(samples)
        self.assertIn("| spread |", text)
        self.assertIn("1/1", text)

    def test_a_single_design_is_reported_as_underpowered(self):
        # The cell must not read "worse" when one design cannot support
        # any verdict; this is the same rule stats.verdict enforces, and
        # the summary is the table a reader skims first.
        samples = [
            sample(arm="shipped", seed=s, gp_hpwl_final=100.0 + s) for s in range(1, 5)
        ] + [
            sample(arm="spread", seed=s, gp_hpwl_final=900.0 + s) for s in range(1, 5)
        ]
        self.assertIn("underpowered", report.summary_table(samples))


class NoiseFloorTest(unittest.TestCase):
    def test_no_baseline_says_not_yet_measured(self):
        self.assertIn("Not yet measured", report.noise_floor_table([]))

    def test_reports_two_sigma_of_the_baseline_arm(self):
        samples = [
            sample(arm="shipped", seed=s, gp_hpwl_final=v)
            for s, v in enumerate([100.0, 102.0, 98.0, 100.0], start=1)
        ]
        text = report.noise_floor_table(samples)
        self.assertIn("asap7/gcd", text)
        # 2 sigma of that ensemble is 2*1.6330 = 3.266, i.e. 3.27% of 100.
        self.assertIn("3.266", text)
        self.assertIn("3.27", text)


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def test_a_partial_campaign_never_reads_as_a_complete_one(self):
        with open(os.path.join(self.root, "a.json"), "w") as handle:
            json.dump(sample(gp_hpwl_final=100.0), handle)
        text = report.build(self.root)
        # Place-stage data present, global-route data absent: the timing
        # and congestion sections must say so out loud.
        self.assertIn("Not yet measured", text)
        self.assertIn("min_period", text)


if __name__ == "__main__":
    unittest.main()
