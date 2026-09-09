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
