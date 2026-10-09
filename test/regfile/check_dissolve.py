#!/usr/bin/env python3
"""test/regfile's regfile_top after the macro step: the register file dissolved.

The flow saw RegFile as a macro through synthesis and macro placement;
regfile_dissolve.tcl (ORFS patch 0089) then replaced it with its cells.
dissolve_probe.tcl counts what is there; this asserts what should be:

- no RegFile macro is left;
- the core, the cells memories/RegFile.place names, is in the design,
  FIRM, each on a row of its own orientation; bit 0 is never read, so
  its column went with the dead logic and fewer cells than the .place
  lines remain;
- the core's flops are not dont_touch (CTS rewires their clock pins),
  some of its other cells and nets are;
- the periphery, the address decode, is left unplaced for global
  placement, none of it FIRM.
"""

import json
import sys
import unittest

PROBE = None


class Dissolved(unittest.TestCase):
    def setUp(self):
        with open(PROBE) as f:
            self.p = json.load(f)

    def test_macro_gone(self):
        self.assertEqual(self.p["macros"], 0)

    def test_core_firm_on_rows(self):
        p = self.p
        self.assertGreater(p["core"], 0)
        self.assertEqual(p["core_firm"], p["core"])
        self.assertEqual(p["core_off_row"], 0)

    def test_dead_column_removed(self):
        self.assertLess(self.p["core"], self.p["place_lines"])

    def test_dont_touch(self):
        p = self.p
        self.assertGreater(p["core_flops"], 0)
        self.assertGreater(p["core_dont_touch"], 0)
        self.assertLessEqual(p["core_dont_touch"], p["core"] - p["core_flops"])
        self.assertGreater(p["internal_nets_dont_touch"], 0)

    def test_periphery_unplaced(self):
        p = self.p
        self.assertGreater(p["periphery"], 0)
        self.assertEqual(p["periphery_placed"], 0)
        self.assertEqual(p["periphery_firm"], 0)


if __name__ == "__main__":
    PROBE = sys.argv.pop(1)
    unittest.main()
