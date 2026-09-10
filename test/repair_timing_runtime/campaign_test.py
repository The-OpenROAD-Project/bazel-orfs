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
        """Synth is Yosys; repair_timing never runs there."""
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


class NoNeighbour(unittest.TestCase):
    def test_returns_when_nothing_matches(self):
        """The common case must not sleep."""
        self.assertEqual(campaign.other_openroad_pids("no-such-process-zz9"), [])
        campaign.wait_for_no_openroad(timeout_s=0, poll_s=0) if not campaign.other_openroad_pids() else None


class ResultPaths(unittest.TestCase):
    def test_arms_do_not_collide(self):
        """Every arm needs its own file, or resume would skip real work."""
        names = {
            campaign.result_path("d", "aes", stage, arm, repeat)
            for stage in ("cts", "grt")
            for arm in campaign.ARMS
            for repeat in (1, 2, 3)
        }
        self.assertEqual(len(names), 2 * len(campaign.ARMS) * 3)

    def test_a_patched_binary_is_visible_in_the_name(self):
        self.assertNotEqual(
            campaign.result_path("d", "aes", "cts", "base", 1),
            campaign.result_path("d", "aes", "cts", "base-p0066", 1),
        )


class Witness(unittest.TestCase):
    """The echoed repair_timing line must agree with the arm."""

    def summary(self, **args):
        return [{"kind": "setup_hold", "witness": dict(args)}]

    def test_agreeing_value_passes(self):
        campaign.check_witness(
            "4_1_cts",
            self.summary(repair_tns="20", verbose=True),
            {"TNS_END_PERCENT": "20"},
        )

    def test_disagreeing_value_is_refused(self):
        """A sample for the wrong knob is worse than a missing one."""
        with self.assertRaises(SystemExit):
            campaign.check_witness(
                "4_1_cts",
                self.summary(repair_tns="100", verbose=True),
                {"TNS_END_PERCENT": "20"},
            )

    def test_flag_must_be_present_when_asked(self):
        with self.assertRaises(SystemExit):
            campaign.check_witness(
                "4_1_cts", self.summary(repair_tns="100"), {"SKIP_LAST_GASP": "1"}
            )
        campaign.check_witness(
            "4_1_cts",
            self.summary(repair_tns="100", skip_last_gasp=True),
            {"SKIP_LAST_GASP": "1"},
        )

    def test_base_arm_has_nothing_to_witness_but_needs_a_call(self):
        """The census still requires repair_timing to have run."""
        campaign.check_witness("4_1_cts", [], {})

    def test_post_grt_call_must_be_absent_when_disabled(self):
        with self.assertRaises(SystemExit):
            campaign.check_witness(
                "5_1_grt",
                self.summary(repair_tns="100")
                + [{"kind": "post_grt_wns", "witness": {}}],
                {"OPT_POST_GRT_WNS": "0"},
            )


if __name__ == "__main__":
    unittest.main()
