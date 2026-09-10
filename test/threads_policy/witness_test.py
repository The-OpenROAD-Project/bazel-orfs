#!/usr/bin/env python3
"""A witness that reports a divergence which is not there is worse than none.

#968 hit that: comparing everything the flow wrote produced a fake QoR
divergence across 48 of 54 design/substep pairs, because runtime and
peak-memory fields differ between two runs of identical work. So the
tests here are as much about what the QoR witness *excludes* as about
what it reads.

The metric fixture is a trimmed copy of a real
`logs/nangate45/gcd/<variant>/4_1_cts.json`.
"""

import json
import os
import shutil
import tempfile
import unittest

import witness

METRICS = {
    "cts__timing__setup__ws": -0.0432,
    "cts__timing__setup__tns": -1.203,
    "cts__timing__hold__ws": 0.0121,
    "cts__timing__hold__tns": 0.0,
    "cts__clock__skew__setup": 0.0189,
    "cts__design__instance__count": 331,
    "cts__design__instance__count__setup_buffer": 7,
    "cts__design__instance__count__hold_buffer": 0,
    "cts__design__instance__count__stdcell": 331,
    "cts__design__instance__area": 920.4,
    "cts__route__wirelength__estimated": 4711,
    "cts__design__nets": 402,
    # The fields that differ between two runs of identical work.
    "cts__runtime__total": 4.96,
    "cts__peak_memory": 148260,
    "cts__power__total": 0.00123,
}


class QoR(unittest.TestCase):
    def setUp(self):
        self.logs = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.logs)
        with open(os.path.join(self.logs, "4_1_cts.json"), "w") as handle:
            json.dump(METRICS, handle)

    def test_the_stage_prefix_is_stripped_so_columns_read_across_stages(self):
        got = witness.qor(self.logs, "4_1_cts")
        self.assertIn("timing__setup__ws", got)
        self.assertNotIn("cts__timing__setup__ws", got)

    def test_runtime_and_memory_are_excluded(self):
        # The #968 failure: these differ between two runs of identical
        # work, so including them reports every pair as divergent.
        got = witness.qor(self.logs, "4_1_cts")
        self.assertFalse([k for k in got if "runtime" in k or "memory" in k])

    def test_power_is_excluded(self):
        self.assertFalse([k for k in witness.qor(self.logs, "4_1_cts") if "power" in k])

    def test_the_rsz_buffer_counts_are_included(self):
        # OpenROAD#9781's signal: repair_timing inserted a different
        # number of buffers at 16 threads than at 1.
        got = witness.qor(self.logs, "4_1_cts")
        self.assertEqual(got["design__instance__count__setup_buffer"], 7)
        self.assertEqual(got["design__instance__count__hold_buffer"], 0)

    def test_a_longer_key_is_not_swallowed_by_a_shorter_suffix(self):
        # `__count__stdcell` must not be read as `__count`, or two
        # different metrics would land in one column.
        got = witness.qor(self.logs, "4_1_cts")
        self.assertEqual(got["design__instance__count"], 331)
        self.assertNotIn("design__instance__count__stdcell", got)

    def test_no_metrics_file_is_none_not_empty(self):
        # None means "the substep wrote no metrics"; {} would mean "it
        # wrote metrics and none were comparable". Different findings.
        self.assertIsNone(witness.qor(self.logs, "5_2_route"))

    def test_unparseable_metrics_are_none_rather_than_a_crash(self):
        with open(os.path.join(self.logs, "5_1_grt.json"), "w") as handle:
            handle.write("{not json")
        self.assertIsNone(witness.qor(self.logs, "5_1_grt"))


