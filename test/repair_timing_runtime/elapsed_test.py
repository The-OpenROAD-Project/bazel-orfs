#!/usr/bin/env python3
"""Unit tests for the substep log reader."""

import unittest

import elapsed

# Verbatim tail of a real gcd 3_3_place_gp log run at NUM_CORES=7.
REAL = """
[INFO ORD-0030] Using 7 thread(s).
[INFO GPL-0002] DBU: 1000
Design area 44 um^2 72% utilization.
Elapsed time: 0:01.13[h:]min:sec. CPU time: user 2.60 sys 0.22 (250%). Peak memory: 319892KB.
Log                       Ext     Elapsed/s Peak Memory/MB sha1sum result [0:20)
3_3_place_gp              .odb            1            312 734947984bd3fee97b5f
"""


class ParseText(unittest.TestCase):
    def test_reads_a_real_log_tail(self):
        got = elapsed.parse_text(REAL)
        self.assertAlmostEqual(got["wall_s"], 1.13)
        self.assertAlmostEqual(got["user_s"], 2.60)
        self.assertAlmostEqual(got["sys_s"], 0.22)
        self.assertEqual(got["cpu_pct"], 250)
        self.assertEqual(got["peak_kb"], 319892)
        self.assertEqual(got["threads"], 7)
        self.assertEqual(got["result_sha1"], "734947984bd3fee97b5f")

    def test_the_hash_is_found_behind_an_elapsed_stamp(self):
        """log_timestamps.py prefixes every line. Missing this made every
        stamped arm report result_sha1=None, which read as a different
        result rather than an unread one."""
        got = elapsed.parse_text(
            "[   12.345] 3_3_place_gp              .odb            1"
            "            312 734947984bd3fee97b5f\n"
            "[   12.400] Elapsed time: 0:01.13[h:]min:sec. CPU time: user "
            "2.60 sys 0.22 (250%). Peak memory: 319892KB.\n"
        )
        self.assertEqual(got["result_sha1"], "734947984bd3fee97b5f")

    def test_a_log_line_ending_in_hex_is_not_mistaken_for_the_hash(self):
        """The summary row is anchored, so prose cannot impersonate it."""
        got = elapsed.parse_text(
            "some tool says deadbeefdeadbeefdead\n"
            "Elapsed time: 0:01.00[h:]min:sec. CPU time: user 1.00 "
            "sys 0.00 (100%). Peak memory: 1024KB.\n"
        )
        self.assertIsNone(got["result_sha1"])

    def test_hours_are_optional(self):
        """A long route logs h:min:sec; a short substep logs min:sec."""
        short = elapsed.parse_text(
            "Elapsed time: 4:12.31[h:]min:sec. CPU time: user 3821.44 "
            "sys 91.02 (1549%). Peak memory: 8214032KB."
        )
        self.assertAlmostEqual(short["wall_s"], 252.31)

        long = elapsed.parse_text(
            "Elapsed time: 2:04:12.31[h:]min:sec. CPU time: user 3821.44 "
            "sys 91.02 (1549%). Peak memory: 8214032KB."
        )
        self.assertAlmostEqual(long["wall_s"], 7452.31)

    def test_missing_thread_witness_is_none_not_a_guess(self):
        """No ORD-0030 line means unproven, which is not the same as 1."""
        got = elapsed.parse_text(
            "Elapsed time: 0:01.00[h:]min:sec. CPU time: user 1.00 "
            "sys 0.00 (100%). Peak memory: 1024KB."
        )
        self.assertIsNone(got["threads"])

    def test_a_crashed_substep_raises_instead_of_scoring_zero(self):
        """The failure mode this harness exists to prevent."""
        with self.assertRaises(elapsed.LogIncomplete):
            elapsed.parse_text("[INFO ORD-0030] Using 16 thread(s).\nsegfault\n")

    def test_last_line_wins_when_a_log_was_appended_to(self):
        text = (
            "[INFO ORD-0030] Using 32 thread(s).\n"
            "Elapsed time: 0:10.00[h:]min:sec. CPU time: user 1.00 "
            "sys 0.00 (100%). Peak memory: 1024KB.\n"
            "[INFO ORD-0030] Using 16 thread(s).\n"
            "Elapsed time: 0:20.00[h:]min:sec. CPU time: user 2.00 "
            "sys 0.00 (200%). Peak memory: 2048KB.\n"
        )
        got = elapsed.parse_text(text)
        self.assertAlmostEqual(got["wall_s"], 20.0)
        self.assertEqual(got["threads"], 16)


if __name__ == "__main__":
    unittest.main()
