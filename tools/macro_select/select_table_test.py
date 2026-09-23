"""select_table on a small Verilog file with continuation-style ports."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import select_table  # noqa: E402

SV = """
module Leaf(
  input         clock,
                reset,
                a,
  input  [7:0]  b,
                c,
  output [15:0] d
);
endmodule
module Parent(
  input        clock,
  output [3:0] q
);
  Leaf l(.clock(clock));
endmodule
module Other(input x, output y);
endmodule
"""


class TableTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(prefix="select_table."), "d.sv")
        with open(self.path, "w") as f:
            f.write(SV)

    def test_continuation_widths_carry(self):
        bits = select_table.port_bits(self.path, ["Leaf", "Parent", "Other"])
        # clock, reset, a: 3; b, c: 16; d: 16
        self.assertEqual(bits["Leaf"], (35, 6))
        self.assertEqual(bits["Parent"], (5, 2))
        self.assertEqual(bits["Other"], (2, 2))

    def test_parent_gets_the_children_area(self):
        bits = select_table.port_bits(self.path, ["Leaf", "Parent"])
        rows = select_table.table(bits, {"Leaf": 10000.0}, {"Parent": ["Leaf"]})
        by = {r[0]: r for r in rows}
        self.assertEqual(by["Parent"][3], 10000.0)
        self.assertEqual(by["Parent"][6], "children's area")
        self.assertAlmostEqual(by["Leaf"][4], 100.0)
        self.assertAlmostEqual(by["Leaf"][5], 35 / 400.0)

    def test_format(self):
        bits = select_table.port_bits(self.path, ["Leaf"])
        text = select_table.format_table(select_table.table(bits, {}, {}))
        self.assertIn("Leaf", text)
        self.assertIn("no area", text)


if __name__ == "__main__":
    unittest.main()