class UnprefixedKeys(unittest.TestCase):
    """Not every substep prefixes its metric keys with the stage.

    `5_3_fillcell.json` writes bare `design__violations`. Matching on
    the `__`-leading suffix alone dropped it, so that substep compared
    no metrics and still reported `stable`.
    """

    def setUp(self):
        self.logs = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.logs)

    def _write(self, step, metrics):
        with open(os.path.join(self.logs, step + ".json"), "w") as handle:
            json.dump(metrics, handle)

    def test_a_bare_key_is_read(self):
        self._write("5_3_fillcell", {"design__violations": 3})
        self.assertEqual(
            witness.qor(self.logs, "5_3_fillcell"), {"design__violations": 3}
        )

    def test_a_prefixed_key_lands_in_the_same_column(self):
        self._write("4_1_cts", {"cts__design__violations": 3})
        self.assertEqual(witness.qor(self.logs, "4_1_cts"), {"design__violations": 3})

    def test_the_route_substep_compares_more_than_its_wirelength(self):
        # route runs no STA, so its metrics are drt's own counts and
        # none of the timing suffixes exist there.
        self._write(
            "5_2_route",
            {
                "detailedroute__route__wirelength": 764,
                "detailedroute__route__drc_errors": 0,
                "detailedroute__route__vias": 300,
                "detailedroute__route__vias__multicut": 0,
                "detailedroute__route__net": 40,
                "detailedroute__antenna__violating__nets": 0,
                "detailedroute__flow__errors__count": 0,
                "detailedroute__route__drc_errors__iter:0": 5,
            },
        )
        got = witness.qor(self.logs, "5_2_route")
        self.assertIn("route__drc_errors", got)
        self.assertIn("route__vias", got)
        self.assertIn("route__net", got)
        self.assertIn("antenna__violating__nets", got)
        self.assertGreaterEqual(len(got), 6)

    def test_vias_and_multicut_vias_do_not_share_a_column(self):
        self._write(
            "5_2_route",
            {
                "detailedroute__route__vias": 300,
                "detailedroute__route__vias__multicut": 7,
            },
        )
        got = witness.qor(self.logs, "5_2_route")
        self.assertEqual(got["route__vias"], 300)
        self.assertEqual(got["route__vias__multicut"], 7)


class Differences(unittest.TestCase):
    def test_identical_samples_have_none(self):
        self.assertEqual(witness.differences({"a": 1}, {"a": 1}), {})

    def test_the_last_decimal_place_counts_as_a_divergence(self):
        # The question is whether two runs computed the same thing, not
        # whether the difference is large enough to matter.
        got = witness.differences(
            {"timing__setup__ws": -0.0432}, {"timing__setup__ws": -0.0433}
        )
        self.assertEqual(got, {"timing__setup__ws": (-0.0432, -0.0433)})

    def test_a_key_present_on_one_side_only_is_a_difference(self):
        self.assertEqual(witness.differences({"a": 1}, {}), {"a": (1, None)})

    def test_a_missing_sample_does_not_crash(self):
        self.assertEqual(witness.differences(None, {"a": 1}), {"a": (None, 1)})
        self.assertEqual(witness.differences(None, None), {})


class Hashes(unittest.TestCase):
    def setUp(self):
        self.results = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.results)

    def test_twenty_hex_characters_to_match_orfs_own_summary(self):
        path = os.path.join(self.results, "4_1_cts.odb")
        with open(path, "wb") as handle:
            handle.write(b"odb")
        got = witness.odb_sha1(self.results, "4_1_cts")
        self.assertEqual(len(got), 20)
        self.assertTrue(all(c in "0123456789abcdef" for c in got))

    def test_a_missing_file_is_none_not_a_crash(self):
        # A substep that died leaves no .odb, and the sample has to
        # record an unproven witness rather than fail to be recorded.
        self.assertIsNone(witness.odb_sha1(self.results, "4_1_cts"))
        self.assertIsNone(witness.sdc_sha1(self.results, "4_cts.sdc"))
        self.assertIsNone(witness.sdc_sha1(self.results, None))

    def test_different_bytes_give_different_witnesses(self):
        for name, data in (("a.odb", b"one"), ("b.odb", b"two")):
            with open(os.path.join(self.results, name), "wb") as handle:
                handle.write(data)
        self.assertNotEqual(
            witness.odb_sha1(self.results, "a"), witness.odb_sha1(self.results, "b")
        )

    def test_sdc_comes_before_odb_in_the_reading_order(self):
        # check_same.sh's reason: a binary ODB diff stops at the first
        # differing byte, an .sdc diff is readable.
        self.assertLess(witness.KINDS.index("sdc"), witness.KINDS.index("odb"))


if __name__ == "__main__":
    unittest.main()
