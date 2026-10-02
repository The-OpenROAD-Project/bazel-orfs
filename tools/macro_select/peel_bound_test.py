"""peel_bound.py: the balance of two stages around a movable flop."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import peel_bound  # noqa: E402

HEADER_PATHS = [
    "rank",
    "path_ps",
    "launch_block",
    "launch_port",
    "crossing_ps",
    "startpoint",
    "endpoint",
]


def path(rank, ps, block="", port="", crossing=""):
    return dict(
        zip(HEADER_PATHS, [str(rank), str(ps), block, port, str(crossing), "s", "e"])
    )


def flop(kind, ports, da, extra=0):
    return {
        "kind": kind,
        "flop": "f",
        "ports": ports,
        "extra_pins": str(extra),
        "da_ps": str(da),
    }


class PathBound(unittest.TestCase):
    def test_balances(self):
        # 1,000 out, 200 in, wire enough to move 400: both stages 600
        self.assertEqual(peel_bound.path_bound(1000, 200, 1000), 600)

    def test_limited_by_crossing(self):
        # only 100 of wire to move: 900 out, 300 in
        self.assertEqual(peel_bound.path_bound(1000, 200, 100), 900)

    def test_never_worse(self):
        # the block's stage is already the longer one: the flop stays put
        self.assertEqual(peel_bound.path_bound(500, 800, 1000), 800)


class Bound(unittest.TestCase):
    def setUp(self):
        self.blocks = {
            "Frontend": [
                flop("out_pure", "a[0]", 1200),
                flop("out_shared", "b[0]", 1000, extra=1),
                flop("in_pure", "c[0]", ""),
            ]
        }

    def test_unpeelable_path_sets_the_bound(self):
        paths = [
            path(1, 3800, "Frontend", "a[0]", 2000),
            path(2, 3000),  # launched by a parent flop: stays
        ]
        rows, s = peel_bound.bound(paths, self.blocks)
        self.assertEqual(rows[0]["bound_ps"], 2500)
        self.assertFalse(rows[1]["peeled"])
        self.assertEqual(s["bound_ps"], 3000)
        self.assertEqual(s["first_unpeeled_ps"], 3000)

    def test_pure_only_skips_shared(self):
        paths = [path(1, 3800, "Frontend", "b[0]", 2000), path(2, 1000)]
        _, s = peel_bound.bound(paths, self.blocks, pure_only=True)
        self.assertEqual(s["peeled"], 0)
        self.assertEqual(s["bound_ps"], 3800)
        _, s = peel_bound.bound(paths, self.blocks)
        self.assertEqual(s["peeled"], 1)

    def test_floor_says_probe_more(self):
        paths = [
            path(1, 3800, "Frontend", "a[0]", 2000),
            path(2, 2600, "Frontend", "a[0]", 2000),
        ]
        _, s = peel_bound.bound(paths, self.blocks)
        # 3,800 balances to 2,500, 2,600 to 1,900; nothing below 2,600 was probed
        self.assertEqual(s["bound_ps"], 2600)
        self.assertTrue(s["at_floor"])

    def test_input_flops_are_not_launch_ports(self):
        paths = [path(1, 3800, "Frontend", "c[0]", 2000)]
        _, s = peel_bound.bound(paths, self.blocks)
        self.assertEqual(s["peeled"], 0)

    def test_no_paths(self):
        with self.assertRaises(ValueError):
            peel_bound.bound([], self.blocks)


if __name__ == "__main__":
    unittest.main()
