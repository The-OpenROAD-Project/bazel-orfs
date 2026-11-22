#!/usr/bin/env python3
"""Unit tests for generating a shard's replay."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from replay_gen import generate, module_at  # noqa: E402

RTL = """module soc(input clock, input [3:0] d, output [3:0] q);
  Blk u_blk (.clock(clock), .din(d), .dout(q));
endmodule
module Blk(
  input clock,
  input [3:0] din,
  output [3:0] dout
);
  wire [3:0] mid;
  Sub u_sub (.clock(clock), .a(din), .y(mid));
  Rf u_rf (.clock(clock), .w(mid), .r(dout));
endmodule
module Sub(input clock, input [3:0] a, output [3:0] y);
endmodule
module Rf(input clock, input [3:0] w, output [3:0] r);
endmodule
"""

# The block's netlist: Sub kept, Rf a hardened macro (not defined), a
# second clock pin the flow split off.
NETLIST = """module Blk (clock, clock_b, din, dout);
 input clock;
 input clock_b;
 input [3:0] din;
 output [3:0] dout;
 wire [3:0] mid;
 Sub u_sub (.clock(clock_b),
    .a(din),
    .y(mid));
 Rf u_rf (.clock(clock),
    .w(mid),
    .r(dout));
endmodule
module Sub (clock, a, y);
 input clock;
 input [3:0] a;
 output [3:0] y;
 INVx1_ASAP7_75t_R _1_ (.A(a[0]), .Y(y[0]));
endmodule
"""


def gen(**kw):
    args = dict(
        name="replay_blk",
        top="Blk",
        netlist=NETLIST,
        rtl=RTL,
        capture_scope="TOP.soc.rtl.u_blk",
        children=[],
        clock_ports=["clock", "clock_b"],
        record_stubs=bool(kw.get("children")),
    )
    args.update(kw)
    return generate(**args)


class ReplayGenTest(unittest.TestCase):
    def test_unit_whole_with_its_hardened_child_a_stub(self):
        sv, cc, report, net = gen(children=[("u_rf", "TOP.soc.rtl.u_blk.rtl.u_rf")])
        self.assertIn("  Blk dut (", sv)
        self.assertIn(".clock_b(p", sv)  # tied to the RTL's clock
        self.assertEqual(report["clock_tied"], ["clock_b"])
        self.assertIn("module Rf (clock, r, w);", sv)
        self.assertRegex(sv, r"assign r = replay_blk\.p\d+;")
        self.assertRegex(sv, r"assign p\d+ = dut\.u_rf\.w;")
        self.assertIn('"TOP.soc.rtl.u_blk.rtl.u_rf.r"', cc)
        self.assertIn('"TOP.soc.rtl.u_blk.din"', cc)
        self.assertIn("module Sub (", net)  # the kept module stays

    def test_kept_module_cut_out_and_replayed_alone(self):
        sv, _, _, net = gen(children=[("u_sub", "TOP.soc.rtl.u_blk.rtl.u_sub")])
        self.assertIn("module Sub (a, clock, y);", sv)  # its stub
        self.assertNotIn("module Sub (", net)  # its gates gone from the rest
        sv, cc, report, net = gen(
            path="u_sub", capture_scope="TOP.soc.rtl.u_blk.rtl.u_sub"
        )
        self.assertIn("  Sub dut (", sv)
        self.assertEqual(report["path"], "u_sub")
        self.assertIn("INVx1_ASAP7_75t_R", net)
        self.assertNotIn("module Blk", net)

    def test_cut_that_is_no_kept_boundary_refused(self):
        with self.assertRaisesRegex(
            ValueError, "not a module of its own in the netlist"
        ):
            gen(path="u_rf")  # a macro in the netlist, no module of its own
        with self.assertRaisesRegex(ValueError, "not a module of its own"):
            gen(path="u_nope")

    def test_cut_rtl_input_the_netlist_lacks_dropped(self):
        # an RTL input the netlist does not use: no pin of the stub, reported
        rtl = RTL.replace(
            "module Sub(input clock, input [3:0] a, output [3:0] y);",
            "module Sub(input clock, input [3:0] a, input e, output [3:0] y);",
        )
        sv, _, report, _ = gen(rtl=rtl, children=[("u_sub", "S")])
        self.assertIn("module Sub (a, clock, y);", sv)
        self.assertEqual(report["stubs"]["u_sub"]["dropped"], ["e"])
        # the module alone from the capture: refused, as before
        with self.assertRaisesRegex(ValueError, "differ, not at the clock: e"):
            gen(rtl=rtl, path="u_sub", capture_scope="S")

    def test_cut_with_other_outputs_refused(self):
        # an RTL output synthesis took away (nothing loads it): dropped
        rtl = RTL.replace(
            "module Sub(input clock, input [3:0] a, output [3:0] y);",
            "module Sub(input clock, input [3:0] a, output e, output [3:0] y);",
        )
        _, _, report, _ = gen(rtl=rtl, children=[("u_sub", "S")])
        self.assertEqual(report["stubs"]["u_sub"]["dropped"], ["e"])
        # a punched output: refused
        net = PUNCHED.replace(" input net7_0;", " output net7_0;")
        with self.assertRaisesRegex(
            ValueError, "differ: netlist output net7_0 its RTL lacks"
        ):
            gen(netlist=net, children=[("u_sub", "S")])

    def test_ports_alike_no_punched_ports(self):
        sv, cc, report, _ = gen(children=[("u_sub", "S")])
        self.assertEqual(report["stubs"]["u_sub"]["punched"], {})
        self.assertEqual(report["bits_recorded"], 0)
        self.assertNotIn("kRec,", cc)
        # every stub port traced for a level 2 all the same
        self.assertIn('{"TOP.replay_blk.dut.u_sub", "a", ', cc)


# Sub as a hierarchical global route leaves it: Sub's own output y[0]
# buffered in the parent and fed back in through a punched port, net7_0,
# and Blk's din[2] in through another, named like an RTL net; inside,
# their loads use the punched ports. Sub's clock arrives on a clock-tree
# leaf.
PUNCHED = """module Blk (clock, clock_b, din, dout);
 input clock;
 input clock_b;
 input [3:0] din;
 output [3:0] dout;
 wire [3:0] mid;
 wire n1, n2, n3;
 BUFx3_ASAP7_75t_R place1 (.A(mid[0]), .Y(n1));
 BUFx3_ASAP7_75t_R place2 (.A(n1), .Y(n2));
 BUFx2_ASAP7_75t_R place3 (.A(din[2]), .Y(n3));
 Sub u_sub (.clknet_0_clock(clock_b),
    .a(din),
    .y(mid),
    .net7_0(n2),
    .\\din.x_2_ (n3));
 Rf u_rf (.clock(clock),
    .w(mid),
    .r(dout));
