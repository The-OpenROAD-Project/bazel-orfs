"""Unit tests for the raw-sample CSV exporter."""

import csv
import io
import unittest

import csv_export


def sample(**fields):
    record = {
        "platform": "asap7",
        "design": "gcd",
        "arm": "spread",
        "arm_witnessed": "spread",
        "seed": 3,
        "gp_hpwl_final": 523.4,
        "initial_place": {
            "last_iteration": 5,
            "final_residual": 1.1e-07,
            "converged": True,
            "hit_cap": False,
            "hpwl_first": 721133,
            "hpwl_last": 637513,
        },
        "position_sources": {"odb": 0, "core_center": 314, "region_center": 0},
        "witness": {"3_3_place_gp.odb": "abc123"},
        "run": {"serial": False, "cores": 4, "loadavg_at_start": 1.2, "status": 0,
                "command": ["<tree>/make", "do-place"]},
    }
    record.update(fields)
    return record


def parse(text):
    return list(csv.DictReader(io.StringIO(text)))


class ColumnsTest(unittest.TestCase):
    def test_header_is_the_allowlist_in_order(self):
        rows = csv_export.export([sample()])
        header = rows.splitlines()[0].split(",")
        self.assertEqual(header, csv_export.SAFE_COLUMNS)

    def test_nested_fields_are_flattened(self):
        row = parse(csv_export.export([sample()]))[0]
        self.assertEqual(row["ip_iterations"], "5")
        self.assertEqual(row["ip_converged"], "True")
        self.assertEqual(row["src_core_3_3"], "314")
        self.assertEqual(row["place_gp_sha1"], "abc123")
        self.assertEqual(row["cores"], "4")

    def test_absent_pieces_are_empty_not_the_word_none(self):
        # A spreadsheet must read a missing value as missing, and a
        # reader must not mistake the string "None" for a measurement.
        row = parse(csv_export.export([sample(initial_place=None, witness={})]))[0]
        self.assertEqual(row["ip_iterations"], "")
        self.assertEqual(row["grt_sha1"], "")

    def test_the_command_never_becomes_a_column(self):
        # The allowlist is what stops a future field -- a path, a host
        # name, an absolute tree -- from reaching a published comment by
        # being added to the record.
        self.assertNotIn("command", csv_export.SAFE_COLUMNS)
        self.assertNotIn("run", csv_export.SAFE_COLUMNS)
        self.assertNotIn("metrics", csv_export.SAFE_COLUMNS)
        text = csv_export.export([sample()])
        self.assertNotIn("<tree>", text)
        self.assertNotIn("do-place", text)

    def test_no_absolute_path_survives_export(self):
        record = sample()
        record["run"]["command"] = ["/home/someone/secret/make", "do-place"]
        text = csv_export.export([record])
        self.assertNotIn("/home/", text)

    def test_the_witness_is_a_column_not_a_silent_filter(self):
        self.assertIn("arm_witnessed", csv_export.SAFE_COLUMNS)


class OrderTest(unittest.TestCase):
    def test_rows_sort_by_design_arm_seed(self):
        rows = parse(
            csv_export.export(
                [
                    sample(arm="spread", seed=2),
                    sample(arm="center", arm_witnessed="center", seed=10),
                    sample(arm="center", arm_witnessed="center", seed=2),
                ]
            )
        )
        self.assertEqual(
            [(r["arm"], r["seed"]) for r in rows],
            [("center", "2"), ("center", "10"), ("spread", "2")],
        )

    def test_seeds_sort_numerically_not_lexically(self):
        rows = parse(
            csv_export.export([sample(seed=10), sample(seed=9), sample(seed=100)])
        )
        self.assertEqual([r["seed"] for r in rows], ["9", "10", "100"])


if __name__ == "__main__":
    unittest.main()
