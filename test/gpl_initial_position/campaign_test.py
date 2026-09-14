"""Unit tests for the campaign runner's bookkeeping."""

import os
import shutil
import tempfile
import unittest

import campaign


class SeedParsingTest(unittest.TestCase):
    def test_range(self):
        self.assertEqual(campaign.parse_seeds("1-4"), [1, 2, 3, 4])

    def test_list(self):
        self.assertEqual(campaign.parse_seeds("1,2,5"), [1, 2, 5])

    def test_mixed_and_whitespace(self):
        self.assertEqual(campaign.parse_seeds(" 1-3 , 9 "), [1, 2, 3, 9])

    def test_empty_parts_are_ignored(self):
        self.assertEqual(campaign.parse_seeds("1,,2"), [1, 2])


class ArmsTest(unittest.TestCase):
    def test_the_baseline_passes_no_mode(self):
        # The baseline must be ORFS exactly as it stands, or the study
        # is comparing two changes rather than one.
        self.assertEqual(campaign.ARMS[campaign.BASELINE_ARM], [])

    def test_every_other_arm_names_a_mode(self):
        for name, knobs in campaign.ARMS.items():
            if name == campaign.BASELINE_ARM:
                continue
            self.assertEqual(len(knobs), 1, name)
            self.assertTrue(knobs[0].startswith("-initial_position_mode "), name)

    def test_the_mode_matches_the_arm_name(self):
        # The witness read back out of the log is the arm name, so these
        # cannot be allowed to drift apart.
        for name, knobs in campaign.ARMS.items():
            if name == campaign.BASELINE_ARM:
                continue
            self.assertEqual(knobs[0].split()[-1], name)

    def test_center_is_a_distinct_arm_from_shipped(self):
        # ORFS forces the core center at 3_3 but not at 3_1, so a single
        # centre policy applied at both is a different flow, and the gap
        # between the two is one of the things being measured.
        self.assertIn("center", campaign.ARMS)
        self.assertNotEqual(campaign.ARMS["center"], campaign.ARMS["shipped"])

    def test_stochastic_arms_are_all_real_arms(self):
        for name in campaign.STOCHASTIC_ARMS:
            self.assertIn(name, campaign.ARMS)


class VariantPreparationTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.results = os.path.join(self.root, "results", "asap7", "gcd")
        self.base = os.path.join(self.results, "base")
        os.makedirs(self.base)
        for name in [
            "2_floorplan.odb",
            "2_floorplan.sdc",
            "3_place.short.mk",
            "3_1_place_gp_skip_io.odb",
            "3_3_place_gp.odb",
            "3_place.odb",
            "5_1_grt.odb",
        ]:
            with open(os.path.join(self.base, name), "w") as handle:
                handle.write(name)

    def test_the_frozen_prefix_is_copied_and_the_tail_is_not(self):
        results_dir, _ = campaign.prepare_variant(self.root, "asap7", "gcd", "v1")
        present = sorted(os.listdir(results_dir))
        self.assertEqual(
            present, ["2_floorplan.odb", "2_floorplan.sdc", "3_place.short.mk"]
        )

    def test_an_existing_variant_is_removed_not_updated(self):
        # A leftover output would let make declare the stage already
        # built, and the sample would be harvested from the previous run
        # under a new name.
        results_dir, _ = campaign.prepare_variant(self.root, "asap7", "gcd", "v1")
        stale = os.path.join(results_dir, "3_3_place_gp.odb")
        with open(stale, "w") as handle:
            handle.write("stale")
        campaign.prepare_variant(self.root, "asap7", "gcd", "v1")
        self.assertFalse(os.path.exists(stale))

    def test_logs_dir_is_returned_alongside(self):
        _, logs_dir = campaign.prepare_variant(self.root, "asap7", "gcd", "v1")
        self.assertTrue(logs_dir.endswith(os.path.join("logs", "asap7", "gcd", "v1")))


class ClockTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def _write(self, text):
        with open(os.path.join(self.root, "2_floorplan.sdc"), "w") as handle:
            handle.write(text)

    def test_reads_the_literal_period(self):
        self._write("create_clock -name core_clock -period 310.0 [get_ports clk]\n")
        self.assertEqual(campaign.clock_from_frozen_sdc(self.root), 310.0)

    def test_missing_sdc_is_none_not_zero(self):
        self.assertIsNone(campaign.clock_from_frozen_sdc(self.root))

    def test_a_non_literal_period_is_none(self):
        # An SDC that computes its period cannot be read this way, and a
        # None propagates into the record as a missing timing endpoint
        # rather than as a clock of zero.
        self._write("create_clock -period $period [get_ports clk]\n")
        self.assertIsNone(campaign.clock_from_frozen_sdc(self.root))


if __name__ == "__main__":
    unittest.main()
