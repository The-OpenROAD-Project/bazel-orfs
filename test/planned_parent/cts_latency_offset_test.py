"""CTS_LATENCY_OFFSETS clocks the named block by the offset and no other.

Two CTS runs of the miniature parent on one placement: lat0 asks for
u_blocka at 0 ps, lat40 at 40 ps later than balanced. Asking at all makes
the latency balancer balance the macros one by one, so the two differ in
the offset alone. Each block's error is its clock pin arrival plus its
insertion delay less the parent registers' median, in CTS's own model
(block_clocks.tcl). The named block moves by the offset within a delay
buffer's resolution; every other block stays within a few ps.
"""

import json
import sys
import unittest

OFFSET = 40.0
# asap7's delay buffers step 10 to 17 ps; the balancer lands within one.
NAMED_TOLERANCE = 12.0
OTHERS_TOLERANCE = 8.0


def load(path):
    with open(path) as f:
        return json.load(f)["block_error"]


class CtsLatencyOffsetTest(unittest.TestCase):
    def test_named_block_moves_by_the_offset(self):
        zero, offset = load(sys.argv[1]), load(sys.argv[2])
        self.assertEqual(sorted(zero), sorted(offset))
        moved = offset["u_blocka"] - zero["u_blocka"]
        self.assertLess(
            abs(moved - OFFSET),
            NAMED_TOLERANCE,
            "u_blocka moved %.1f ps for a %.0f ps offset" % (moved, OFFSET),
        )
        for inst in sorted(zero):
            if inst == "u_blocka":
                continue
            moved = offset[inst] - zero[inst]
            self.assertLess(
                abs(moved),
                OTHERS_TOLERANCE,
                "%s, not asked for, moved %.1f ps" % (inst, moved),
            )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
