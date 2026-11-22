#!/usr/bin/env python3
"""Unit tests for spelling `/` in escaped netlist names."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slash_names import TOKEN, slash_names  # noqa: E402

NETLIST = """module BlockA (clock, din);
 input clock;
 input [1:0] din;
 wire \\u_core/_089_ ;
 wire \\din_r[0] ;
 INVx1_ASAP7_75t_R \\u_core/_180_  (.A(\\u_core/_089_ ),
    .Y(\\din_r[0] ));
 DFFHQNx1_ASAP7_75t_R \\u_core/lane[0].u_lane/q[0]$_DFF_P_  (.CLK(clock),
    .D(din[0]));
 BUFx2_ASAP7_75t_R input1 (.A(din[1]));
endmodule
"""


class SlashNamesTest(unittest.TestCase):
    def test_slash_spelled_in_escaped_names_only(self):
        out, n = slash_names(NETLIST)
        self.assertEqual(n, 3)
        self.assertIn("\\u_core__SL___180_  (.A(\\u_core__SL___089_ ),", out)
        self.assertIn("\\u_core__SL__lane[0].u_lane__SL__q[0]$_DFF_P_  (", out)
        self.assertIn("\\din_r[0] ", out)
        self.assertIn("BUFx2_ASAP7_75t_R input1 (.A(din[1]));", out)
        self.assertNotIn("/", out)

    def test_reversible(self):
        out, _ = slash_names(NETLIST)
        self.assertEqual(out.replace(TOKEN, "/"), NETLIST)

    def test_token_already_present_is_refused(self):
        with self.assertRaisesRegex(ValueError, "already holds __SL__"):
            slash_names(NETLIST + "wire \\a__SL__b ;\n")

    def test_no_slash_no_change(self):
        text = "module m; wire \\a[0] ; endmodule\n"
        self.assertEqual(slash_names(text), (text, 0))


if __name__ == "__main__":
    unittest.main()
