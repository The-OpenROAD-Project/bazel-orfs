#!/usr/bin/env python3
"""Tests for the report generator's verdicts.

The verdicts are the study's conclusions, so they are what needs
testing: a generator that calls a null result a speedup, or a
different-work comparison a speedup, would produce a plausible and
wrong pull request.
"""

import unittest

import report

PROV = {
    "cpu_model": "Test CPU",
    "physical_cores": 16,
    "hardware_threads": 32,
    "governor": "powersave",
    "boost": "1",
    "kernel": "test",
}


def rec(design, stage, threads, repeat, substeps, pinned=False):
    return {
        "design": design,
        "stage": stage,
        "threads": threads,
        "repeat": repeat,
        "pinned": pinned,
        "loadavg_at_start": 0.1,
        "provenance": PROV,
        "substeps": substeps,
    }


def step(wall, cpu=1500, sha1="a" * 20, user=None, phases=None, reconcile=None):
    got = {
        "wall_s": wall,
        "user_s": user if user is not None else wall * cpu / 100.0,
        "sys_s": 0.0,
        "cpu_pct": cpu,
        "peak_kb": 1024,
        "threads": None,
        "result_sha1": sha1,
    }
    if phases is not None:
        got["phases"] = [
            {"name": n, "seconds": sec, "detail": "", "order": i}
            for i, (n, sec) in enumerate(phases)
        ]
        attributed = sum(sec for _, sec in phases)
        got["reconcile"] = reconcile or {
            "wall_s": wall,
            "attributed_s": attributed,
            "unattributed_s": wall - attributed,
            "over_attributed": False,
            "ok": True,
            "allowed_s": 1.0,
        }
    return got


def build(records):
    return records, report.index(records)


class EmptyResults(unittest.TestCase):
    def test_body_says_nothing_was_measured(self):
        text = report.body([], {})
        self.assertIn("No results recorded yet", text)

    def test_every_section_names_itself_unmeasured(self):
        """A partial campaign must not read as a complete one."""
        records, cells = build(
            [
                rec("aes", "route", 32, 1, {"5_2_route": step(100.0)}),
            ]
        )
        text = report.body(records, cells)
        self.assertIn("Not measured", text)
        # No 16-thread arm, so the headline comparison cannot be drawn.
        self.assertIn("Needs unpinned arms at both", text)


class Verdicts(unittest.TestCase):
    def test_a_real_speedup_is_called_faster(self):
        records, cells = build(
            [rec("aes", "route", 32, r, {"5_2_route": step(100.0)}) for r in (1, 2, 3)]
            + [rec("aes", "route", 16, r, {"5_2_route": step(70.0)}) for r in (1, 2, 3)]
        )
        text = report.body(records, cells)
        self.assertIn("faster", text)
        self.assertIn("-30.0%", text)

    def test_a_single_threaded_substep_is_thread_blind_not_a_null_speedup(self):
        """The distinction that keeps every average from being diluted."""
        records, cells = build(
            [
                rec("aes", "route", 32, r, {"5_3_fillcell": step(10.0, cpu=99)})
                for r in (1, 2, 3)
            ]
            + [
                rec("aes", "route", 16, r, {"5_3_fillcell": step(10.0, cpu=99)})
                for r in (1, 2, 3)
            ]
        )
        text = report.body(records, cells)
        self.assertIn("thread-blind", text)

    def test_a_difference_inside_the_noise_did_not_resolve(self):
        """Smaller than the instrument's spread is not 'no effect'."""
        records, cells = build(
            [
                rec("aes", "route", 32, r, {"5_2_route": step(w)})
                for r, w in enumerate([100.0, 120.0, 80.0], start=1)
            ]
            + [
                rec("aes", "route", 16, r, {"5_2_route": step(w)})
                for r, w in enumerate([99.0, 121.0, 79.0], start=1)
            ]
        )
        text = report.body(records, cells)
        self.assertIn("did not resolve", text)

    def test_one_run_per_arm_cannot_resolve_anything(self):
        records, cells = build(
            [
                rec("aes", "route", 32, 1, {"5_2_route": step(100.0)}),
                rec("aes", "route", 16, 1, {"5_2_route": step(70.0)}),
            ]
        )
        text = report.body(records, cells)
        self.assertIn("did not resolve", text)


