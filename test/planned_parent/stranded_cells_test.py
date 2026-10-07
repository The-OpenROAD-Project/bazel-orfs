"""The parent's legalization hook moves cells out of hard blocks before every legalization.

stranded_cells.tcl moves a few of the miniature parent's placed cells to the
middle of its biggest block, where there is no row, sources
legalize_out_of_blocks.tcl, runs its step and the detailed placement it
wraps. On XSTile the resizer left tens of thousands of cells inside the
blocks and the legaliser failed on the few deepest (DPL-0036); the
miniature's blocks are too shallow for that failure, so this checks the
hook: it is wrapped around ORFS's detailed_placement_helper, its step takes
every stranded cell out of the block, and the placement is legal.
"""

import json
import sys
import unittest


class StrandedCells(unittest.TestCase):
    def setUp(self):
        with open(sys.argv[1]) as f:
            self.r = json.load(f)

    def test_the_cells_start_inside_the_block(self):
        self.assertGreater(self.r["stranded"], 0)
        self.assertEqual(self.r["inside_before"], self.r["stranded"])

    def test_the_hook_wraps_the_legaliser(self):
        self.assertTrue(self.r["wrapped"])

    def test_the_hook_moves_every_stranded_cell_out(self):
        self.assertEqual(self.r["moved"], self.r["stranded"])
        self.assertEqual(self.r["inside_after_hook"], 0)

    def test_the_wrapped_legalization_is_legal(self):
        self.assertTrue(self.r["legal"], self.r["error"])
        self.assertEqual(self.r["inside_after_legalization"], 0)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
