"""timing_table on two hand-written dumps."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timing_table  # noqa: E402

BOUNDARIES = """module top/a master A in 10 reg_in 8 out 6 reg_out 6 cells 100 flops 40 empty_stages 8
module top/a/inner master Inner in 4 reg_in 0 out 4 reg_out 0 cells 20 flops 4 empty_stages 0
module top/b master B in 2 reg_in 0 out 2 reg_out 0 cells 50 flops 10 empty_stages 0
"""
PATHS = """-120.0 30 top/a/x_reg/D top/a/y_reg/CLK
-80.0 22 top/b/z_reg/D top/a/inner/q_reg/CLK
10.0 8 top/a/inner/r_reg/D top/a/inner/q_reg/CLK
"""


class TableTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp(prefix="timing_table.")
        self.b = os.path.join(d, "b.txt")
        self.p = os.path.join(d, "p.txt")
        with open(self.b, "w") as f:
            f.write(BOUNDARIES)
        with open(self.p, "w") as f:
            f.write(PATHS)

    def test_attribution_and_stats(self):
        mods = timing_table.read_boundaries(self.b)
        paths = timing_table.read_paths(self.p, mods)
        self.assertEqual(paths[0][2:], ("top/a", "top/a"))
        self.assertEqual(paths[1][2:], ("top/b", "top/a/inner"))  # deepest module wins
        rows = {r["module"]: r for r in timing_table.table(mods, paths, 800)}
        self.assertAlmostEqual(rows["top/a"]["registered"], 14 / 16.0)
        self.assertAlmostEqual(rows["top/a"]["empty_stages"], 0.2)
        self.assertEqual(rows["top/a"]["worst_ps"], -120.0)
        self.assertEqual(rows["top/b"]["worst_cross_ps"], -80.0)
        self.assertEqual(rows["top/b"]["crossing"], 1)
        self.assertEqual(rows["top/a/inner"]["worst_ps"], 10.0)

    def test_format_puts_the_worst_first(self):
        mods = timing_table.read_boundaries(self.b)
        rows = timing_table.table(mods, timing_table.read_paths(self.p, mods), 800)
        text = timing_table.format_table(rows, 10).splitlines()
        self.assertTrue(text[1].startswith("top/a "))
        self.assertTrue(text[2].startswith("top/b "))


if __name__ == "__main__":
    unittest.main()