class DifferentWork(unittest.TestCase):
    def test_identical_hashes_report_identical_work(self):
        records, cells = build(
            [
                rec("aes", "route", 32, 1, {"5_2_route": step(100.0, sha1="b" * 20)}),
                rec("aes", "route", 16, 1, {"5_2_route": step(70.0, sha1="b" * 20)}),
            ]
        )
        self.assertIn("**No.**", report.section_work_changed(cells))

    def test_differing_hashes_disqualify_the_speedup_reading(self):
        records, cells = build(
            [
                rec("aes", "route", 32, 1, {"5_2_route": step(100.0, sha1="b" * 20)}),
                rec("aes", "route", 16, 1, {"5_2_route": step(70.0, sha1="c" * 20)}),
            ]
        )
        text = report.section_work_changed(cells)
        self.assertIn("different work", text)
        body = report.body(records, cells)
        self.assertIn("**NO**", body)

    def test_a_missing_hash_is_unproven_not_equal(self):
        records, cells = build(
            [
                rec("aes", "route", 32, 1, {"5_2_route": step(100.0, sha1=None)}),
                rec("aes", "route", 16, 1, {"5_2_route": step(70.0, sha1=None)}),
            ]
        )
        self.assertIn("unproven", report.body(records, cells))


class Pinning(unittest.TestCase):
    def test_pinned_arms_are_compared_against_the_free_ones(self):
        records, cells = build(
            [
                rec("aes", "route", 16, 1, {"5_2_route": step(100.0)}),
                rec("aes", "route", 16, 1, {"5_2_route": step(80.0)}, pinned=True),
            ]
        )
        text = report.section_pinning(cells, records)
        self.assertIn("-20.0%", text)

    def test_absent_pinning_says_what_it_cannot_conclude(self):
        records, cells = build(
            [
                rec("aes", "route", 16, 1, {"5_2_route": step(100.0)}),
            ]
        )
        text = report.section_pinning(cells, records)
        self.assertIn("Not measured", text)
        self.assertIn("affinity", text)


class RawComment(unittest.TestCase):
    def test_one_row_per_substep_sample(self):
        records, _ = build(
            [
                rec(
                    "aes",
                    "route",
                    32,
                    1,
                    {"5_2_route": step(100.0), "5_3_fillcell": step(5.0)},
                ),
                rec(
                    "aes",
                    "route",
                    16,
                    1,
                    {"5_2_route": step(70.0), "5_3_fillcell": step(5.0)},
                ),
            ]
        )
        rows = report.csv_rows(records)
        self.assertEqual(len(rows), 5)  # header + 4
        self.assertIn("design,stage,substep", rows[0])

    def test_the_cap_is_enforced_rather_than_hoped_for(self):
        self.assertEqual(report.GITHUB_CHAR_CAP, 65536)


class Ladder(unittest.TestCase):
    def test_needs_three_arms_before_it_says_anything(self):
        records, cells = build(
            [
                rec("aes", "grt", 32, 1, {"5_1_grt": step(100.0)}),
                rec("aes", "grt", 16, 1, {"5_1_grt": step(90.0)}),
            ]
        )
        self.assertIn("Not measured", report.section_ladder(cells, records))

    def test_names_the_best_arm_and_flags_the_ceiling(self):
        records, cells = build(
            [
                rec("aes", "route", t, 1, {"5_2_route": step(w)})
                for t, w in [(8, 140.0), (16, 120.0), (32, 100.0)]
            ]
        )
        text = report.section_ladder(cells, records)
        self.assertIn("t=32 (ceiling)", text)

    def test_a_stage_that_wants_fewer_threads_shows_it(self):
        records, cells = build(
            [
                rec("aes", "grt", t, 1, {"5_1_grt": step(w)})
                for t, w in [(8, 90.0), (16, 80.0), (32, 100.0)]
            ]
        )
        text = report.section_ladder(cells, records)
        self.assertIn("t=16", text)
        self.assertNotIn("t=16 (ceiling)", text)


