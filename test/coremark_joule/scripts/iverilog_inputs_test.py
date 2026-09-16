"""Tests for iverilog_inputs.py — the netlist and its SDF must agree."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from iverilog_inputs import REPLACEMENT, drop_celltypes, drop_cond, drop_timingcheck, rewrite_sdf, rewrite_verilog, safe  # noqa: E402


class TestVerilog(unittest.TestCase):
    def test_renames_an_escaped_name_with_a_dot(self):
        out, n = rewrite_verilog("  BUFx24 \\clkbuf_3_7_0_u_core.clk (.A(x));")
        self.assertEqual(n, 1)
        self.assertIn("\\clkbuf_3_7_0_u_core%sclk" % REPLACEMENT, out)
        self.assertNotIn("u_core.clk", out)

    def test_leaves_escaped_names_without_dots_alone(self):
        """Thousands of those exist; rewriting them would be pure churn."""
        src = "  AND2 \\some$paramod_thing (.A(x));"
        out, n = rewrite_verilog(src)
        self.assertEqual((out, n), (src, 0))

    def test_leaves_unescaped_identifiers_alone(self):
        src = "  wire foo_bar; assign y = a.b;"
        out, n = rewrite_verilog(src)
        self.assertEqual((out, n), (src, 0))


class TestSdf(unittest.TestCase):
    def test_renames_an_escaped_dot(self):
        out, n = rewrite_sdf("(INSTANCE clkbuf_3_7_0_u_core\\.clk)")
        self.assertEqual(n, 1)
        self.assertEqual(out, "(INSTANCE clkbuf_3_7_0_u_core%sclk)" % REPLACEMENT)

    def test_leaves_a_plain_instance_alone(self):
        src = "(INSTANCE u_core/alu_i)"
        self.assertEqual(rewrite_sdf(src), (src, 0))

    def test_keeps_the_divider_it_does_not_own(self):
        """An unescaped slash is hierarchy and must survive; only the
        escaped dot is part of a name."""
        out, _ = rewrite_sdf("(INSTANCE top/a\\.b/c)")
        self.assertEqual(out, "(INSTANCE top/a%sb/c)" % REPLACEMENT)

    def test_empty_instance_is_untouched(self):
        """write_sdf uses (INSTANCE) for the top level."""
        self.assertEqual(rewrite_sdf("(INSTANCE)"), ("(INSTANCE)", 0))


class TestAgreement(unittest.TestCase):
    def test_both_files_land_on_the_same_name(self):
        """The whole point: the simulator does not care what an instance
        is called, only that the netlist and the SDF agree."""
        v, _ = rewrite_verilog("BUFx24 \\clkbuf_9_u_core.clk (.A(x));")
        s, _ = rewrite_sdf("(INSTANCE clkbuf_9_u_core\\.clk)")
        self.assertIn(safe("clkbuf_9_u_core.clk"), v)
        self.assertIn(safe("clkbuf_9_u_core.clk"), s)


class TestDropCond(unittest.TestCase):
    def test_drops_the_block_and_keeps_the_plain_arc(self):
        src = "\n".join([
            "(IOPATH A1 Y (1:1:1))",
            "(COND (A2 & ~B1)",
            " (IOPATH A1 Y (2:2:2)))",
            "(IOPATH A2 Y (3:3:3))",
        ])
        out, n = drop_cond(src)
        self.assertEqual(n, 1)
        self.assertIn("(IOPATH A1 Y (1:1:1))", out)
        self.assertIn("(IOPATH A2 Y (3:3:3))", out)
        self.assertNotIn("COND", out)

    def test_nested_parens_do_not_truncate_the_file(self):
        """Half a COND block left behind is a syntax error, and iverilog
        stops annotating the whole file on one of those."""
        out, n = drop_cond("(COND ((a) & (b)) (IOPATH A Y (1:1:1)))TAIL")
        self.assertEqual((out.strip(), n), ("TAIL", 1))

    def test_a_file_without_cond_is_untouched(self):
        src = "(IOPATH A Y (1:1:1))"
        self.assertEqual(drop_cond(src), (src, 0))


class TestDropTimingCheck(unittest.TestCase):
    def test_drops_the_section(self):
        src = "(DELAY (ABSOLUTE (IOPATH A Y (1:1:1))))(TIMINGCHECK (SETUP a b (1:1:1)))"
        out, n = drop_timingcheck(src)
        self.assertEqual(n, 1)
        self.assertIn("IOPATH", out)
        self.assertNotIn("TIMINGCHECK", out)

    def test_delays_are_untouched(self):
        src = "(IOPATH A Y (1:1:1))"
        self.assertEqual(drop_timingcheck(src), (src, 0))


class TestDropCelltypes(unittest.TestCase):
    def test_drops_only_the_named_type(self):
        src = ('(CELL (CELLTYPE "mem") (INSTANCE a) (DELAY))'
               '(CELL (CELLTYPE "INVx1") (INSTANCE b) (DELAY))')
        out, n = drop_celltypes(src, ["mem"])
        self.assertEqual(n, 1)
        self.assertIn("INVx1", out)
        self.assertNotIn("CELLTYPE \"mem\"", out)

    def test_no_names_drops_nothing(self):
        src = '(CELL (CELLTYPE "mem") (INSTANCE a) (DELAY))'
        self.assertEqual(drop_celltypes(src, []), (src, 0))


if __name__ == "__main__":
    unittest.main()
