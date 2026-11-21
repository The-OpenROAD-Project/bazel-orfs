import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_libs  # noqa: E402


def lib(unit, setup, delay):
    return """
/* a model */
library (m) {
  time_unit : "%s";
  capacitive_load_unit (1,ff);
  cell (Block) {
    pin (clock) { direction : input; clock : true; }
    bus (in_bits) {
      direction : input;
      pin (in_bits[0]) {
        timing () {
          related_pin : "clock";
          timing_type : setup_rising;
          rise_constraint (scalar) { values ("%s"); }
          fall_constraint (t) { index_1 ("1, 2"); values ("0, \\
            %s"); }
        }
      }
    }
    pin (out_valid) {
      direction : output;
      timing () {
        related_pin : "clock";
        timing_type : rising_edge;
        cell_rise (t) { values ("0, %s", "0, 0"); }
      }
      timing () {
        related_pin : "in_bits[0]";
        timing_type : combinational;
        cell_rise (t) { values ("900"); }
      }
    }
    pin (spare) { direction : output; }
  }
}
""" % (
        unit,
        setup,
        setup,
        delay,
    )


class CompareLibsTest(unittest.TestCase):
    def write(self, d, name, text):
        path = os.path.join(d, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_boundary_in_ps(self):
        with tempfile.TemporaryDirectory() as d:
            b = compare_libs.boundary(
                self.write(d, "r.lib", lib("1ns", "0.05", "0.2")), "Block"
            )
        self.assertAlmostEqual(b["in_bits"]["setup"], 50.0)
        self.assertAlmostEqual(b["out_valid"]["arrival"], 200.0)
        self.assertIsNone(b["spare"]["arrival"])

    def test_report(self):
        with tempfile.TemporaryDirectory() as d:
            e = compare_libs.boundary(
                self.write(d, "e.lib", lib("1ps", "40", "150")), "Block"
            )
            r = compare_libs.boundary(
                self.write(d, "r.lib", lib("1ns", "0.05", "0.2")), "Block"
            )
        text = compare_libs.report("Block", 1000, e, r)
        self.assertIn("| in_bits | input | required | 960.0 | 950.0 | -10.0 |", text)
        self.assertIn("| out_valid | output | arrival | 150.0 | 200.0 | 50.0 |", text)
        self.assertNotIn("| spare |", text)
        self.assertIn("No arc in either view: clock, spare", text)

    def test_missing_cell(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                compare_libs.boundary(
                    self.write(d, "r.lib", lib("1ps", "1", "1")), "Other"
                )


if __name__ == "__main__":
    unittest.main()
