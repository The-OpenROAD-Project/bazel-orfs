#!/usr/bin/env python3
"""Unit tests for the netlist instance-name uniquifier."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uniquify_netlist import uniquify  # noqa: E402


def lines(text):
    return [l + "\n" for l in text.strip("\n").split("\n")]


class UniquifyTest(unittest.TestCase):
    CLEAN = lines("""
module top (a, y);
 input a;
 output y;
 INVx1_ASAP7_75t_R _0001_ (.A(a),
    .Y(y));
endmodule
""")

    def test_a_clean_netlist_is_unchanged(self):
        out, renames = uniquify(self.CLEAN)
        self.assertEqual([], renames)
        self.assertEqual(self.CLEAN, out)

    def test_a_duplicate_is_renamed_not_dropped(self):
        """Dropping one would run a design the power was not reported on."""
        src = lines("""
module top (a, y);
 AND2x2_ASAP7_75t_R _131758_ (.A(clknet_leaf_152_clk_i),
    .Y(n1));
 AND2x2_ASAP7_75t_R _131758_ (.A(clknet_leaf_24_clk_i),
    .Y(n2));
endmodule
""")
        out, renames = uniquify(src)
        self.assertEqual([("top", "_131758_", "_131758__uniq1")], renames)
        self.assertEqual(len(src), len(out))
        self.assertIn("clknet_leaf_24_clk_i", "".join(out))
        self.assertIn("clknet_leaf_152_clk_i", "".join(out))

    def test_the_same_name_in_two_modules_is_not_a_collision(self):
        src = lines("""
module a (x);
 INVx1_ASAP7_75t_R _1_ (.A(x));
endmodule
module b (x);
 INVx1_ASAP7_75t_R _1_ (.A(x));
endmodule
""")
        self.assertEqual([], uniquify(src)[1])

    def test_a_third_occurrence_gets_its_own_name(self):
        src = lines("""
module top (x);
 INVx1_ASAP7_75t_R _1_ (.A(x));
 INVx1_ASAP7_75t_R _1_ (.A(x));
 INVx1_ASAP7_75t_R _1_ (.A(x));
endmodule
""")
        out, renames = uniquify(src)
        self.assertEqual(["_1__uniq1", "_1__uniq2"], [r[2] for r in renames])

    def test_declarations_are_not_mistaken_for_instances(self):
        """`wire foo (` never appears, but `input`/`wire` lines must not
        be rewritten if the pattern ever matched one."""
        src = lines("""
module top (a);
 input a;
 wire n1;
 assign n1 = a;
endmodule
""")
        self.assertEqual(src, uniquify(src)[0])

    def test_an_escaped_name_is_handled(self):
        src = lines("""
module top (x);
 INVx1_ASAP7_75t_R \\inst[0] (.A(x));
 INVx1_ASAP7_75t_R \\inst[0] (.A(x));
endmodule
""")
        self.assertEqual(1, len(uniquify(src)[1]))


if __name__ == "__main__":
    unittest.main()
