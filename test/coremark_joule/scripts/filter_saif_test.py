#!/usr/bin/env python3
"""Unit tests for the SAIF name filter."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from filter_saif import carryable, filter_saif, is_clock  # noqa: E402


def lines(text):
    return [l + "\n" for l in text.strip("\n").split("\n")]


class CarryableTest(unittest.TestCase):
    def test_a_plain_name_is_carryable(self):
        self.assertTrue(carryable("_10124_"))
        self.assertTrue(carryable("net45140"))

    def test_dots_and_brackets_are_in_the_id_rule(self):
        self.assertTrue(carryable("swerv.ifu.bp.BTB_FLOPS[39]"))

    def test_a_slash_is_not(self):
        """`/` is HCHAR, the hierarchy separator -- never part of a name."""
        self.assertFalse(carryable("clknet_1_0__leaf_swerv.ifu.bp/BTB_FLOPS[39].Q"))

    def test_a_leading_backslash_is_not_an_escape_hatch(self):
        """An ID must start with a letter or underscore, so there is no
        spelling of a slashed name the format accepts."""
        self.assertFalse(carryable("\\clknet_a/b"))


class IsClockTest(unittest.TestCase):
    def test_openroad_clock_net_prefixes(self):
        self.assertTrue(is_clock("clknet_1_0__leaf_x/y"))
        self.assertTrue(is_clock("clkbuf_0_x/y"))

    def test_a_cloned_net_is_not_assumed_to_be_a_clock(self):
        self.assertFalse(is_clock("clonenet_12/x"))


class FilterTest(unittest.TestCase):
    SRC = lines("""
(SAIFILE
(INSTANCE TOP
 (NET
  (_10124_ (T0 0) (T1 100) (TZ 0) (TX 0) (TB 0) (TC 1))
  (clknet_1_0__leaf_a.b/c.Q (T0 100) (T1 0) (TZ 0) (TX 0) (TB 0) (TC 0))
  (clonenet_7/x (T0 0) (T1 100) (TZ 0) (TX 0) (TB 0) (TC 3))
  (net1079 (T0 0) (T1 100) (TZ 0) (TX 0) (TB 0) (TC 1))
 )
)
)
""")

    def test_only_uncarryable_names_are_dropped(self):
        kept, clock, other = filter_saif(self.SRC)
        self.assertEqual(["clknet_1_0__leaf_a.b/c.Q"], clock)
        self.assertEqual(["clonenet_7/x"], other)
        self.assertEqual(len(self.SRC) - 2, len(kept))

    def test_structure_is_preserved(self):
        kept, _, _ = filter_saif(self.SRC)
        body = "".join(kept)
        self.assertIn("(SAIFILE", body)
        self.assertIn("(INSTANCE TOP", body)
        self.assertIn("_10124_", body)
        self.assertIn("net1079", body)

    def test_an_uncarryable_instance_takes_its_block(self):
        """Half a block left behind is a worse file than the original."""
        src = lines("""
(SAIFILE
 (INSTANCE good
  (NET
   (_1_ (T0 0) (T1 10) (TZ 0) (TX 0) (TB 0) (TC 1))
  )
 )
 (INSTANCE clkbuf_0_a.b/c.clk
  (NET
   (Y (T0 0) (T1 10) (TZ 0) (TX 0) (TB 0) (TC 2))
   (A (T0 0) (T1 10) (TZ 0) (TX 0) (TB 0) (TC 2))
  )
 )
 (INSTANCE after
  (NET
   (_2_ (T0 0) (T1 10) (TZ 0) (TX 0) (TB 0) (TC 1))
  )
 )
)
""")
        kept, clock, other = filter_saif(src)
        body = "".join(kept)
        self.assertEqual(["clkbuf_0_a.b/c.clk"], clock)
        self.assertEqual([], other)
        self.assertNotIn("clkbuf", body)
        self.assertNotIn("(Y (T0", body)
        self.assertIn("(INSTANCE good", body)
        self.assertIn("(INSTANCE after", body)
        self.assertEqual(body.count("("), body.count(")"))

    def test_a_nested_uncarryable_instance_takes_only_its_own_block(self):
        src = lines("""
(SAIFILE
 (INSTANCE outer
  (INSTANCE clkbuf_0_x/y
   (NET
    (A (T0 0) (T1 10) (TZ 0) (TX 0) (TB 0) (TC 1))
   )
  )
  (NET
   (_9_ (T0 0) (T1 10) (TZ 0) (TX 0) (TB 0) (TC 1))
  )
 )
)
""")
        kept, clock, _ = filter_saif(src)
        body = "".join(kept)
        self.assertEqual(["clkbuf_0_x/y"], clock)
        self.assertIn("(INSTANCE outer", body)
        self.assertIn("_9_", body)
        self.assertEqual(body.count("("), body.count(")"))

    def test_a_clean_saif_is_unchanged(self):
        src = lines("""
(SAIFILE
 (NET
  (_1_ (T0 0) (T1 10) (TZ 0) (TX 0) (TB 0) (TC 1))
 )
)
""")
        kept, clock, other = filter_saif(src)
        self.assertEqual((src, [], []), (kept, clock, other))


if __name__ == "__main__":
    unittest.main()
