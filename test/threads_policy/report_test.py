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


def step(wall, cpu=1500, sha1="a" * 20, user=None):
    return {
        "wall_s": wall,
        "user_s": user if user is not None else wall * cpu / 100.0,
        "sys_s": 0.0,
        "cpu_pct": cpu,
        "peak_kb": 1024,
        "threads": None,
        "result_sha1": sha1,
    }


def build(records):
    return records, report.index(records)


class EmptyResults(unittest.TestCase):
    def test_body_says_nothing_was_measured(self):
        text = report.body([], {})
        self.assertIn("No results recorded yet", text)

    def test_every_section_names_itself_unmeasured(self):
        """A partial campaign must not read as a complete one."""
        records, cells = build([
            rec("aes", "route", 32, 1, {"5_2_route": step(100.0)}),
        ])
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
            [rec("aes", "route", 32, r, {"5_3_fillcell": step(10.0, cpu=99)})
             for r in (1, 2, 3)]
            + [rec("aes", "route", 16, r, {"5_3_fillcell": step(10.0, cpu=99)})
               for r in (1, 2, 3)]
        )
        text = report.body(records, cells)
        self.assertIn("thread-blind", text)

    def test_a_difference_inside_the_noise_did_not_resolve(self):
        """Smaller than the instrument's spread is not 'no effect'."""
        records, cells = build(
            [rec("aes", "route", 32, r, {"5_2_route": step(w)})
             for r, w in enumerate([100.0, 120.0, 80.0], start=1)]
            + [rec("aes", "route", 16, r, {"5_2_route": step(w)})
               for r, w in enumerate([99.0, 121.0, 79.0], start=1)]
        )
        text = report.body(records, cells)
        self.assertIn("did not resolve", text)

    def test_one_run_per_arm_cannot_resolve_anything(self):
        records, cells = build([
            rec("aes", "route", 32, 1, {"5_2_route": step(100.0)}),
            rec("aes", "route", 16, 1, {"5_2_route": step(70.0)}),
        ])
        text = report.body(records, cells)
        self.assertIn("did not resolve", text)


class DifferentWork(unittest.TestCase):
    def test_identical_hashes_report_identical_work(self):
        records, cells = build([
            rec("aes", "route", 32, 1, {"5_2_route": step(100.0, sha1="b" * 20)}),
            rec("aes", "route", 16, 1, {"5_2_route": step(70.0, sha1="b" * 20)}),
        ])
        self.assertIn("**No.**", report.section_work_changed(cells))

    def test_differing_hashes_disqualify_the_speedup_reading(self):
        records, cells = build([
            rec("aes", "route", 32, 1, {"5_2_route": step(100.0, sha1="b" * 20)}),
            rec("aes", "route", 16, 1, {"5_2_route": step(70.0, sha1="c" * 20)}),
        ])
        text = report.section_work_changed(cells)
        self.assertIn("different work", text)
        body = report.body(records, cells)
        self.assertIn("**NO**", body)

    def test_a_missing_hash_is_unproven_not_equal(self):
        records, cells = build([
            rec("aes", "route", 32, 1, {"5_2_route": step(100.0, sha1=None)}),
            rec("aes", "route", 16, 1, {"5_2_route": step(70.0, sha1=None)}),
        ])
        self.assertIn("unproven", report.body(records, cells))


class Pinning(unittest.TestCase):
    def test_pinned_arms_are_compared_against_the_free_ones(self):
        records, cells = build([
            rec("aes", "route", 16, 1, {"5_2_route": step(100.0)}),
            rec("aes", "route", 16, 1, {"5_2_route": step(80.0)}, pinned=True),
        ])
        text = report.section_pinning(cells, records)
        self.assertIn("-20.0%", text)

    def test_absent_pinning_says_what_it_cannot_conclude(self):
        records, cells = build([
            rec("aes", "route", 16, 1, {"5_2_route": step(100.0)}),
        ])
        text = report.section_pinning(cells, records)
        self.assertIn("Not measured", text)
        self.assertIn("affinity", text)


class RawComment(unittest.TestCase):
    def test_one_row_per_substep_sample(self):
        records, _ = build([
            rec("aes", "route", 32, 1, {"5_2_route": step(100.0), "5_3_fillcell": step(5.0)}),
            rec("aes", "route", 16, 1, {"5_2_route": step(70.0), "5_3_fillcell": step(5.0)}),
        ])
        rows = report.csv_rows(records)
        self.assertEqual(len(rows), 5)  # header + 4
        self.assertIn("design,stage,substep", rows[0])

    def test_the_cap_is_enforced_rather_than_hoped_for(self):
        self.assertEqual(report.GITHUB_CHAR_CAP, 65536)


if __name__ == "__main__":
    unittest.main()
