#!/usr/bin/env python3
"""A design's pinned power (pin_power.py) is whole and consistent.

    power_pin_test.py PINNED.json [--min-annotation 0.9]
                      [--results results.json --core xiangshan]

Seconds, no flow: the pinned file parses; every provenance field is
there and names no machine; the shards' own totals sum to the pinned
total within report_power's printed digits; every shard's annotation
rate is at or over the gate; and, once the file is whole and its pass
final, the
study's results.json carries the point it gives (its power, as
cm_per_joule.py reads a stage_power() JSON). A partial file, or one
not of the final pass, must not be in results.json yet.
"""

import argparse
import json
import sys
import unittest

ARGS = None
KINDS = ["internal", "switching", "leakage", "total"]
FIELDS = [
    "bazel_orfs_commit",
    "date",
    "period_ps",
    "min_period_ps",
    "cycles",
    "saif_window_ps",
    "method",
    "machine",
    "partial",
    "pass",
    "replays",
]


class PowerPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ARGS.pinned) as f:
            cls.pin = json.load(f)

    def test_provenance(self):
        prov = self.pin["provenance"]
        for field in FIELDS:
            self.assertIn(field, prov)
        self.assertEqual(sorted(prov["machine"]), ["cores", "memory_gb"])
        self.assertEqual(len(prov["saif_window_ps"]), 2)
        self.assertLess(prov["saif_window_ps"][0], prov["saif_window_ps"][1])

    def test_min_period_per_unit(self):
        # energy is read against each unit's own period: every shard has
        # one, measured (at most the SDC's plus its WNS) or null
        periods = self.pin["provenance"]["min_period_ps"]
        self.assertEqual(sorted(periods), sorted(s["unit"] for s in self.pin["shards"]))
        for unit, p in periods.items():
            with self.subTest(unit=unit):
                self.assertTrue(p is None or p > 0)

    def test_shards_sum_to_the_total(self):
        for arm in ("vectorless", "vector_driven"):
            for k in KINDS:
                summed = sum(s[arm][k] for s in self.pin["shards"])
                total = self.pin[arm]["Total"][k]
                with self.subTest(arm=arm, kind=k):
                    self.assertLessEqual(
                        abs(summed - total), 1e-5 * max(abs(total), 1e-12)
                    )

    def test_annotation_at_or_over_the_gate(self):
        for s in self.pin["shards"]:
            with self.subTest(unit=s["unit"]):
                self.assertGreaterEqual(s["annotation"]["rate"], ARGS.min_annotation)

    def test_units_within_their_shard(self):
        rows = self.pin.get("units", [])
        for s in self.pin["shards"]:
            depth1 = [r for r in rows if r["unit"] == s["unit"] and r["depth"] <= 1]
            if not depth1:
                continue
            with self.subTest(unit=s["unit"]):
                total = sum(r["total"] for r in depth1)
                self.assertLessEqual(
                    abs(total - s["vector_driven"]["total"]),
                    1e-5 * s["vector_driven"]["total"],
                )

    def test_results_json(self):
        if not ARGS.results:
            self.skipTest("no results.json given")
        with open(ARGS.results) as f:
            results = json.load(f)
        points = [p for p in results["points"] if p.get("core") == ARGS.core]
        prov = self.pin["provenance"]
        if prov["partial"] or prov["pass"] != "final":
            self.assertEqual(
                points, [], "a partial or not final pin is in results.json"
            )
            return
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(
            points[0]["power_w"], self.pin["vector_driven"]["Total"]["total"], places=6
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pinned")
    parser.add_argument("--min-annotation", type=float, default=0.9)
    parser.add_argument("--results")
    parser.add_argument("--core")
    ARGS = parser.parse_args()
    unittest.main(argv=sys.argv[:1])
