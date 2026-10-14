"""boundary_constants.py on a parent with a kept and a flattened child."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boundary_constants import scan  # noqa: E402

NETLIST = """
module Top(
  input clock
);
  wire [1:0] tie = 2'h2;
  Kept k0 (
    .a (1'h0),
    .b (tie),
    .c (clock),
    .q ()
  );
  Kept k1 (
    .a (1'h1),
    .b (tie),
    .c (clock),
    .q ()
  );
  Flat f (
    .a (1'h0)
  );
endmodule

module Kept(
  input       a,
  input [1:0] b,
  input       c,
  output      q
);
  assign q = a & c;
endmodule

module Flat(
  input a
);
endmodule
"""


class BoundaryTest(unittest.TestCase):
    def test_tied_and_unconnected_ports_of_kept_modules(self):
        rows = {
            (r["module"], r["port"]): r for r in scan(NETLIST, "Top", {"Kept": "keep"})
        }
        self.assertEqual(set(rows), {("Kept", "a"), ("Kept", "b"), ("Kept", "q")})
        self.assertEqual(rows[("Kept", "a")]["tied"], {"1'h0": 1, "1'h1": 1})
        # A wire its parent declares equal to a literal counts as one.
        self.assertEqual(rows[("Kept", "b")]["tied"], {"2'h2": 2})
        self.assertEqual(rows[("Kept", "b")]["uses"], 0)
        self.assertEqual(rows[("Kept", "a")]["uses"], 1)
        self.assertEqual(rows[("Kept", "q")]["tied"], {"unconnected": 2})


if __name__ == "__main__":
    unittest.main()
