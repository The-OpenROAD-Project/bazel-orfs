"""--seeds: a packing near the core's size is legal for some seeds and not
others. XSTile's MemBlock after the OpenROAD/ORFS bump (3353b055): seed 1
left 16 of L2TLB's l0 arrays outside the core, while seeds 7 and 8 place
all 57 macros; the search keeps the legal one of least cost."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_anneal  # noqa: E402

INVENTORY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "testdata", "memblock_inventory.txt"
)
KNOBS = [
    "--depth",
    "3",
    "--min-cluster",
    "1",
    "--channel-um",
    "4.0",
    "--block-gap-um",
    "10.8",
    "--strap-pitch-um",
    "5.4",
    "--strap-offset-um",
    "0.3",
    "--strap-pair-um",
    "0.312",
    "--fill",
    "0.5",
    "--channel-check",
    "warn",
]


def anneal(seeds):
    with tempfile.TemporaryDirectory() as d:
        metrics = os.path.join(d, "metrics.json")
        rc = macro_anneal.main(
            [
                "macro_anneal.py",
                "--inventory",
                INVENTORY,
                "--out",
                os.path.join(d, "placement.tcl"),
                "--metrics",
                metrics,
                "--seed",
                "1",
                "--seeds",
                str(seeds),
            ]
            + KNOBS
        )
        with open(metrics) as f:
            return rc, json.load(f)


class SeedsTest(unittest.TestCase):
    def test_one_seed_leaves_macros_outside_the_core(self):
        rc, m = anneal(1)
        self.assertEqual(rc, 1)
        self.assertTrue(any("outside core" in p for p in m["problems"]))

    def test_the_search_finds_a_legal_placement(self):
        rc, m = anneal(8)
        self.assertEqual(rc, 0)
        self.assertEqual(m["problems"], [])
        self.assertEqual(m["placed"], 57)


if __name__ == "__main__":
    unittest.main()