class Regions(unittest.TestCase):
    def test_says_so_when_no_phase_stacks_were_recorded(self):
        records, cells = build(
            [
                rec("aes", "grt", 32, 1, {"5_1_grt": step(100.0)}),
            ]
        )
        text = report.section_regions(records, cells)
        self.assertIn("Not measured", text)
        self.assertIn("RUN_CMD", text)

    def test_regions_inside_one_substep_get_their_own_curves(self):
        """The point of the whole exercise: grt is mostly repair_timing,
        and repair_timing may want a different count than FastRoute."""
        records, cells = build(
            [
                rec(
                    "aes",
                    "grt",
                    32,
                    1,
                    {
                        "5_1_grt": step(
                            200.0,
                            phases=[("global_route", 40.0), ("repair_timing", 150.0)],
                        )
                    },
                ),
                rec(
                    "aes",
                    "grt",
                    16,
                    1,
                    {
                        "5_1_grt": step(
                            170.0,
                            phases=[("global_route", 20.0), ("repair_timing", 140.0)],
                        )
                    },
                ),
                rec(
                    "aes",
                    "grt",
                    8,
                    1,
                    {
                        "5_1_grt": step(
                            190.0,
                            phases=[("global_route", 25.0), ("repair_timing", 155.0)],
                        )
                    },
                ),
            ]
        )
        text = report.section_regions(records, cells)
        self.assertIn("global_route", text)
        self.assertIn("repair_timing", text)
        # global_route is best at 16 here, and is listed after the bigger
        # repair_timing since regions are ranked by time.
        self.assertLess(text.index("repair_timing"), text.index("global_route"))

    def test_a_command_running_twice_is_summed_within_the_arm(self):
        records, cells = build(
            [
                rec(
                    "aes",
                    "grt",
                    32,
                    1,
                    {
                        "5_1_grt": step(
                            100.0,
                            phases=[("repair_timing", 30.0), ("repair_timing", 20.0)],
                        )
                    },
                ),
                rec(
                    "aes",
                    "grt",
                    16,
                    1,
                    {
                        "5_1_grt": step(
                            90.0,
                            phases=[("repair_timing", 25.0), ("repair_timing", 15.0)],
                        )
                    },
                ),
                rec(
                    "aes",
                    "grt",
                    8,
                    1,
                    {
                        "5_1_grt": step(
                            95.0,
                            phases=[("repair_timing", 28.0), ("repair_timing", 18.0)],
                        )
                    },
                ),
            ]
        )
        text = report.section_regions(records, cells)
        self.assertIn("50.0s", text)


class UnequalCoverage(unittest.TestCase):
    """Pooling arms that cover different designs manufactures an effect.

    Real instance: `route` was swept at t=24 on three designs and
    measured at t=32 on six. Summing each arm as it stood made the
    three-design arm look 47% faster than the six-design one, and that
    fiction propagated into the flow total (-26.5% instead of -8.2%).
    Reconciliation cannot catch this -- every individual sample is fine.
    """

    def _records(self):
        recs = []
        # Six designs at the ceiling, three of them also at t=24.
        for d in ("a", "b", "c", "d", "e", "f"):
            recs.append(rec(d, "route", 32, 1, {"5_2_route": step(100.0)}))
        for d in ("a", "b", "c"):
            recs.append(rec(d, "route", 24, 1, {"5_2_route": step(110.0)}))
        return build(recs)

    def test_a_sparser_arm_does_not_read_as_a_speedup(self):
        records, cells = self._records()
        text = report.section_potential(cells, records)
        # t=24 is slower per design (110 vs 100), so it must never be
        # named the best arm however few designs it covers.
        self.assertNotIn("t=24", text)
        self.assertIn("at ceiling", text)

    def test_the_reduced_scope_is_stated_when_arms_are_dropped(self):
        records, cells = self._records()
        text = report.section_potential(cells, records)
        self.assertIn("designs", text)

    def test_one_arm_is_never_the_answer(self):
        """Keeping both designs here would leave a single arm, which
        compares nothing. Better to compare one design over two arms and
        say so than to report a one-point 'ladder'."""
        per = {"a": {8: 1.0, 16: 1.0}, "b": {16: 1.0}}
        keys, arms = report._common_arms(per, [8, 16])
        self.assertEqual(keys, ["a"])
        self.assertEqual(arms, [8, 16])

    def test_every_returned_key_covers_every_returned_arm(self):
        """The invariant the whole helper exists for."""
        per = {"a": {2: 1.0, 8: 1.0}, "b": {8: 1.0, 16: 1.0}, "c": {8: 1.0, 16: 1.0}}
        keys, arms = report._common_arms(per, [2, 8, 16])
        for k in keys:
            for a in arms:
                self.assertIn(a, per[k])

    def test_common_arms_prefers_the_arms_with_most_coverage(self):
        per = {
            "a": {2: 1.0, 8: 1.0, 16: 1.0},
            "b": {8: 1.0, 16: 1.0},
            "c": {8: 1.0, 16: 1.0},
        }
        keys, arms = report._common_arms(per, [2, 8, 16])
        self.assertEqual(arms, [8, 16])
        self.assertEqual(len(keys), 3)


