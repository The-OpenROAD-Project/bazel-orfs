"""critical_cut.py: paths above the period union the modules they touch; a module
above the fold depth counts only its own cells, one at it its subtree."""

import unittest

import critical_cut

CROSSINGS = [
    "2300\tparent\tX:a:b:2300\tM=core/ctrl/dispatch,core/ctrl/decode\n",
    "2100\tparent\tX:a:b:2100\tM=core/ctrl/decode,core/int/iq\n",
    "2050\tB->X\tB:a:b:1\tX:c:d:1\tM=core/vec/iq,core/vec/pipe\n",
    "1900\tparent\tX:a:b:1900\tM=core/ctrl/decode,core/vec/iq\n",
]
AREA = [
    "core\t100\t1000.0\n",
    "core/ctrl\t40\t400.0\n",
    "core/ctrl/dispatch\t10\t100.0\n",
    "core/ctrl/decode\t20\t200.0\n",
    "core/int\t30\t300.0\n",
    "core/int/iq\t30\t300.0\n",
    "core/vec\t30\t300.0\n",
    "core/vec/iq\t10\t100.0\n",
    "core/vec/pipe\t5\t50.0\n",
]


class Carve(unittest.TestCase):
    def test_components(self):
        paths = critical_cut.read_paths(CROSSINGS, 2000, 3)
        self.assertEqual(len(paths), 3)  # 1900 is below the period
        comps, pair = critical_cut.carve(paths, critical_cut.read_area(AREA), 2000, 3)
        self.assertEqual(len(comps), 2)
        big = comps[0]
        self.assertEqual(
            big["modules"], {"core/ctrl/dispatch", "core/ctrl/decode", "core/int/iq"}
        )
        self.assertEqual(big["um2"], 600.0)
        self.assertEqual(big["paths"], 2)
        self.assertEqual(big["excess"], 400)
        self.assertEqual(comps[1]["um2"], 150.0)
        self.assertEqual(pair[("core/ctrl/decode", "core/int/iq")], [1, 100])

    def test_fold_and_nesting(self):
        paths = critical_cut.read_paths(CROSSINGS, 2000, 2)
        comps, _ = critical_cut.carve(paths, critical_cut.read_area(AREA), 2000, 2)
        # folded to two levels: ctrl+int in one, vec alone, each its subtree
        self.assertEqual(sorted(c["um2"] for c in comps), [300.0, 700.0])

    def test_glue_counts_its_own_cells(self):
        # a cell directly in core puts "core" on the path: its own cells
        # (1000 less ctrl, int and vec: none here), not the whole design
        paths = critical_cut.read_paths(
            ["2400\tparent\tX:a:b:1\tM=core,core/ctrl/decode\n"], 2000, 3
        )
        comps, _ = critical_cut.carve(paths, critical_cut.read_area(AREA), 2000, 3)
        self.assertEqual(comps[0]["um2"], 0.0 + 200.0)


if __name__ == "__main__":
    unittest.main()
