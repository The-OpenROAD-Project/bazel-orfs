#!/usr/bin/env python3
"""After the dissolve, STA sees every register clocked.

regfile_dissolve.tcl (ORFS patch 0089) replaces the register file macro
with its cells inside the macro's module. A cell connected to the flat
clock net but not to the module's clock net is invisible to STA's clock
propagation: its flops are no endpoints until CTS rewires them, and
global placement and repair at place never see the paths through the
array. clocked_probe.tcl counts the registers and the clocked ones.
"""

import json
import sys
import unittest

PROBE = None


class Clocked(unittest.TestCase):
    def test_every_register_clocked(self):
        with open(PROBE) as f:
            p = json.load(f)
        self.assertGreater(p["registers"], 0)
        self.assertEqual(p["clocked"], p["registers"])


if __name__ == "__main__":
    PROBE = sys.argv.pop(1)
    unittest.main()