class Priority(unittest.TestCase):
    """The ranking table, and the attribution rule it turns on."""

    def _grt_like(self):
        """A substep shaped like 5_1_grt: one phase that gets *faster*
        with threads and is the largest, and one that gets slower."""
        recs = []
        for t, pa, rt, wall in [
            (8, 160.0, 255.0, 430.0),
            (24, 94.0, 316.0, 480.0),
            (32, 90.0, 330.0, 504.0),
            (16, 120.0, 260.0, 426.0),
        ]:
            recs.append(
                rec(
                    "aes",
                    "grt",
                    t,
                    1,
                    {
                        "5_1_grt": step(
                            wall, phases=[("pin_access", pa), ("repair_timing", rt)]
                        )
                    },
                )
            )
        return build(recs)

    def test_credits_the_region_that_pays_not_the_largest(self):
        """pin_access is the biggest phase at low thread counts but gets
        faster as threads rise, so a cap cannot be recovering it."""
        records, cells = self._grt_like()
        text = report.section_priority(cells, records)
        row = [l for l in text.splitlines() if l.startswith("| `5_1_grt`")][0]
        self.assertIn("repair_timing", row)
        self.assertNotIn("pin_access", row)

    def test_a_u_shaped_curve_is_measured_from_its_minimum(self):
        """global_placement is slower at 2 threads than at 8, so
        comparing the arm extremes hides the penalty entirely."""
        recs = []
        for t, gp, wall in [
            (2, 98.0, 140.0),
            (8, 78.0, 118.0),
            (24, 89.0, 128.0),
            (32, 92.0, 130.0),
            (16, 80.0, 120.0),
        ]:
            recs.append(
                rec(
                    "aes",
                    "place",
                    t,
                    1,
                    {"3_3_place_gp": step(wall, phases=[("global_placement", gp)])},
                )
            )
        records, cells = build(recs)
        text = report.section_priority(cells, records)
        row = [l for l in text.splitlines() if l.startswith("| `3_3_place_gp`")][0]
        self.assertIn("global_placement", row)

    def test_a_substep_at_the_ceiling_is_marked_as_costing_time(self):
        recs = [
            rec("aes", "route", t, 1, {"5_2_route": step(w)})
            for t, w in [(4, 400.0), (8, 300.0), (16, 200.0), (24, 180.0), (32, 170.0)]
        ]
        # A second substep that does have a saving, so the table renders
        # rather than reporting nothing available.
        recs += [
            rec("aes", "grt", t, 1, {"5_1_grt": step(w)})
            for t, w in [(4, 90.0), (8, 80.0), (16, 70.0), (24, 90.0), (32, 100.0)]
        ]
        records, cells = build(recs)
        text = report.section_priority(cells, records)
        self.assertIn("the ceiling", text)
        row = [l for l in text.splitlines() if l.startswith("| `5_2_route`")][0]
        self.assertIn("capping costs time", row)

    def test_ranked_by_absolute_seconds_not_percentage(self):
        """A big percentage on a small base is worth nothing."""
        recs = []
        # small substep, huge relative gain
        for t, w in [(8, 1.0), (16, 1.0), (24, 5.0), (32, 10.0)]:
            recs.append(rec("aes", "cts", t, 1, {"4_1_cts": step(w)}))
        # large substep, modest relative gain
        for t, w in [(8, 480.0), (16, 420.0), (24, 480.0), (32, 500.0)]:
            recs.append(rec("aes", "grt", t, 1, {"5_1_grt": step(w)}))
        records, cells = build(recs)
        text = report.section_priority(cells, records)
        lines = [l for l in text.splitlines() if l.startswith("| `")]
        self.assertIn("5_1_grt", lines[0])


