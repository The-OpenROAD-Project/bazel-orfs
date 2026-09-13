#!/usr/bin/env python3

"""Tests for the three parsers that turn git history into numbers.

Every claim in the study is downstream of these, and all three parse text
written by other people over four years. The cases below are taken from
real ORFS commits, reduced to the smallest form that still exercises the
thing that could break.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract
import labels
import series


class RulesBlob(unittest.TestCase):
    def test_parses_value_compare_and_level(self):
        blob = b"""{
            "synth__netlist__hash": {"value": "N/A", "compare": "==", "level": "warning"},
            "finish__design__instance__area": {"value": 319, "compare": "<="}
        }"""
        out = extract.parse_rules(blob)
        self.assertEqual(out["finish__design__instance__area"], (319, "<=", ""))
        self.assertEqual(out["synth__netlist__hash"], ("N/A", "==", "warning"))

    def test_non_object_revision_is_an_error_not_a_silent_empty(self):
        with self.assertRaises(ValueError):
            extract.parse_rules(b"[1, 2, 3]")

    def test_malformed_revision_raises(self):
        with self.assertRaises(Exception):
            extract.parse_rules(b"{not json")


class DesignPaths(unittest.TestCase):
    def test_platform_and_design_are_recovered(self):
        m = extract.PATH_RE.match("flow/designs/asap7/aes-block/rules-base.json")
        self.assertEqual(m.groups(), ("asap7", "aes-block"))

    def test_other_files_are_not_rules(self):
        for path in (
            "flow/designs/asap7/aes/config.mk",
            "flow/designs/asap7/aes/metadata-base-ok.json",
            "docs/rules-base.json",
        ):
            self.assertIsNone(extract.PATH_RE.match(path), path)


class CommitTables(unittest.TestCase):
    ROW = "| finish__design__instance__area              |     167958 |     238519 | Failing  |"

    def test_row_is_parsed(self):
        m = labels.ROW_RE.match(self.ROW)
        self.assertEqual(m.group("metric"), "finish__design__instance__area")
        self.assertEqual(m.group("old"), "167958")
        self.assertEqual(m.group("new"), "238519")
        self.assertEqual(m.group("type"), "Failing")

    def test_negative_and_fractional_values(self):
        row = "| cts__timing__setup__ws  |     -0.225 |     -0.603 | Tighten  |"
        m = labels.ROW_RE.match(row)
        self.assertEqual(m.group("old"), "-0.225")
        self.assertEqual(m.group("type"), "Tighten")

    def test_separator_row_is_not_a_metric(self):
        self.assertIsNone(labels.ROW_RE.match("| ------  | ---  | ---  | ----     |"))

    def test_header_row_is_not_a_metric(self):
        self.assertIsNone(labels.ROW_RE.match("| Metric  | Old  | New  | Type     |"))

    def test_design_header_line(self):
        m = labels.HEADER_RE.search("designs/ihp-sg13g2/aes/rules-base.json updates:")
        self.assertEqual(m.group("platform"), "ihp-sg13g2")
        self.assertEqual(m.group("design"), "aes")


class Retargeting(unittest.TestCase):
    TIMES = [10, 20, 30]

    def test_change_inside_the_interval_is_found(self):
        self.assertTrue(series.retargeted_between(self.TIMES, 15, 25))

    def test_interval_with_no_change_is_clean(self):
        self.assertFalse(series.retargeted_between(self.TIMES, 21, 29))

    def test_boundary_is_half_open_so_a_step_is_counted_once(self):
        # (lo, hi]: a retarget exactly at lo belongs to the previous step.
        self.assertFalse(series.retargeted_between(self.TIMES, 20, 20))
        self.assertTrue(series.retargeted_between(self.TIMES, 19, 20))


if __name__ == "__main__":
    unittest.main()
