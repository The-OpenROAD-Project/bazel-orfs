"""The campaign must not read a log that belongs to another rung.

Everything tested here is a way the campaign could produce a plausible
number from the wrong file: a design/top mapping that has drifted from
the BUILD file, a variant that matches two directories, the .runfiles
copy of every stage log.
"""

import os
import re
import tempfile
import unittest

import campaign

BUILD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BUILD.bazel")


def build_file_designs():
    """STUDY_DESIGNS as BUILD.bazel declares it."""
    with open(BUILD_FILE) as handle:
        text = handle.read()
    body = re.search(r"STUDY_DESIGNS = \{(.*?)\n\}", text, re.DOTALL).group(1)
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', body))


class CampaignTest(unittest.TestCase):
    def test_design_tops_agree_with_the_build_file(self):
        # The BUILD file declares the arms; this dict only says where
        # their logs land. A design added to one and not the other would
        # otherwise fail as a missing log, hours into a campaign.
        self.assertEqual(campaign.DESIGN_TOPS, build_file_designs())

    def test_rung_variant_is_zero_padded(self):
        self.assertEqual(campaign.rung_variant(8), "t08")
        self.assertEqual(campaign.rung_variant(31), "t31")
        self.assertEqual(campaign.rung_variant(8, "n"), "nt08")

    def test_rung_target_names_the_declared_arm(self):
        self.assertEqual(
            campaign.rung_target("mock-alu", 12),
            "//test/estimate_density:mock-alu_t12_place",
        )

    def test_coarse_ladder_stays_inside_the_declared_rungs(self):
        self.assertTrue(all(0 <= rung < campaign.RUNG_COUNT for rung in campaign.COARSE))


class FindStageLogTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self.cwd)

    def write_log(self, *parts):
        path = os.path.join(
            "bazel-bin", "test", "estimate_density", *parts, "3_3_place_gp.log"
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("log\n")
        return path

    def test_picks_the_rung_and_ignores_the_runfiles_copy(self):
        wanted = self.write_log("logs", "asap7", "gcd", "t08")
        self.write_log("gcd_t08_place.sh.runfiles", "_main", "logs", "asap7", "gcd", "t08")
        self.write_log("logs", "asap7", "gcd", "t09")
        self.assertEqual(campaign.find_stage_log("gcd", "t08"), wanted)

    def test_another_designs_rung_is_not_a_match(self):
        self.write_log("logs", "asap7", "uart", "t08")
        with self.assertRaises(RuntimeError):
            campaign.find_stage_log("gcd", "t08")

    def test_two_candidates_is_an_error_not_a_coin_flip(self):
        self.write_log("logs", "asap7", "gcd", "t08")
        self.write_log("other", "logs", "asap7", "gcd", "t08")
        with self.assertRaises(RuntimeError):
            campaign.find_stage_log("gcd", "t08")

    def test_the_probe_control_has_its_own_variant(self):
        wanted = self.write_log("logs", "asap7", "gcd", "nt08")
        self.write_log("logs", "asap7", "gcd", "t08")
        self.assertEqual(campaign.find_stage_log("gcd", "nt08"), wanted)


if __name__ == "__main__":
    unittest.main()
