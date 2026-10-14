"""clock_gate_census.py on a two-level firtool-shaped netlist."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clock_gate_census import census  # noqa: E402

NETLIST = """
module Top(
  input clock
);
  Unit u0 (
    .clock (clock)
  );
  Unit u1 (
    .clock (clock)
  );
  Leaf l (
    .clock (clock)
  );
endmodule

module Unit(
  input clock
);
  ClockGate ckg (
    .CK (clock),
    .Q  (_ckg_Q),
    .E  (1'h1),
    .TE (te_cgen)
  );
  ClockGate ckg_0 (
    .CK (clock),
    .Q  (_ckg_0_Q),
    .E  (io_en),
    .TE (te_cgen)
  );
  Leaf l (
    .clock (clock)
  );
endmodule

module Leaf(
  input clock
);
  ClockGate ckg (
    .CK (clock),
    .Q  (_ckg_Q),
    .E  (io_en),	// a location comment
    .TE (1'h0)
  );
endmodule

module Unused(
  input clock
);
  ClockGate ckg (
    .CK (clock),
    .Q  (_ckg_Q),
    .E  (1'h1),
    .TE (1'h0)
  );
endmodule
"""


class CensusTest(unittest.TestCase):
    def test_counts_expand_the_hierarchy(self):
        r = census(NETLIST, "Top")
        # Unit twice (2 gates each), Leaf three times (once under Top,
        # once under each Unit); Unused is not under Top.
        self.assertEqual(r["gates"], 2 * 2 + 3)
        self.assertEqual(r["always_on"], 2)
        self.assertFalse(r["gate_module_defined"])

    def test_reports_each_holder_once(self):
        r = census(NETLIST, "Top")
        by = {m["module"]: m for m in r["modules"]}
        self.assertEqual(set(by), {"Unit", "Leaf"})
        self.assertEqual(by["Leaf"]["instances"], 3)
        self.assertEqual(by["Leaf"]["gates"][0]["E"], "io_en")

    def test_unknown_top_stops(self):
        with self.assertRaises(SystemExit):
            census(NETLIST, "Nope")


if __name__ == "__main__":
    unittest.main()
