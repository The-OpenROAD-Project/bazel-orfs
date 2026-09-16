"""Tests for glitch_count.py — transition counting over a VCD."""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from glitch_count import bit_changes, count, parse_header  # noqa: E402

VCD = """\
$timescale 1ps $end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 32 " pc $end
$scope module core $end
$var wire 1 # y $end
$scope module mult $end
$var wire 1 $ m $end
$var wire 1 % busy $end
$upscope $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0!
b0 "
0#
0$
0%
#100
1!
#200
0!
1#
1$
1%
#300
1!
#400
0!
0$
1$
0$
$end
"""


class TestHeader(unittest.TestCase):
    def test_scope_paths_are_full(self):
        ids, width = parse_header(io.StringIO(VCD))
        self.assertEqual(ids["$"], "tb/core/mult/m")
        self.assertEqual(ids["#"], "tb/core/y")
        self.assertEqual(width['"'], 32)


class TestBitChanges(unittest.TestCase):
    def test_a_bus_counts_every_bit_that_moved(self):
        """A net is a net: three bits changing is three nets toggling."""
        self.assertEqual(bit_changes("0000", "0111"), 3)

    def test_unknowns_are_not_transitions(self):
        self.assertEqual(bit_changes("xxxx", "0000"), 0)
        self.assertEqual(bit_changes("0000", "xxxx"), 0)

    def test_no_previous_value_is_not_a_transition(self):
        self.assertEqual(bit_changes(None, "1111"), 0)

    def test_widths_are_padded_as_vcd_does(self):
        """VCD drops leading zeros, so `b1` after `b0000` is one bit."""
        self.assertEqual(bit_changes("0000", "1"), 1)


class TestCount(unittest.TestCase):
    def _run(self, **kw):
        return count(io.StringIO(VCD), clock="clk", **kw)

    def test_counts_cycles_on_posedge(self):
        self.assertEqual(self._run()["cycles"], 2)

    def test_subtree_is_counted_separately(self):
        r = self._run(subtree="mult")
        self.assertEqual(r["signals_in_subtree"], 2)
        self.assertLess(r["transitions_subtree"], r["transitions_total"])
        self.assertGreater(r["transitions_subtree"], 0)

    def test_glitch_shows_up_as_extra_transitions(self):
        """m goes 0->1->0 inside one timestamp block: two transitions on a
        net the logic only needed to move once."""
        r = self._run(subtree="mult")
        self.assertGreaterEqual(r["transitions_subtree"], 3)

    def test_busy_fraction(self):
        r = self._run(subtree="mult", busy="busy")
        self.assertEqual(r["busy_cycles"], 1)
        self.assertAlmostEqual(r["busy_fraction"], 0.5)

    def test_clock_is_not_counted_as_activity(self):
        """The clock's own toggles are not design activity; OpenSTA takes
        clock pins from the SDC rather than from the trace."""
        with_clk = self._run()["transitions_total"]
        self.assertEqual(with_clk, count(io.StringIO(VCD), clock="clk")["transitions_total"])
        self.assertLess(with_clk, 20)


if __name__ == "__main__":
    unittest.main()
