"""The campaign's file handling, which is where a silent wrong answer lives.

Nothing here runs a flow. What it pins is the bookkeeping around one:
which directory a sample writes to, what is copied into it, and what is
deliberately not -- because every failure mode in that list produces a
plausible number rather than an error.
"""

import os
import tempfile
import unittest

import campaign


def make_tree(root, platform="asap7", design="aes", results="aes_cipher_top"):
    """A deployed tree, reduced to the parts campaign.py looks at."""
    design_root = os.path.join(root, "+orfs_repositories+orfs", "flow", "designs",
                               platform, design)
    base = os.path.join(design_root, "results", platform, results, "base")
    os.makedirs(base)
    os.makedirs(os.path.join(design_root, "logs", platform, results))
    for name, text in [
        ("2_floorplan.odb", "odb"),
        ("2_floorplan.sdc", "create_clock -name core_clock -period 380.0000 [get_ports clk]\n"
                            "create_clock -name vclk -period 380.0000\n"),
        ("1_synth.args.json", "{}"),
        ("3_place.short.mk", "export DESIGN_NAME?=x\n"),
        # Outputs of the tail: these must NOT be carried into a variant.
        ("3_3_place_gp.odb", "stale"),
        ("5_1_grt.odb", "stale"),
        ("3_place.odb", "stale"),
        ("route.guide", "stale"),
    ]:
        with open(os.path.join(base, name), "w") as handle:
            handle.write(text)
    return design_root


class ResultsName(unittest.TestCase):
    def test_detects_the_design_name_not_the_directory(self):
        with tempfile.TemporaryDirectory() as root:
            design_root = make_tree(root)
            self.assertEqual(campaign.results_name(design_root, "asap7"), "aes_cipher_top")


class PrepareVariant(unittest.TestCase):
    def test_copies_the_frozen_prefix_and_no_tail_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            design_root = make_tree(root)
            results, _ = campaign.prepare_variant(
                design_root, "asap7", "aes_cipher_top", "base_s1"
            )
            present = sorted(os.listdir(results))
            self.assertIn("2_floorplan.odb", present)
            self.assertIn("2_floorplan.sdc", present)
            self.assertIn("3_place.short.mk", present)
            for stale in ("3_3_place_gp.odb", "5_1_grt.odb", "3_place.odb", "route.guide"):
                self.assertNotIn(stale, present)

    def test_a_rerun_starts_from_an_empty_directory(self):
        # The trap: leaving a previous run's outputs behind lets make
        # decide the stage is already built, and the sample is harvested
        # from the old run under a new name.
        with tempfile.TemporaryDirectory() as root:
            design_root = make_tree(root)
            results, _ = campaign.prepare_variant(
                design_root, "asap7", "aes_cipher_top", "base_s1"
            )
            with open(os.path.join(results, "5_1_grt.odb"), "w") as handle:
                handle.write("from the previous run")
            results, _ = campaign.prepare_variant(
                design_root, "asap7", "aes_cipher_top", "base_s1"
            )
            self.assertNotIn("5_1_grt.odb", os.listdir(results))


class Clock(unittest.TestCase):
    def test_period_comes_from_the_frozen_sdc(self):
        with tempfile.TemporaryDirectory() as root:
            design_root = make_tree(root)
            results, _ = campaign.prepare_variant(
                design_root, "asap7", "aes_cipher_top", "base_s1"
            )
            period, source = campaign.clock_from_frozen_sdc(results, design_root)
            self.assertEqual(period, 380.0)
            self.assertEqual(source, "2_floorplan.sdc")

    def test_retighten_rewrites_every_clock(self):
        with tempfile.TemporaryDirectory() as root:
            design_root = make_tree(root)
            results, _ = campaign.prepare_variant(
                design_root, "asap7", "aes_cipher_top", "clk300_s1"
            )
            self.assertEqual(campaign.retighten_sdc(results, 300.0), 2)
            period, _ = campaign.clock_from_frozen_sdc(results, design_root)
            self.assertEqual(period, 300.0)

    def test_retighten_refuses_when_there_is_no_sdc(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(SystemExit):
                campaign.retighten_sdc(root, 300.0)


if __name__ == "__main__":
    unittest.main()
