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
        included, report, _, _ = gate_stitch.stitch(
            NETLIST, self.rtl, "cm_soc", ["_ASAP7_"]
        )
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
        included, _, _, _ = gate_stitch.stitch(NETLIST, self.rtl, "cm_soc", ["_ASAP7_"])
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


# The parent instantiates its block as a cell; each unit's own netlist,
# hierarchical, defines it and submodules write_verilog named after the
# same RTL (`Leaf`), and instantiates an SRAM it does not define.
BLOCK_GATES = (
    "module Leaf(clock);\n  input clock;\n"
    "  INVx1_ASAP7_75t_R _1_ (.A(clock));\nendmodule\n"
    "module Block(clock);\n  input clock;\n"
    "  Leaf leaf (.clock(clock));\n"
    "  array_8x8 mem (.clk(clock));\n"
    "  RegFile \\inner/rf  (.clock(clock));\nendmodule\n"
)
FILE_GATES = (
    "module Leaf(clock);\n  input clock;\nendmodule\n"
    "module RegFile(clock);\n  input clock;\n"
    "  Leaf leaf (.clock(clock));\nendmodule\n"
)


class GateNetlistTest(StitchTest):
    def stitch(self, gates, netlist=NETLIST):
        return gate_stitch.stitch(netlist, self.rtl, "cm_soc", ["_ASAP7_"], gates)

    def test_units_stop_the_rtl_and_their_srams_come_from_it(self):
        included, report, gates, _ = self.stitch([BLOCK_GATES, FILE_GATES])
        self.assertNotIn("Block", included)  # the block is gates
        self.assertNotIn("Leaf", included)
        self.assertIn("array_8x8", included)  # its SRAM's model
        self.assertIn("Bus", included)
        self.assertEqual(report["gate_units"], {"Block": 2, "RegFile": 2})
        self.assertIn("module Block(", gates[0])
        self.assertIn("module RegFile(", gates[1])

    def test_submodules_renamed_per_unit(self):
        _, _, gates, _ = self.stitch([BLOCK_GATES, FILE_GATES])
        self.assertIn("module Block__Leaf(", gates[0])
        self.assertIn("  Block__Leaf leaf (", gates[0])
        self.assertIn("module RegFile__Leaf(", gates[1])
        self.assertIn("  RegFile__Leaf leaf (", gates[1])
        # instance names, which the SAIF scopes are, stay
        self.assertIn("RegFile \\inner/rf  (", gates[0])

    def test_two_tops_refused(self):
        with self.assertRaisesRegex(ValueError, "tops"):
            self.stitch(
                [BLOCK_GATES + "module Spare(clock);\n  input clock;\nendmodule\n"]
            )

    def test_same_unit_twice_refused(self):
        with self.assertRaises(ValueError) as cm:
            self.stitch([FILE_GATES, FILE_GATES, BLOCK_GATES])
        self.assertEqual(cm.exception.args[0], ["two gate netlists define RegFile"])

    def test_unit_the_parent_defines_refused(self):
        with self.assertRaises(ValueError) as cm:
            self.stitch(
                [BLOCK_GATES, FILE_GATES],
                netlist=NETLIST
                + FILE_GATES.split("module RegFile")[0]
                + "module RegFile(clock);\nendmodule\n",
            )
        self.assertIn(
            "RegFile is defined in the parent netlist too", cm.exception.args[0]
        )

    def test_unit_nothing_instantiates_refused(self):
        with self.assertRaises(ValueError) as cm:
            self.stitch(
                [BLOCK_GATES, FILE_GATES, FILE_GATES.replace("RegFile", "Stray")]
            )
        self.assertEqual(
            cm.exception.args[0], ["gate netlist Stray is instantiated nowhere"]
        )

    def test_main_writes_units_after_the_rtl(self):
        paths = []
        for i, text in enumerate([NETLIST, BLOCK_GATES, FILE_GATES]):
            paths.append(os.path.join(self.dir.name, "n{}.v".format(i)))
            with open(paths[-1], "w") as f:
                f.write(text)
        out = os.path.join(self.dir.name, "out.sv")
        rc = gate_stitch.main(
            [
                "x",
                "--netlist",
                paths[0],
                "--rtl-dir",
                self.dir.name,
                "--top",
                "cm_soc",
                "--cell-suffix",
                "_ASAP7_",
                "--gate-netlist",
                paths[1],
                "--gate-netlist",
                paths[2],
                "--out",
                out,
            ]
        )
        self.assertEqual(rc, 0)
        text = open(out).read()
        self.assertLess(text.index("module Bus"), text.index("module Block("))
        self.assertIn("module RegFile__Leaf(", text)


