import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_libs  # noqa: E402
import ports_lib  # noqa: E402

SOURCE = """
// a block the parent instantiates
module Other(input a, output b);
  assign b = a;
endmodule

module Block #(parameter W = 4) (
  input              clock,
  input              reset, // tied off
  input  wire [3:0]  in_bits,
  input  [0:1]       in_up,
  output logic [7:0] out_bits,
  output             out_valid, out_ready,
  input  [1:0][2:0]  packed2
);
  /* module Block(input nope); */
endmodule
"""


class PortsLibTest(unittest.TestCase):
    def test_ports(self):
        ports = ports_lib.parse_ports(
            ports_lib.header(ports_lib.mask(SOURCE), "Block"), "Block"
        )
        self.assertEqual(
            [(p.name, p.direction, p.width) for p in ports],
            [
                ("clock", "input", 1),
                ("reset", "input", 1),
                ("in_bits", "input", 4),
                ("in_up", "input", 2),
                ("out_bits", "output", 8),
                ("out_valid", "output", 1),
                ("out_ready", "output", 1),
                ("packed2", "input", 6),
            ],
        )
        self.assertEqual((ports[3].msb, ports[3].lsb), (0, 1))

    def test_non_ansi_refused(self):
        with self.assertRaises(ports_lib.PortError):
            ports_lib.parse_ports(
                ports_lib.header(ports_lib.mask("module M(a, b); endmodule"), "M"),
                "M",
            )

    def test_parameter_range_refused(self):
        text = "module M(input [W-1:0] a); endmodule"
        with self.assertRaises(ports_lib.PortError):
            ports_lib.parse_ports(ports_lib.header(ports_lib.mask(text), "M"), "M")

    def test_lib_reads_back(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "b.sv")
            lef = os.path.join(d, "Block.lef")
            out = os.path.join(d, "Block.lib")
            with open(src, "w") as f:
                f.write(SOURCE)
            with open(lef, "w") as f:
                f.write("MACRO Block\n  SIZE 10.0 BY 2.5 ;\nEND Block\n")
            self.assertEqual(
                ports_lib.main(
                    ["--module", "Block", "--out", out, "--lef", lef]
                    + ["--clock", "clock", src]
                ),
                0,
            )
            with open(out) as f:
                lib = compare_libs.parse(f.read())
            cell = lib.find("cell")[0]
            self.assertEqual(cell.args, ["Block"])
            self.assertEqual(float(cell.attrs["area"]), 25.0)
            clock = [g for g in cell.find("pin") if g.args == ["clock"]][0]
            self.assertEqual(clock.attrs["clock"], "true")
            buses = {g.args[0]: g for g in cell.find("bus")}
            self.assertEqual(sorted(buses), ["in_bits", "in_up", "out_bits", "packed2"])
            self.assertEqual(buses["out_bits"].attrs["direction"], "output")
            self.assertEqual(
                [g for g in cell.groups if g.find("timing")],
                [],
                "a ports-only view has no arcs",
            )

    def test_missing_clock(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "b.sv")
            with open(src, "w") as f:
                f.write(SOURCE)
            self.assertEqual(
                ports_lib.main(
                    ["--module", "Block", "--out", os.path.join(d, "x.lib")]
                    + ["--clock", "clk", src]
                ),
                1,
            )

    def test_missing_module(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "b.sv")
            with open(src, "w") as f:
                f.write(SOURCE)
            self.assertEqual(
                ports_lib.main(
                    ["--module", "Nope", "--out", os.path.join(d, "x.lib"), src]
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
