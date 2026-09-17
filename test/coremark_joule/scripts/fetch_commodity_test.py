#!/usr/bin/env python3
"""Unit tests for the commodity-table regenerator.

The four exports are Phoronix's data and are not committed, so the
end-to-end check -- that results/commodity_coremark.csv still matches them
-- is a local step rather than a CI one:

    fetch_commodity.py --exports DIR --check results/commodity_coremark.csv

What is testable without them is everything between: that the wide PTS
export parses, that a measured row takes its numbers from the export rather
than from the manifest, and that every way of carrying a wrong number is
either refused or reported.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_commodity  # noqa: E402
from fetch_commodity import Row, build, read_export  # noqa: E402

EXPORT = """,Some CPU Review,

 ,,"Alpha","Beta",
Processor,,Widget A 8-Core @ 5.50GHz (8 Cores / 16 Threads),Widget B @ 3.00GHz (4 Cores / 4 Threads),
"Coremark - CoreMark Size 666 - Iterations Per Second (Iterations/Sec)",HIB,514275.923035,204530.928779
"Coremark - CPU Power Consumption Monitor (Watts)",,112.42
"""

ALPHA = Row("RID", "Alpha", "Widget A", "desktop", "Zen 4",
            "8", "16", "5.50", "measured", None, ("17.60", "130.16"))
BETA = Row("RID", "Beta", "Widget B", "laptop", "Oryon",
           "4", "4", "3.00", "package_est", "20", None)


def render(rows, export=EXPORT):
    with mock.patch.object(fetch_commodity, "SELECTION", rows), \
         mock.patch.dict(fetch_commodity.SOURCES, {"RID": "a review"}, clear=True):
        return build({"RID": read_export(export)})


class ReadExportTest(unittest.TestCase):
    def test_parses_perf_power_and_processor(self):
        got = read_export(EXPORT)
        self.assertEqual(514275.923035, got["Alpha"]["perf"])
        self.assertEqual(112.42, got["Alpha"]["power"])
        self.assertEqual(("8", "16", "5.50"), (got["Alpha"]["cores"],
                                               got["Alpha"]["threads"],
                                               got["Alpha"]["ghz"]))

    def test_a_system_without_a_power_monitor_has_no_power(self):
        self.assertNotIn("power", read_export(EXPORT)["Beta"])

    def test_a_file_that_is_not_an_export_is_refused(self):
        with self.assertRaises(ValueError):
            read_export("nothing,to,see\n")


class BuildTest(unittest.TestCase):
    def test_measured_numbers_come_from_the_export(self):
        csv, notes = render([ALPHA])
        self.assertEqual([], notes)
        # perf rounded, not truncated; power to two places
        self.assertTrue(csv.endswith(
            "RID,desktop,Widget A,Zen 4,8,16,5.50,514276,112.42,measured,17.60,130.16\n"))

    def test_the_header_block_is_reproduced(self):
        csv, _ = render([ALPHA])
        self.assertTrue(csv.startswith("# Multi-threaded CoreMark 1.0"))
        self.assertIn(
            "result_id,class,cpu,microarchitecture,cores,threads,reported_ghz,"
            "iterations_per_s,power_w,power_kind,power_min_w,power_max_w\n", csv)

    def test_a_carried_power_is_used_when_pts_measured_none(self):
        csv, notes = render([BETA])
        self.assertEqual([], notes)
        self.assertIn(",204531,20,package_est,,\n", csv)

    def test_claiming_measured_when_the_export_has_none_is_fatal(self):
        with self.assertRaises(SystemExit):
            render([BETA._replace(power_kind="measured", power=None)])

    def test_carrying_a_power_the_export_actually_measured_is_reported(self):
        _, notes = render([ALPHA._replace(power_kind="tdp", power="95")])
        self.assertEqual(1, len(notes))
        self.assertIn("carried as tdp, but the export measured 112.42 W", notes[0])

    def test_a_carried_field_that_disagrees_is_reported_not_silent(self):
        _, notes = render([ALPHA._replace(ghz="5.57")])
        self.assertEqual(["Widget A: ghz carried as 5.57, export says 5.50"], notes)

    def test_a_missing_system_names_itself(self):
        with self.assertRaises(SystemExit):
            render([ALPHA._replace(key="Gamma")])

    def test_a_missing_export_names_the_result_id(self):
        with self.assertRaises(SystemExit):
            render([ALPHA._replace(result_id="OTHER")])


class SelectionTest(unittest.TestCase):
    """The manifest is the study's choice of parts, so guard its shape."""

    def test_every_row_cites_a_known_export(self):
        for row in fetch_commodity.SELECTION:
            self.assertIn(row.result_id, fetch_commodity.SOURCES, row.cpu)

    def test_no_part_appears_twice(self):
        names = [r.cpu for r in fetch_commodity.SELECTION]
        self.assertEqual(sorted(set(names)), sorted(names))

    def test_a_row_is_measured_or_says_where_its_power_came_from(self):
        for row in fetch_commodity.SELECTION:
            if row.power_kind == "measured":
                self.assertIsNone(row.power, "%s: measured, so do not carry one" % row.cpu)
            elif row.power_kind == "none":
                self.assertFalse(row.power, "%s: no power means no figure" % row.cpu)
            else:
                self.assertTrue(row.power, "%s: %s with no figure" % (row.cpu, row.power_kind))

    def test_only_one_row_has_no_power_at_all(self):
        """Graviton4 is the only part with nothing to divide by, and A.1 says so."""
        self.assertEqual(["AWS Graviton4"],
                         [r.cpu for r in fetch_commodity.SELECTION if r.power_kind == "none"])


if __name__ == "__main__":
    unittest.main()