# One simulation per unit: the SoC's RTL, one unit's netlist swapped in.
# The flow split the block's one clock port into two (clock, clock_b).
SOC_RTL = (
    "module soc(input clock, input [1:0] d, output [1:0] q);\n"
    "  Blk u_blk (.clock(clock), .din(d), .dout(q));\n"
    "endmodule\n"
    "module Blk(\n    input clock,\n    input [1:0] din,\n    output [1:0] dout\n);\n"
    "  Sub u_sub (.clock(clock));\n"
    "  reg [1:0] r;\n  always @(posedge clock) r <= din;\n  assign dout = r;\n"
    "endmodule\n"
    "module Sub(input clock);\nendmodule\n"
)
BLK_GATES = (
    "module Blk (clock, clock_b, din, dout);\n"
    " input clock;\n input clock_b;\n input [1:0] din;\n output [1:0] dout;\n"
    " Sub u_sub (.clock(clock_b));\n"
    " DFFHQNx1_ASAP7_75t_R r (.CLK(clock_b));\n"
    "endmodule\n"
)
PARENT_GATES = (
    "module soc (clock, d, q);\n input clock;\n input [1:0] d;\n output [1:0] q;\n"
    " Blk u_blk (.clock(clock),\n    .clock_b(clock),\n    .din(d),\n    .dout(q));\n"
    "endmodule\n"
)


class PerUnitTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.rtl_path = os.path.join(self.dir.name, "soc.sv")
        with open(self.rtl_path, "w") as f:
            f.write(SOC_RTL)
        self.rtl, _ = gate_stitch.rtl_files([self.rtl_path])

    def tearDown(self):
        self.dir.cleanup()

    def stitch(self, netlist, gates, clocks=("clock", "clock_b")):
        return gate_stitch.stitch(netlist, self.rtl, "soc", ["_ASAP7_"], gates, clocks)

    def test_unit_swapped_into_rtl_with_its_clocks_bridged(self):
        included, report, gates, patched = self.stitch("", [BLK_GATES])
        self.assertEqual(included, ["soc", "Sub"])  # Sub: under the gates, from RTL
        self.assertNotIn("Blk", included)
        self.assertEqual(patched, {})
        text = gates[0]
        self.assertIn("module Blk (clock, din, dout);", text)
        self.assertIn(" wire clock_b;\n assign clock_b = clock;", text)
        self.assertEqual(report["clock_bridges"], ["Blk: netlist ['clock_b'] / RTL []"])

    def test_sub_of_a_unit_still_from_rtl(self):
        _, report, _, _ = self.stitch("", [BLK_GATES])
        self.assertIn("Sub", report["netlist_instantiates_undefined"])

    def test_rtl_unit_under_gate_parent_gets_the_clock_pin(self):
        included, report, _, patched = self.stitch(PARENT_GATES, [])
        self.assertIn("Blk", included)
        self.assertIn("    input clock_b,", patched["Blk"])
        self.assertEqual(report["clock_bridges"], ["Blk: RTL given ['clock_b']"])

    def test_all_gates_need_no_bridge(self):
        _, report, gates, patched = self.stitch(PARENT_GATES, [BLK_GATES])
        self.assertNotIn("clock_bridges", report)
        self.assertIn("module Blk (clock, clock_b, din, dout);", gates[0])

    def test_a_port_that_is_not_the_clock_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            self.stitch("", [BLK_GATES.replace("clock_b", "scan_en")])
        self.assertEqual(
            cm.exception.args[0],
            ["Blk: ports of its netlist and its RTL differ, not at the clock: scan_en"],
        )
        with self.assertRaises(ValueError) as cm:
            self.stitch(PARENT_GATES.replace("clock_b", "scan_en"), [])
        self.assertEqual(
            cm.exception.args[0],
            ["Blk: a netlist connects pins its RTL lacks, not at the clock: scan_en"],
        )

    def test_the_clock_bridged_only_when_declared(self):
        with self.assertRaisesRegex(ValueError, "not at the clock: clock_b"):
            self.stitch("", [BLK_GATES], clocks=("clock",))

    def test_later_rtl_file_wins_and_is_reported(self):
        other = os.path.join(self.dir.name, "sub.sv")
        with open(other, "w") as f:
            f.write("module Sub(input clock, input x);\nendmodule\n")
        rtl, replaced = gate_stitch.rtl_files([self.rtl_path, other])
        self.assertEqual(replaced, ["Sub"])
        self.assertIn("input x", gate_stitch.read_rtl(rtl["Sub"]))


