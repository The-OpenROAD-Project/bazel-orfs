#!/usr/bin/env python3
"""Tests for the campaign runner's assumptions about the flow it drives."""

import ast
import os
import re
import unittest

import campaign

STAGES_BZL = os.path.join(
    os.environ.get("TEST_SRCDIR", ""),
    os.environ.get("TEST_WORKSPACE", ""),
    "private/stages.bzl",
)


def stage_substeps_from_bzl(path):
    """The STAGE_SUBSTEPS dict literal out of private/stages.bzl.

    A plain Starlark dict of string lists is also a Python literal, so
    it can be read rather than reimplemented.
    """
    with open(path) as handle:
        text = handle.read()
    match = re.search(r"^STAGE_SUBSTEPS = (\{.*?^\})", text, re.M | re.S)
    if not match:
        raise AssertionError("STAGE_SUBSTEPS not found in {}".format(path))
    return ast.literal_eval(match.group(1))


class StageSubsteps(unittest.TestCase):
    def test_matches_the_single_source_of_truth(self):
        """The runner's copy may not drift from private/stages.bzl.

        Substep names decide which logs are read and which `do-` targets
        run. If ORFS renames or splits one and this copy lags, the
        campaign measures a stage that no longer exists -- or silently
        stops measuring part of one.
        """
        upstream = stage_substeps_from_bzl(STAGES_BZL)
        for stage, substeps in campaign.STAGE_SUBSTEPS.items():
            self.assertIn(stage, upstream, "stage {} is not a flow stage".format(stage))
            self.assertEqual(
                substeps,
                upstream[stage],
                "substeps for {} drifted from private/stages.bzl".format(stage),
            )

    def test_synth_is_deliberately_absent(self):
        """Synth is Yosys, which takes no -threads, so it is not measurable."""
        self.assertNotIn("synth", campaign.STAGE_SUBSTEPS)


class HostTopology(unittest.TestCase):
    def test_physical_cores_never_exceeds_hardware_threads(self):
        cores = campaign.physical_cores()
        if cores is None:
            self.skipTest("/proc/cpuinfo exposes no core topology here")
        self.assertLessEqual(cores, campaign.hardware_threads())
        self.assertGreaterEqual(cores, 1)

    def test_provenance_records_what_could_move_a_timing_number(self):
        prov = campaign.provenance()
        for key in ("hardware_threads", "physical_cores", "kernel", "governor"):
            self.assertIn(key, prov)


class WaitForIdle(unittest.TestCase):
    def test_returns_immediately_when_already_idle(self):
        """The common case must not sleep."""
        got = campaign.wait_for_idle(threshold=1e9, timeout_s=0)
        self.assertLess(got, 1e9)

    def test_gives_up_rather_than_measuring_a_busy_machine(self):
        """A machine that never settles is not silently measured."""
        with self.assertRaises(SystemExit):
            campaign.wait_for_idle(threshold=-1.0, timeout_s=0, poll_s=0)


class ResultPaths(unittest.TestCase):
    def test_arms_do_not_collide(self):
        """Every arm needs its own file, or resume would skip real work."""
        names = {
            campaign.result_path("d", "aes", stage, threads, pin, repeat)
            for stage in ("place", "route")
            for threads in (16, 32)
            for pin in (False, True)
            for repeat in (1, 2, 3)
        }
        self.assertEqual(len(names), 2 * 2 * 2 * 3)

    def test_pinning_is_visible_in_the_name(self):
        self.assertNotEqual(
            campaign.result_path("d", "aes", "route", 16, False, 1),
            campaign.result_path("d", "aes", "route", 16, True, 1),
        )


if __name__ == "__main__":
    unittest.main()


class Designs(unittest.TestCase):
    """The design set spans platforms, so the key has to say which."""

    def test_every_key_is_prefixed_with_its_platform(self):
        # The key is the label every table, file name and CSV row uses.
        # Two designs called `gcd` on different PDKs would collide in
        # the results directory and be averaged together in the report.
        for name, target in campaign.DESIGNS.items():
            platform = re.search(r"/flow/designs/([^/]+)/", target).group(1)
            self.assertTrue(
                name.startswith(platform.replace("-", "_") + "_"),
                "{} is a {} design but its key does not say so".format(name, platform),
            )

    def test_keys_are_unique_per_target(self):
        self.assertEqual(len(set(campaign.DESIGNS.values())), len(campaign.DESIGNS))

    def test_the_three_platforms_bazel_orfs_970_asks_for_are_present(self):
        platforms = {
            re.search(r"/flow/designs/([^/]+)/", t).group(1)
            for t in campaign.DESIGNS.values()
        }
        self.assertEqual(platforms, {"asap7", "sky130hd", "nangate45"})


class ArmCeiling(unittest.TestCase):
    """An arm above the ceiling is a duplicate, not a measurement."""

    def test_an_arm_above_the_hosts_thread_count_is_refused(self):
        ceiling = campaign.hardware_threads()
        with self.assertRaises(SystemExit) as caught:
            campaign.check_arms([1, ceiling, ceiling + 1], pin=False)
        # The message has to name the clamp, because the symptom
        # otherwise looks like a ladder that saturated.
        self.assertIn(str(ceiling + 1), str(caught.exception))
        self.assertIn("clamp", str(caught.exception))

    def test_arms_at_or_below_the_ceiling_are_accepted(self):
        self.assertIsNone(
            campaign.check_arms([1, campaign.hardware_threads()], pin=False)
        )

    def test_zero_threads_is_not_an_arm(self):
        with self.assertRaises(SystemExit):
            campaign.check_arms([0], pin=False)

    def test_pinning_lowers_the_ceiling_to_the_core_count(self):
        # hardware_concurrency reports the affinity mask, so a pinned
        # process cannot install more threads than the cores it is
        # pinned to -- and #968's pinned arms asked for the hardware
        # thread count.
        cores = campaign.physical_cores()
        if not cores or cores >= campaign.hardware_threads():
            self.skipTest("host exposes no SMT topology to lower the ceiling")
        self.assertEqual(campaign.arm_ceiling(pin=True), cores)
        with self.assertRaises(SystemExit):
            campaign.check_arms([campaign.hardware_threads()], pin=True)
