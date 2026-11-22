#!/usr/bin/env python3
"""The per-module breakdown across the power shards adds up.

    units_test.py UNITS.json SHARDS.json VECTOR_DRIVEN.json

Per unit, its depth-1 module instances and its flat remainder sum to the
unit's own total; over every unit, to the design's total; and no module
instance appears in two units (a module never spans a shard: a shard's
children are cut out of its ODB). BlockC's two kept modules, u_in and
u_core, are its rows.
"""

import json
import sys
import unittest

UNITS, SHARDS, TOTAL = sys.argv[1:4]


def load(path):
    with open(path) as f:
        return json.load(f)


class UnitsTest(unittest.TestCase):
    def test_each_unit_adds_up(self):
        rows = load(UNITS)
        for shard in load(SHARDS)["shards"]:
            depth1 = [r for r in rows if r["unit"] == shard["unit"] and r["depth"] <= 1]
            with self.subTest(unit=shard["unit"]):
                self.assertAlmostEqual(
                    sum(r["total"] for r in depth1),
                    shard["vector_driven"]["total"],
                    places=9,
                )

    def test_the_design_adds_up(self):
        rows = [r for r in load(UNITS) if r["depth"] <= 1]
        self.assertAlmostEqual(
            sum(r["total"] for r in rows), load(TOTAL)["Total"]["total"], places=9
        )

    def test_no_module_in_two_units(self):
        paths = [r["path"] for r in load(UNITS) if r["depth"] > 0]
        self.assertEqual(len(paths), len(set(paths)))

    def test_blockc_kept_modules_reported(self):
        paths = {r["path"]: r for r in load(UNITS)}
        for p in ("u_blockc/u_in", "u_blockc/u_core"):
            self.assertIn(p, paths)
            self.assertGreater(paths[p]["total"], 0)
        print(
            "BlockC: u_in {:.3e} W, u_core {:.3e} W, own cells {:.3e} W".format(
                paths["u_blockc/u_in"]["total"],
                paths["u_blockc/u_core"]["total"],
                paths["u_blockc"]["total"],
            )
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
