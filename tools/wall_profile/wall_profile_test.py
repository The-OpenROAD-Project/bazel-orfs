"""The profile reader and the report, on a profile made up here."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wall_profile  # noqa: E402


def profile(records, maps=""):
    words = [0, 3, 0, 1000, 0]
    for count, pcs in records:
        words += [count, len(pcs)] + pcs
    words += [0, 1, 0]
    return struct.pack(f"<{len(words)}Q", *words) + maps.encode()


SYMS = [(0x1000, "serial(int)"), (0x2000, "wait()"), (0x3000, "main")]


class WallProfileTest(unittest.TestCase):
    def test_reads_records_and_maps(self):
        stacks, maps = wall_profile.read_profile(
            profile([(3, [0x1010, 0x3010]), (1, [0x2010, 0x3010])], "maps\n")
        )
        self.assertEqual(stacks, [(3, [0x1010, 0x3010]), (1, [0x2010, 0x3010])])
        self.assertEqual(maps, "maps\n")

    def test_refuses_other_files(self):
        with self.assertRaises(ValueError):
            wall_profile.read_profile(b"not a profile at all, not even close")

    def test_inclusive_and_self(self):
        stacks = [(3, [0x1010, 0x3010]), (1, [0x2010, 0x3010])]
        lines = wall_profile.summarize(stacks, SYMS)
        self.assertEqual(lines[0], "4 samples")
        self.assertIn(" 100.0% main", lines)
        self.assertIn("  75.0% serial", lines)
        self.assertIn("  25.0% wait", lines)

    def test_load_base_moves_pcs(self):
        stacks = [(2, [0x501010, 0x503010])]
        lines = wall_profile.summarize(stacks, SYMS, base=0x500000)
        self.assertIn(" 100.0% serial", lines)

    def test_pc_outside_binary_named_by_address(self):
        lines = wall_profile.summarize([(1, [0x7F0000000000])], SYMS)
        self.assertIn(" 100.0% 0x7f0000000000", lines)


if __name__ == "__main__":
    unittest.main()