class OverlayTest(unittest.TestCase):
    """The flows' RTL below a root, the simulation's around it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        base = {
            "soc": "module soc(input clock);\n  Tile tile (.clock(clock));\n  Sync s (.clock(clock));\nendmodule\n",
            "Tile": "module Tile(input clock, input unused);\n  Blk u_blk (.clock(clock));\nendmodule\n",
            "Blk": "module Blk(input clock, input dropped);\nendmodule\n",
            "Sync": "module Sync(input clock);\nendmodule\n",
        }
        for name, text in base.items():
            with open(os.path.join(self.dir.name, name + ".sv"), "w") as f:
                f.write(text)
        self.overlay = os.path.join(self.dir.name, "surgered.v")
        with open(self.overlay, "w") as f:
            f.write(
                "module Tile(input clock);\n  Blk u_blk (.clock(clock), .x(1'b0));\n"
                "  Sync s2 (.clock(clock), .tied(1'b0));\nendmodule\n"
                "module Blk(\n  input clock, // output of the surgery\n  input x\n);\n"
                "  Sync s3 (.clock(clock), .tied(1'b1));\nendmodule\n"
                "module Sync(input clock, input tied);\nendmodule\n"
            )

    def tearDown(self):
        self.dir.cleanup()

    def test_overlay_below_the_root_base_above(self):
        base = gate_stitch.rtl_index(self.dir.name)
        rtl, renames = gate_stitch.apply_overlay(base, [self.overlay], "Tile", "soc")
        self.assertEqual(renames, {"Sync": "Sync__Tile"})
        self.assertIn("Sync__Tile s2", gate_stitch.read_rtl(rtl["Tile"]))
        self.assertIn("module Sync__Tile(", gate_stitch.read_rtl(rtl["Sync__Tile"]))
        self.assertEqual(
            gate_stitch.ports(gate_stitch.read_rtl(rtl["Sync"])), {"clock"}
        )
        included, _, _, _ = gate_stitch.stitch("", rtl, "soc", [], [])
        self.assertEqual(sorted(included), ["Blk", "Sync", "Sync__Tile", "Tile", "soc"])

    def test_ports_ignore_comments(self):
        base = gate_stitch.rtl_index(self.dir.name)
        rtl, _ = gate_stitch.apply_overlay(base, [self.overlay], "Tile", "soc")
        self.assertEqual(
            gate_stitch.ports(gate_stitch.read_rtl(rtl["Blk"])), {"clock", "x"}
        )


class PinCheckTest(unittest.TestCase):
    """Every instance against the module it resolves to."""

    TOP = "module top(input clock, input [5:0] d, output [5:0] q);\n  Rf rf (.clock(clock), .a0(d), .q0(q));\nendmodule\n"
    # firtool's style: one declaration, the next names on their own lines
    RF = (
        "module Rf(\n  input        clock,\n  input  [5:0] a0,\n               a1,\n"
        "  output [5:0] q0,\n               q1\n);\nendmodule\n"
    )

    def test_continued_declarations_are_ports(self):
        self.assertEqual(
            gate_stitch.port_decls(self.RF),
            {
                "clock": ("input", 1),
                "a0": ("input", 6),
                "a1": ("input", 6),
                "q0": ("output", 6),
                "q1": ("output", 6),
            },
        )
        net = "module m (a, b, c);\n input [3:0] a, b;\n output c;\nendmodule\n"
        self.assertEqual(gate_stitch.ports(net), {"a", "b", "c"})

    def test_unconnected_input_and_unknown_pin_refused(self):
        _, refused, _ = gate_stitch.check_pins([self.TOP, self.RF])
        self.assertEqual(refused, ["Rf rf: inputs a1 unconnected"])
        _, refused, _ = gate_stitch.check_pins(
            [self.TOP.replace(".q0(q)", ".q9(q)"), self.RF]
        )
        self.assertIn("Rf rf: pins q9 that Rf does not have", refused)

    def test_tie_connects_it_by_name(self):
        out, refused, made = gate_stitch.check_pins(
            [self.TOP, self.RF], {"Rf": {"a1": "6'd0"}}
        )
        self.assertEqual(refused, [])
        self.assertIn("Rf rf (.a1(6'd0), .clock(clock)", out[0])
        self.assertEqual(made, ["Rf rf: a1=6'd0"])

    def test_unconnected_output_allowed(self):
        _, refused, _ = gate_stitch.check_pins(
            [self.TOP.replace(", .q0(q)", ""), self.RF], {"Rf": {"a1": "0"}}
        )
        self.assertEqual(refused, [])


if __name__ == "__main__":
    unittest.main()
