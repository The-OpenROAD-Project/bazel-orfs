#!/usr/bin/env python3
"""gate_stitch on a synthetic SoC: uncore in, core out, blocks and memories in."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_stitch  # noqa: E402

RTL = {
    "cm_soc": "module cm_soc(input clock);\n  Bus bus (.clock(clock));\n  Core core (.clock(clock));\nendmodule\n",
    "Bus": '`include "defs.svh"\nmodule Bus(input clock);\nendmodule\n',
    "Core": "module Core(input clock);\n  Block blk (.clock(clock));\n  Alu alu (.clock(clock));\nendmodule\n",
    "Block": "module Block(input clock);\n  array_8x8 mem (.clk(clock));\n  Leaf leaf (.clock(clock));\nendmodule\n",
    "Leaf": "module Leaf(input clock);\nendmodule\n",
    "Alu": "module Alu(input clock);\nendmodule\n",
    "array_8x8": "module array_8x8(input clk);\n  reg [7:0] Memory[0:7];\nendmodule\n",
}

NETLIST = (
    "module Core(clock);\n  input clock;\n"
    "  Block blk (.clock(clock));\n"
    "  array_8x8 mem2 (.clk(clock));\n"
    "  NAND2xp33_ASAP7_75t_R _001_ (.A(clock));\n"
    "endmodule\n"
)


class StitchTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        for name, text in RTL.items():
            with open(os.path.join(self.dir.name, name + ".sv"), "w") as f:
                f.write(text)
        self.rtl = gate_stitch.rtl_index(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_uncore_in_core_out_blocks_and_memories_in(self):
        included, report = gate_stitch.stitch(NETLIST, self.rtl, "cm_soc", ["_ASAP7_"])
        self.assertIn("cm_soc", included)
        self.assertIn("Bus", included)
        self.assertNotIn("Core", included)  # the netlist defines it
        self.assertNotIn("Alu", included)  # inside the core, synthesized away
        self.assertIn("Block", included)
        self.assertIn("Leaf", included)  # the block's own subtree
        self.assertIn("array_8x8", included)
        self.assertEqual(report["uncore_modules"], 2)
        self.assertEqual(report["block_and_memory_modules"], 3)
        self.assertEqual(report["cells_seen"], ["NAND2xp33_ASAP7_75t_R"])

    def test_children_come_before_parents(self):
        included, _ = gate_stitch.stitch(NETLIST, self.rtl, "cm_soc", ["_ASAP7_"])
        self.assertLess(included.index("Bus"), included.index("cm_soc"))
        self.assertLess(included.index("Leaf"), included.index("Block"))

    def test_unknown_module_is_loud(self):
        bad = NETLIST.replace("array_8x8 mem2", "sram_ghost mem2")
        with self.assertRaises(ValueError) as cm:
            gate_stitch.stitch(bad, self.rtl, "cm_soc", ["_ASAP7_"])
        self.assertEqual(cm.exception.args[0], ["sram_ghost"])

    def test_main_strips_includes_and_writes_report(self):
        netlist = os.path.join(self.dir.name, "core.v")
        with open(netlist, "w") as f:
            f.write(NETLIST)
        out = os.path.join(self.dir.name, "out.sv")
        report = os.path.join(self.dir.name, "r.json")
        rc = gate_stitch.main(
            [
                "x",
                "--netlist",
                netlist,
                "--rtl-dir",
                self.dir.name,
                "--top",
                "cm_soc",
                "--cell-suffix",
                "_ASAP7_",
                "--out",
                out,
                "--report",
                report,
            ]
        )
        self.assertEqual(rc, 0)
        text = open(out).read()
        self.assertNotIn("`include", text)
        self.assertIn("module Bus", text)
        self.assertNotIn("module Core", text)
        self.assertTrue(os.path.exists(report))


if __name__ == "__main__":
    unittest.main()
