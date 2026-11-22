#!/usr/bin/env python3
"""Unit tests for wrapping units of an RTL simulation for a capture."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capture_wrap import wrap  # noqa: E402

RTL = """module top(input clock, input [1:0] d, output [1:0] q);
  Blk u_blk (.clock(clock), .din(d), .dout(q));
endmodule
module Blk (
    input clock,
    input [1:0] din,  // the data
    output [1:0] dout
);
  reg [1:0] r;
  always @(posedge clock) r <= din;
  assign dout = r;
endmodule
"""


class WrapTest(unittest.TestCase):
    def test_unit_behind_a_wrapper_of_its_ports(self):
        out = wrap(RTL, ["Blk"])
        self.assertIn("module Blk__rtl (", out)
        self.assertIn("  Blk__rtl rtl (.clock(clock), .din(din), .dout(dout));", out)
        self.assertIn("  Blk u_blk (", out)  # the instance is the wrapper's
        wrapper = out[out.index("module Blk (") :]
        self.assertNotIn("reg", wrapper)
        self.assertEqual(out.count("endmodule"), 3)

    def test_continued_declarations_wrapped_whole(self):
        rtl = (
            "module Rf(\n  input        clock,\n  input  [5:0] a0,\n               a1,\n"
            "  output [5:0] q0,\n               q1\n);\nendmodule\n"
        )
        self.assertIn(
            "Rf__rtl rtl (.a0(a0), .a1(a1), .clock(clock), .q0(q0), .q1(q1));",
            wrap(rtl, ["Rf"]),
        )

    def test_top_wrapped_too(self):
        out = wrap(RTL, ["top", "Blk"])
        self.assertIn("module top__rtl(", out)
        self.assertIn("top__rtl rtl (.clock(clock), .d(d), .q(q));", out)

    def test_missing_and_non_ansi_refused(self):
        with self.assertRaisesRegex(ValueError, "no module Nope"):
            wrap(RTL, ["Nope"])
        with self.assertRaisesRegex(ValueError, "without its port declarations"):
            wrap("module m (a, b);\n  input a;\n  output b;\nendmodule\n", ["m"])


if __name__ == "__main__":
    unittest.main()