endmodule
module Sub (clknet_0_clock, a, y, net7_0, \\din.x_2_ );
 input clknet_0_clock;
 input [3:0] a;
 output [3:0] y;
 input net7_0;
 input \\din.x_2_ ;
 XOR2xp5_ASAP7_75t_R _1_ (.A(net7_0), .B(\\din.x_2_ ), .Y(y[1]));
endmodule
"""


class TwoLevelTest(unittest.TestCase):
    def level1(self, **kw):
        return gen(
            netlist=PUNCHED,
            children=[("u_sub", "TOP.soc.rtl.u_blk.rtl.u_sub")],
            clock_nets=["clknet_*"],
            **kw
        )

    def test_level1_records_the_punched_ports(self):
        sv, cc, report, net = self.level1()
        stub = report["stubs"]["u_sub"]
        self.assertEqual(stub["scope"], "TOP.replay_blk.dut.u_sub")
        self.assertEqual(stub["punched"], {"\\din.x_2_": "pp_0", "net7_0": "pp_1"})
        self.assertEqual(stub["dropped"], [])
        # an escaped name keeps its space, in the header, the declaration
        # and the hierarchical reference
        self.assertIn("module Sub (a, y, \\din.x_2_ , clknet_0_clock, net7_0);", sv)
        self.assertIn("  input \\din.x_2_ ;", sv)
        self.assertRegex(sv, r"assign p\d+ = dut\.u_sub\.\\din\.x_2_ ;")
        self.assertRegex(sv, r"assign p\d+ = dut\.u_sub\.net7_0;")
        # recorded, not compared: no capture name of its own
        self.assertRegex(cc, r'"TOP.replay_blk.dut.u_sub.pp_1", "p\d+", 1, kRec,')
        self.assertEqual(report["bits_recorded"], 2)
        # the RTL inputs compared with the capture
        # a diagnostic, not required to match unless --strict-stub-inputs
        self.assertRegex(cc, r'"TOP.soc.rtl.u_blk.rtl.u_sub.a", "p\d+", 4, kStubIn,')
        # the unit's own outputs, proof obligation (A)
        self.assertRegex(cc, r'"TOP.soc.rtl.u_blk.dout", "p\d+", 4, kOut,')
        # the stub's RTL clock, which its netlist reaches on a leaf: the
        # replay's clock under the RTL's name
        self.assertIn('{"TOP.replay_blk.dut.u_sub", "clock", 0},', cc)
        self.assertIn('{"TOP.replay_blk.dut.u_sub", "pp_1", ', cc)
        self.assertNotIn("module Sub (", net)

    def test_level2_reads_the_punched_ports_from_level1(self):
        _, _, report, _ = self.level1()
        stub = report["stubs"]["u_sub"]
        sv, cc, report, net = gen(
            netlist=PUNCHED,
            path="u_sub",
            capture_scope=stub["scope"],
            stub_map=stub,
            clock_nets=["clknet_*"],
        )
        self.assertIn("  Sub dut (.\\din.x_2_ (p0), ", sv)
        self.assertEqual(report["punched"], stub["punched"])
        self.assertRegex(cc, r'"TOP.replay_blk.dut.u_sub.pp_1", "p\d+", 1, kIn,')
        self.assertRegex(cc, r'"TOP.replay_blk.dut.u_sub.pp_0", "p\d+", 1, kIn,')
        self.assertRegex(cc, r'"TOP.replay_blk.dut.u_sub.y", "p\d+", 4, kOut,')
        self.assertRegex(cc, r'"TOP.replay_blk.dut.u_sub.clock", "p\d+", 1, kClock,')
        self.assertIn("module Sub (", net)

    def test_level2_refusals(self):
        _, _, report, _ = self.level1()
        stub = report["stubs"]["u_sub"]
        kw = dict(netlist=PUNCHED, path="u_sub", clock_nets=["clknet_*"])
        # from the RTL capture, with no level 1: refused by name
        with self.assertRaisesRegex(
            ValueError, r"differ, not at the clock: \S*din.x_2_, net7_0"
        ):
            gen(capture_scope="S", **kw)
        partial = dict(stub, punched={"net7_0": "pp_1"})
        with self.assertRaisesRegex(
            ValueError, r"punched inputs level 1 did not record: \S*din.x_2_'"
        ):
            gen(capture_scope=stub["scope"], stub_map=partial, **kw)
        with self.assertRaisesRegex(ValueError, "recorded its stub at TOP.replay_blk"):
            gen(capture_scope="TOP.other.dut.u_sub", stub_map=stub, **kw)

    def test_module_at(self):
        self.assertEqual(module_at(RTL, "soc", "u_blk/u_sub"), "Sub")
        self.assertIsNone(module_at(RTL, "soc", "u_blk/u_x"))


class OneLevelTest(unittest.TestCase):
    def test_without_record_stubs_the_one_level_harness(self):
        from replay_gen import _HARNESS_ONE_LEVEL

        _, cc, _, _ = gen(record_stubs=False)
        self.assertTrue(cc.startswith(_HARNESS_ONE_LEVEL.split("@NAME@")[0]))
        self.assertNotIn("--stubs-vcd", cc)


# What drives each bit, read from a netlist: MemBlock's two shapes (a
# unit output on tie cells, a stub pin on nets nothing drives) and the
# ways a connection is written.
FIXED = """module Unit (clock, a, mask, flag, k, out);
 input clock;
 input [1:0] a;
 output [3:0] mask;
 output flag;
 output [1:0] k;
 output [2:0] out;
 wire _213994_;
 wire _213995_;
 wire [1:0] w;
 wire z;
 TIEHIx1_ASAP7_75t_R _1_ (.H(mask[3]));
 TIEHIx1_ASAP7_75t_R _2_ (.H(mask[2]));
 TIELOx1_ASAP7_75t_R _3_ (.L(mask[1]));
 INVx1_ASAP7_75t_R _4_ (.A(a[0]),
    .Y(mask[0]));
 assign flag = 1'b1;
 assign k = {z, w[0]};
 TIELOx1_ASAP7_75t_R _5_ (.L(z));
 BUFx2_ASAP7_75t_R _6_ (.A(a[1]),
    .Y(w[0]));
 Sq u_sq (.n({_213995_, _213995_, _213994_, a[1], 1'b0}),
    .\\b.c (w[1]),
    .y(out));
endmodule
module Sq (n, \\b.c , y);
 input [4:0] n;
 input \\b.c ;
 output [2:0] y;
endmodule
"""


class ModuleNetsTest(unittest.TestCase):
    def setUp(self):
        from replay_gen import ModuleNets, _netlist_modules

        self.nets = ModuleNets(_netlist_modules(FIXED), "Unit")

    def fixed(self, port, width):
        return [self.nets.fixed(b) for b in self.nets.port_bits(port, width)]

    def pin(self, pin):
        from replay_gen import expr_bits

        e = self.nets.instances["u_sq"][1][pin]
        return [self.nets.fixed(b) for b in reversed(expr_bits(e, self.nets.ranges))]

    def test_tie_cells_per_bit_select(self):
        self.assertEqual(
            self.fixed("mask", 4), [None, ("tie lo", 0), ("tie hi", 1), ("tie hi", 1)]
        )

    def test_constant_assign(self):
        self.assertEqual(self.fixed("flag", 1), [("const", 1)])

    def test_assign_of_a_concatenation_followed(self):
        # k[1] is z, a tie; k[0] is w[0], a buffer's output
        self.assertEqual(self.fixed("k", 2), [None, ("tie lo", 0)])

    def test_undriven_nets_in_a_concatenation(self):
        # least significant first: 1'b0, a[1], _213994_, _213995_ twice
        self.assertEqual(
            self.pin("n"),
            [
                ("const", 0),
                None,
                ("undriven", None),
                ("undriven", None),
                ("undriven", None),
            ],
        )

    def test_escaped_pin_on_a_bit_nothing_drives(self):
        # w[1]: declared, never driven
        self.assertEqual(self.pin("\\b.c"), [("undriven", None)])

    def test_submodule_output_drives(self):
        self.assertEqual(self.fixed("out", 3), [None, None, None])


class NotComparedTest(unittest.TestCase):
    def test_level1_lists_the_bits_the_netlist_fixes(self):
        rtl = (
            "module Top(input clock, input [1:0] a, output [3:0] mask, output flag,"
            " output [1:0] k, output [2:0] out);\nendmodule\n"
            "module Unit(input clock, input [1:0] a, output [3:0] mask, output flag,"
            " output [1:0] k, output [2:0] out);\n"
            "  Sq u_sq (.n(0), .y(out));\nendmodule\n"
            "module Sq(input [4:0] n, output [2:0] y);\nendmodule\n"
        )
        net = FIXED.replace(
            "module Sq (n, \\b.c , y);\n input [4:0] n;\n input \\b.c ;",
            "module Sq (n, y);\n input [4:0] n;",
        ).replace(" .\\b.c (w[1]),\n", "")
        _, cc, report, _ = generate(
            name="r",
            top="Unit",
            netlist=net,
            rtl=rtl,
            capture_scope="C",
            children=[("u_sq", "C.rtl.u_sq")],
            clock_ports=["clock"],
            record_stubs=True,
        )
        got = sorted(
            (n["signal"], n["bit"], n["reason"]) for n in report["not_compared"]
        )
        self.assertEqual(
            got,
            [
                ("C.flag", 0, "const"),
                ("C.k", 1, "tie lo"),
                ("C.mask", 1, "tie lo"),
                ("C.mask", 2, "tie hi"),
                ("C.mask", 3, "tie hi"),
                ("C.rtl.u_sq.n", 0, "const"),
                ("C.rtl.u_sq.n", 2, "undriven"),
                ("C.rtl.u_sq.n", 3, "undriven"),
                ("C.rtl.u_sq.n", 4, "undriven"),
            ],
        )
        self.assertIn('"tie hi", 1},', cc)
        self.assertIn('"undriven", -1},', cc)
        # the one-level harness has no such table, and compares every bit
        _, cc1, report1, _ = generate(
            name="r",
            top="Unit",
            netlist=net,
            rtl=rtl,
            capture_scope="C",
            children=[],
            clock_ports=["clock"],
        )
        self.assertNotIn("not_compared", report1)
        self.assertNotIn("kExempt", cc1)


class CountOutputsTest(unittest.TestCase):
    def test_only_the_flagged_harness_changes(self):
        _, _, report, _ = gen(
            netlist=PUNCHED,
            children=[("u_sub", "S")],
            clock_nets=["clknet_*"],
            record_stubs=True,
        )
        stub = report["stubs"]["u_sub"]
        kw = dict(
            netlist=PUNCHED,
            path="u_sub",
            capture_scope=stub["scope"],
            stub_map=stub,
            clock_nets=["clknet_*"],
        )
        sv, cc, _, net = gen(**kw)
        sv2, cc2, report2, net2 = gen(count_outputs=True, **kw)
        self.assertEqual((sv, net), (sv2, net2))
        self.assertNotIn("--outputs-json=", cc)
        self.assertNotIn("@COUNT", cc)
        self.assertIn("--outputs-json=", cc2)
        self.assertIn("outputs differing from the RTL", cc2)
        self.assertTrue(report2["count_outputs"])

    def test_refused_in_a_one_level_replay(self):
        with self.assertRaisesRegex(ValueError, "two-level replay's harness"):
            gen(count_outputs=True)


class FromResetTest(unittest.TestCase):
    RTL_RESET = RTL.replace(
        "module Sub(input clock, input [3:0] a, output [3:0] y);",
        "module Sub(input clock, input reset, input [3:0] a, output [3:0] y);",
    )
    NET_RESET = PUNCHED.replace(
        "module Sub (clknet_0_clock, a, y,", "module Sub (clknet_0_clock, reset, a, y,"
    ).replace(
        " input [3:0] a;\n output [3:0] y;",
        " input reset;\n input [3:0] a;\n output [3:0] y;",
    )

    def level2(self, **kw):
        _, _, report, _ = gen(
            netlist=self.NET_RESET,
            rtl=self.RTL_RESET,
            children=[("u_sub", "S")],
            clock_nets=["clknet_*"],
            record_stubs=True,
        )
        stub = report["stubs"]["u_sub"]
        return gen(
            netlist=self.NET_RESET,
            rtl=self.RTL_RESET,
            path="u_sub",
            capture_scope=stub["scope"],
            stub_map=stub,
            clock_nets=["clknet_*"],
            **kw
        )

    def test_only_the_flagged_harness_changes(self):
        sv, cc, _, net = self.level2()
        sv2, cc2, report2, net2 = self.level2(compare_from_reset=True)
        self.assertEqual((sv, net), (sv2, net2))
        self.assertNotIn("@RESET", cc)
        self.assertNotIn("@RESET", cc2)
        self.assertNotIn("--from-reset-json=", cc)
        self.assertIn("--from-reset-json=", cc2)
        self.assertEqual(
            report2["compare_from_reset"], "TOP.replay_blk.dut.u_sub.reset"
        )
        # the reset's row in the table is the one the harness watches
        row = [
            i
            for i, line in enumerate(
                cc2.split("const Sig kSigs[] = {")[1]
                .split("};")[0]
                .strip()
                .splitlines()
            )
            if '"TOP.replay_blk.dut.u_sub.reset"' in line
        ]
        self.assertIn("const std::size_t kReset = {};".format(row[0]), cc2)
        # with --count-outputs too: both inserted
        _, cc3, _, _ = self.level2(compare_from_reset=True, count_outputs=True)
        self.assertIn("--from-reset-json=", cc3)
        self.assertIn("--outputs-json=", cc3)

    def test_refused_without_a_reset_input(self):
        _, _, report, _ = gen(
            netlist=PUNCHED,
            children=[("u_sub", "S")],
            clock_nets=["clknet_*"],
            record_stubs=True,
        )
        stub = report["stubs"]["u_sub"]
        with self.assertRaisesRegex(ValueError, "no reset input reset"):
            gen(
                netlist=PUNCHED,
                path="u_sub",
                capture_scope=stub["scope"],
                stub_map=stub,
                clock_nets=["clknet_*"],
                compare_from_reset=True,
            )

    def test_refused_in_a_one_level_replay(self):
        with self.assertRaisesRegex(ValueError, "two-level replay's harness"):
            gen(
                rtl=self.RTL_RESET.replace(
                    "module Blk(\n  input clock,",
                    "module Blk(\n  input clock,\n  input reset,",
                ),
                netlist=NETLIST.replace(
                    "module Blk (clock,", "module Blk (clock, reset,"
                ).replace(
                    " input clock;\n input clock_b;",
                    " input clock;\n input reset;\n input clock_b;",
                ),
                compare_from_reset=True,
            )


if __name__ == "__main__":
    unittest.main()
