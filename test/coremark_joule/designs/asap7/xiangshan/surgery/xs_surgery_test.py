"""xs_surgery.py: each action, and a broken precondition stopping loudly."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xs_surgery import SurgeryError, apply, parse_header, propose  # noqa: E402

NETLIST = """// header
module Child(	// loc
  input        clock,	// loc
               io_en,
  input  [7:0] io_a,
               io_b,
  output [7:0] io_q
);

  assign io_q = io_en ? io_a : io_b;
endmodule

module Parent(
  input        clock,
  input  [7:0] d,
  output [7:0] q
);
  wire [7:0] tie = 8'h5;
  Child c (
    .clock (clock),
    .io_en (1'h1),
    .io_a  (d),
    .io_b  (tie),
    .io_q  (q)
  );
endmodule
"""


def entry(port, value, instances=1, round_=1):
    return {"round": round_, "module": "Child", "port": port, "value": value, "instances": instances}


class SurgeryTest(unittest.TestCase):
    def test_header_inherits_direction_and_range(self):
        body = NETLIST[NETLIST.index("(") + 1 : NETLIST.index(");")]
        self.assertEqual(
            parse_header(body),
            [
                ("input", "", "clock"),
                ("input", "", "io_en"),
                ("input", "[7:0]", "io_a"),
                ("input", "[7:0]", "io_b"),
                ("output", "[7:0]", "io_q"),
            ],
        )

    def test_literal_port_becomes_a_wire(self):
        out = apply(NETLIST, {"entries": [entry("io_en", "1'h1")]})
        self.assertNotIn(".io_en", out)
        self.assertIn("wire io_en = 1'h1;", out)
        child = out[out.index("module Child") : out.index("endmodule")]
        self.assertNotIn("io_en,", child.split(");")[0])
        # The port after it keeps its range though it no longer follows a
        # declaration that names one.
        self.assertIn("input [7:0] io_b", out)

    def test_constant_wire_in_the_parent_counts_as_its_literal(self):
        out = apply(NETLIST, {"entries": [entry("io_b", "8'h5")]})
        self.assertIn("wire [7:0] io_b = 8'h5;", out)
        self.assertNotIn(".io_b", out)

    def test_rounds_apply_in_order_on_the_previous_text(self):
        out = apply(NETLIST, {"entries": [entry("io_b", "8'h5", round_=2), entry("io_en", "1'h1")]})
        self.assertIn("wire io_en = 1'h1;", out)
        self.assertIn("wire [7:0] io_b = 8'h5;", out)

    def test_wrong_value_stops(self):
        with self.assertRaisesRegex(SurgeryError, "Child.io_en: an instance ties it to"):
            apply(NETLIST, {"entries": [entry("io_en", "1'h0")]})

    def test_wrong_instance_count_stops(self):
        with self.assertRaisesRegex(SurgeryError, "1 instances, the manifest says 2"):
            apply(NETLIST, {"entries": [entry("io_en", "1'h1", instances=2)]})

    def test_live_port_stops(self):
        with self.assertRaisesRegex(SurgeryError, "ties it to 'd'"):
            apply(NETLIST, {"entries": [entry("io_a", "8'h0")]})

    def test_output_port_stops(self):
        with self.assertRaisesRegex(SurgeryError, "connects the port|not one input"):
            apply(NETLIST.replace(".io_q  (q)", ".io_q  (8'h0)"), {"entries": [entry("io_q", "8'h0")]})

    def test_protected_module_stops(self):
        with self.assertRaisesRegex(SurgeryError, "protected"):
            apply(NETLIST, {"entries": [entry("io_en", "1'h1")]}, protect=["Child"])

    def test_propose_takes_every_instance_in_the_file(self):
        boundary = [
            {"module": "Child", "kind": "keep", "port": "io_en", "tied": {"1'h1": 1}},
            {"module": "Child", "kind": "keep", "port": "io_a", "tied": {"8'h0": 1}},
        ]
        two = NETLIST + NETLIST[NETLIST.index("module Parent") :].replace("Parent", "Other")
        self.assertEqual(len(propose(boundary, NETLIST, "o")["entries"]), 2)
        # A second instance outside the top that the boundary scan never saw.
        self.assertEqual(propose(boundary, two, "o")["entries"], [])


if __name__ == "__main__":
    unittest.main()