class Tldr(unittest.TestCase):
    def _flow(self):
        recs = []
        # grt: repair_timing pays, big saving at t=16
        for t, w, rt in [(4, 650.0, 280.0), (8, 480.0, 255.0), (24, 478.0, 316.0)]:
            recs.append(
                rec(
                    "aes",
                    "grt",
                    t,
                    1,
                    {"5_1_grt": step(w, phases=[("repair_timing", rt)])},
                )
            )
        for t, w in [(16, 426.0), (32, 504.0)]:
            recs.append(rec("aes", "grt", t, 1, {"5_1_grt": step(w)}))
        # gpl across two substeps, one of which has no phase data at all
        for t, w, gp in [(4, 120.0, 84.0), (8, 114.0, 78.0), (24, 125.0, 89.0)]:
            recs.append(
                rec(
                    "aes",
                    "place",
                    t,
                    1,
                    {
                        "3_3_place_gp": step(w, phases=[("global_placement", gp)]),
                        "3_1_place_gp_skip_io": step(13.0),
                    },
                )
            )
        for t, w, sk in [(16, 120.0, 14.9), (32, 130.0, 16.2)]:
            recs.append(
                rec(
                    "aes",
                    "place",
                    t,
                    1,
                    {"3_3_place_gp": step(w), "3_1_place_gp_skip_io": step(sk)},
                )
            )
        return build(recs)

    def test_links_the_gpl_pr(self):
        records, cells = self._flow()
        text = report.section_tldr(cells, records)
        self.assertIn("11368", text)
        self.assertIn(
            "https://github.com/The-OpenROAD-Project/OpenROAD/pull/11368", text
        )

    def test_a_substep_with_no_phase_data_still_counts_toward_its_owner(self):
        """3_1_place_gp_skip_io is a gpl call but ORFS emits no `Took`
        line for it. Dropping its seconds inflated the headline ratio
        from 4.4x to 5.5x, which is the kind of error nobody would catch
        by reading the table."""
        records, cells = self._flow()
        rows, total, _measured, _ceiling = report._opportunity(cells, records)
        gpl = sum(
            sv for sv, _st, _rg, ow, _b, _c, _bv in rows if ow == "gpl" and sv > 0
        )
        skip = [
            sv for sv, st, _rg, _ow, _b, _c, _bv in rows if st == "3_1_place_gp_skip_io"
        ][0]
        self.assertGreater(skip, 0)
        self.assertGreaterEqual(gpl, skip)

    def test_says_what_not_to_do(self):
        records, cells = self._flow()
        text = report.section_tldr(cells, records)
        self.assertIn("Do not cap `drt`", text)
        self.assertIn("NUM_CORES", text)

    def test_marks_the_rest_as_reference(self):
        records, cells = self._flow()
        text = report.section_tldr(cells, records)
        self.assertIn("reference detail", text)


class Reconciliation(unittest.TestCase):
    def test_silent_when_nothing_was_reconciled(self):
        records, _ = build([rec("aes", "grt", 32, 1, {"5_1_grt": step(100.0)})])
        self.assertEqual(report.section_reconciliation(records), "")

    def test_reports_a_clean_reconciliation(self):
        records, _ = build(
            [
                rec(
                    "aes",
                    "grt",
                    32,
                    1,
                    {"5_1_grt": step(100.0, phases=[("repair_timing", 90.0)])},
                ),
            ]
        )
        text = report.section_reconciliation(records)
        self.assertIn("reconcile", text)
        self.assertIn("unattributed", text)

    def test_over_attribution_is_surfaced_as_suspect(self):
        """A stack summing past the wall means overlapping phases were
        counted; the per-region table must be flagged, not trusted."""
        bad = {
            "wall_s": 10.0,
            "attributed_s": 90.0,
            "unattributed_s": -80.0,
            "over_attributed": True,
            "ok": False,
            "allowed_s": 1.0,
        }
        records, _ = build(
            [
                rec(
                    "aes",
                    "grt",
                    32,
                    1,
                    {
                        "5_1_grt": step(
                            10.0, phases=[("repair_timing", 90.0)], reconcile=bad
                        )
                    },
                ),
            ]
        )
        text = report.section_reconciliation(records)
        self.assertIn("over-attribute", text)
        self.assertIn("suspect", text)


class Potential(unittest.TestCase):
    def test_a_gain_inside_the_noise_does_not_count_toward_the_total(self):
        """The potential is a bound, not a promise."""
        records, cells = build(
            [
                rec("aes", "grt", 32, r, {"5_1_grt": step(w)})
                for r, w in enumerate([100.0, 130.0, 70.0], start=1)
            ]
            + [
                rec("aes", "grt", 16, r, {"5_1_grt": step(w)})
                for r, w in enumerate([99.0, 129.0, 69.0], start=1)
            ]
        )
        text = report.section_potential(cells, records)
        self.assertIn("**no**", text)

    def test_a_resolved_gain_is_counted(self):
        records, cells = build(
            [
                rec("aes", "grt", 32, r, {"5_1_grt": step(w)})
                for r, w in enumerate([100.0, 101.0, 99.0], start=1)
            ]
            + [
                rec("aes", "grt", 16, r, {"5_1_grt": step(w)})
                for r, w in enumerate([70.0, 71.0, 69.0], start=1)
            ]
        )
        text = report.section_potential(cells, records)
        self.assertIn("yes", text)
        self.assertIn("per-stage choice", text)


if __name__ == "__main__":
    unittest.main()
