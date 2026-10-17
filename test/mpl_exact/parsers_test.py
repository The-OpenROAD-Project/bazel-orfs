"""The study's parsers read what mpl and the flow write as intended."""

import os
import tempfile
import unittest

import bench
import dump_to_problems
import make_table
import patience


class MplArgs(unittest.TestCase):
    def test_reads_the_flows_call(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("something else\n")
            f.write(
                'rtl_macro_placer -max_num_level 2 -min_channel_size "6 6" '
                "-pin_aware_channels -min_ar 0.33 -target_util 0.6\n"
            )
        try:
            args = bench.mpl_args(f.name)
        finally:
            os.remove(f.name)
        self.assertEqual(
            args,
            [
                "--channel",
                "6",
                "6",
                "--pin-aware",
                "--target-util",
                "0.6",
                "--max-num-level",
                "2",
            ],
        )

    def test_no_call_is_none(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("No macros found: Skipping macro_placement\n")
        try:
            self.assertIsNone(bench.mpl_args(f.name))
        finally:
            os.remove(f.name)


class Replay(unittest.TestCase):
    RUN = {"steps": 2000, "improvements": [[1, 9.0], [50, 5.0], [400, 4.0]]}

    def test_stops_at_the_first_long_gap(self):
        # 50 -> 400 is a gap of 350 steps: patience 200 stops at 250 with
        # the best cost so far.
        self.assertEqual(patience.replay(self.RUN, 200), (250, 5.0))

    def test_runs_to_the_last_improvement_plus_patience(self):
        self.assertEqual(patience.replay(self.RUN, 400), (800, 4.0))


class Blocks(unittest.TestCase):
    def test_soft_hard_fixed_and_terminals(self):
        record = {
            "kind": "soft",
            "tag": "place_children:root",
            "seq_pair_macros": 3,
            "macros": [
                {
                    "name": "m",
                    "w": 10,
                    "h": 20,
                    "x": 0,
                    "y": 0,
                    "fixed": 0,
                    "type": "macro",
                    "wi": [[10, 10], [20, 20]],
                    "hi": [[20, 20], [10, 10]],
                    "area": 200,
                },
                {
                    "name": "s",
                    "w": 5,
                    "h": 5,
                    "x": 0,
                    "y": 0,
                    "fixed": 0,
                    "type": "std",
                    "wi": [[4, 8]],
                    "hi": [[3, 6]],
                    "area": 25,
                },
                {
                    "name": "b",
                    "w": 3,
                    "h": 4,
                    "x": 7,
                    "y": 8,
                    "fixed": 1,
                    "type": "blockage",
                    "wi": [],
                    "hi": [],
                    "area": 12,
                },
                {
                    "name": "io",
                    "w": 100,
                    "h": 100,
                    "x": 0,
                    "y": 0,
                    "fixed": 1,
                    "type": "io",
                    "wi": [],
                    "hi": [],
                    "area": 0,
                },
            ],
        }
        self.assertEqual(
            dump_to_problems.blocks_of(record),
            [
                ("R", "m", [(10, 20), (20, 10)]),
                # resizeRandomly's area: min width times max height.
                ("S", "s", [(4, 8, 24)]),
                ("F", "b", 7, 8, 3, 4),
            ],
        )


class Table(unittest.TestCase):
    def test_block_names_are_dropped(self):
        lines = make_table.anonymize("P x 10 20 2\nB u0/r0 R 1 1 2\nB foo S 1 1 2 3\n")
        self.assertEqual(lines, ["P x 10 20 2", "B b0 R 1 1 2", "B b1 S 1 1 2 3"])


if __name__ == "__main__":
    unittest.main()
