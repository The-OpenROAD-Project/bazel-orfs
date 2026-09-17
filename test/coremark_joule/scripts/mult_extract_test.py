"""Tests for mult_extract.py — cutting one module out of a hardened netlist."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mult_extract import cells, module_body, ports, sdf_subtree  # noqa: E402

NETLIST = """\
module other (a, b);
  input a;
  output b;
  BUFx2 u0 (.A(a), .Y(b));
endmodule
module \\mult$top__dot__u  (clk, d, q);
  input clk;
  input [3:0] d;
  output [1:0] q;
  wire n1;
  TIEHIx1 tie0 (.H(n1));
  BUFx2 _001_ (.A(d[0]), .Y(n1));
  DFFx1 \\reg.0  (.CLK(clk), .D(n1), .Q(q[0]));
endmodule
"""

SDF = """\
(DELAYFILE
 (SDFVERSION "3.0")
 (CELL
  (CELLTYPE "BUFx2")
  (INSTANCE top/other_i/u0)
  (DELAY (ABSOLUTE (IOPATH A Y (1:1:1) (1:1:1))))
 )
 (CELL
  (CELLTYPE "BUFx2")
  (INSTANCE top/u/_001_)
  (DELAY (ABSOLUTE (IOPATH A Y (2:2:2) (2:2:2))))
 )
 (CELL
  (CELLTYPE "DFFx1")
  (INSTANCE top/u/reg.0)
  (DELAY (ABSOLUTE (IOPATH CLK Q (3:3:3) (3:3:3))))
 )
)
"""


class TestModuleBody(unittest.TestCase):
    def test_picks_the_module_whose_name_contains_the_needle(self):
        name, body = module_body(NETLIST, "mult")
        self.assertTrue(name.startswith("\\mult$"))
        self.assertIn("TIEHIx1", body)
        self.assertNotIn("module other", body)

    def test_a_needle_that_matches_nothing_is_an_error(self):
        with self.assertRaises(ValueError):
            module_body(NETLIST, "divider")


class TestPorts(unittest.TestCase):
    def test_directions_widths_and_the_netlist_spelling(self):
        _, body = module_body(NETLIST, "mult")
        self.assertEqual(
            ports(body),
            [("input", "clk", 1, "clk"),
             ("input", "d", 4, "d"),
             ("output", "q", 2, "q")],
        )


class TestCells(unittest.TestCase):
    def test_counts_instances_and_not_declarations(self):
        _, body = module_body(NETLIST, "mult")
        self.assertEqual(sorted(cells(body)), ["_001_", "reg.0", "tie0"])


class TestSdfSubtree(unittest.TestCase):
    def test_keeps_only_the_module_and_rewrites_paths_relative(self):
        text, n, prefix = sdf_subtree(SDF, "u/")
        self.assertEqual(n, 2)
        self.assertEqual(prefix, "top/u/")
        self.assertIn("(INSTANCE _001_)", text)
        self.assertIn("(INSTANCE reg.0)", text)
        self.assertNotIn("top/u/", text)
        self.assertNotIn("other_i", text)

    def test_the_header_survives_so_the_file_is_still_an_sdf(self):
        text, _, _ = sdf_subtree(SDF, "u/")
        self.assertIn("(SDFVERSION", text)
        self.assertTrue(text.rstrip().endswith(")"))

    def test_a_needle_matching_two_instances_is_an_error(self):
        """Two instances of one module need the caller to say which."""
        with self.assertRaises(ValueError):
            sdf_subtree(SDF, "top/")

    def test_a_needle_that_matches_nothing_is_an_error(self):
        with self.assertRaises(ValueError):
            sdf_subtree(SDF, "nope")


if __name__ == "__main__":
    unittest.main()
