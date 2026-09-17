"""Tests for mult_replay.py — recording a module boundary for replay."""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mult_replay import is_input, normalize, pack, read_ports, sample  # noqa: E402

# Two clock cycles. `d` settles after the edge, which is where a
# zero-delay dump puts everything an edge causes, so a sampler that
# snapshots mid-timestamp would catch the design half settled.
VCD = """\
$timescale 1ps $end
$scope module tb $end
$var wire 1 ! clknet_leaf_1_clk $end
$var wire 1 " en $end
$var wire 4 # d [3:0] $end
$var wire 2 $ q [1:0] $end
$upscope $end
$enddefinitions $end
#0
0!
0"
b0 #
b0 $
#500
1!
1"
b101 #
b1 $
#1000
0!
#1500
1!
0"
bx11 #
b10 $
#2000
0!
"""

PORTS = [
    ("input", "clknet_leaf_1_clk", 1, "clknet_leaf_1_clk"),
    ("input", "en", 1, "en"),
    ("input", "d", 4, "d"),
    ("output", "q", 2, "q"),
]


class TestNormalize(unittest.TestCase):
    def test_short_values_are_zero_extended(self):
        self.assertEqual(normalize("1", 4), ("0001", []))

    def test_an_x_value_extends_with_x_and_reports_the_bits(self):
        """VCD strips leading bits; an X value extends with X, not with 0."""
        value, mask = normalize("x1", 4)
        self.assertEqual(value, "0001")
        self.assertEqual(mask, [0, 1, 2])

    def test_unknown_bits_come_back_as_positions_not_a_flag(self):
        value, mask = normalize("1x01", 4)
        self.assertEqual(value, "1001")
        self.assertEqual(mask, [1])


class TestPorts(unittest.TestCase):
    def test_a_three_column_file_uses_the_name_as_its_spelling(self):
        path = os.path.join(os.environ.get("TEST_TMPDIR", "."), "p3.txt")
        with open(path, "w") as f:
            f.write("input a 1\noutput b 4 \\b\n")
        ports = read_ports(path)
        self.assertEqual(ports[0], ("input", "a", 1, "a"))
        self.assertEqual(ports[1], ("output", "b", 4, "\\b"))

    def test_clock_leaves_are_not_replayed(self):
        """The testbench drives them: their buffers are outside the module."""
        self.assertFalse(is_input("input", "clknet_leaf_1_clk"))
        self.assertTrue(is_input("input", "op_a_i"))
        self.assertFalse(is_input("output", "valid_o"))


class TestSample(unittest.TestCase):
    def _run(self):
        return sample(io.StringIO(VCD), PORTS, "clknet_leaf_1_clk")

    def test_one_row_per_posedge(self):
        rows, _, _ = self._run()
        self.assertEqual(len(rows), 2)

    def test_the_snapshot_is_taken_after_the_edge_settles(self):
        """At the first edge `d` becomes 0101 in the same timestamp."""
        rows, _, _ = self._run()
        self.assertEqual(rows[0]["d"], "0101")
        self.assertEqual(rows[0]["en"], "1")

    def test_x_is_mapped_to_zero_and_the_bits_are_recorded(self):
        rows, masks, unknown = self._run()
        self.assertEqual(rows[1]["d"], "0011")
        self.assertIn("d", masks[1])
        self.assertEqual(unknown["d"]["bits"], {3: 1, 2: 1})

    def test_a_missing_clock_is_an_error_not_an_empty_result(self):
        with self.assertRaises(ValueError):
            sample(io.StringIO(VCD), PORTS, "nope")


class TestPack(unittest.TestCase):
    def test_inputs_pack_msb_first_in_declared_order(self):
        rows, _, _ = sample(io.StringIO(VCD), PORTS, "clknet_leaf_1_clk")
        words, selected, total = pack(rows, PORTS, is_input)
        # en then d, clock excluded: 5 bits, en=1 d=0101 -> 1_0101.
        self.assertEqual(total, 5)
        self.assertEqual([n for n, _, _ in selected], ["en", "d"])
        self.assertEqual(int(words[0], 16), 0b10101)

    def test_outputs_pack_on_their_own(self):
        rows, _, _ = sample(io.StringIO(VCD), PORTS, "clknet_leaf_1_clk")
        words, selected, total = pack(rows, PORTS, lambda d, n: d == "output")
        self.assertEqual(total, 2)
        self.assertEqual(int(words[1], 16), 0b10)


if __name__ == "__main__":
    unittest.main()
