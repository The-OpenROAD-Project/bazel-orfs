"""The fanout-loop reproducer against the result worked out by hand.

v loops back to itself through one gate on a net that also drives 64 other
sinks. Relaxed and without a fanout cap, the flow builds the loop by hand:
the flop and that gate, no buffer. Under set_max_fanout 32, or at a clock
every endpoint misses, a buffer lands on the loop's sink and the loop gets
slower. That is a trade, not a mistake, and the floor report says so: the
buffer also carries a data path worse than the loop, the floor does not set
the period, and moving the loop's sink ahead of the buffer lowers the floor
and raises the period. A buffered loop is worth chasing only when the floor
binds and the loop is the worst path through its buffers
(.claude/skills/repair-headroom).
"""

import re
import sys
import unittest

FLOOR = re.compile(
    r"One-flop-loop floor: ([0-9.]+) at (\S+) \((\d+) stages, (\d+) buffers;"
)


VERDICT = re.compile(
    r"One-flop-loop floor (binds|does not bind): design period ([0-9.]+)"
    r"(?:; the loop's buffers carry a ([0-9.]+) path)?"
)


def floor(path):
    """(floor, register, stages, buffers, binds, design period, the worst
    path through the loop's buffers when worse than the loop, else None)"""
    with open(path) as f:
        log = f.read()
    m = FLOOR.search(log)
    assert m, "no floor line in " + path
    v = VERDICT.search(log)
    assert v, "no verdict line in " + path
    return (
        float(m.group(1)),
        m.group(2),
        int(m.group(3)),
        int(m.group(4)),
        v.group(1) == "binds",
        float(v.group(2)),
        float(v.group(3)) if v.group(3) else None,
    )


def find(paths, variant):
    for p in paths:
        if p.endswith("/%s/5_1_grt.log" % variant):
            return p
    raise AssertionError("no %s grt log among %s" % (variant, paths))


class FanoutLoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = floor(find(sys.argv[1:], "base"))
        cls.capped = floor(find(sys.argv[1:], "capped"))
        cls.tight = floor(find(sys.argv[1:], "base_tight"))

    def test_the_loop_is_v(self):
        self.assertTrue(self.base[1].startswith("v_out"), self.base)
        self.assertTrue(self.capped[1].startswith("v_out"), self.capped)

    def test_without_a_cap_the_loop_is_the_hand_result(self):
        # the flop and one gate, no buffer on the loop
        _, _, stages, buffers = self.base[:4]
        self.assertEqual(buffers, 0, self.base)
        self.assertLessEqual(stages, 3, self.base)

    def test_the_cap_puts_a_buffer_on_the_loop(self):
        # the reproduction: the fanout tree serves the critical sink through
        # a buffer, and the loop's period grows by it
        self.assertGreater(self.capped[3], 0, self.capped)
        self.assertGreater(self.capped[0], self.base[0] * 1.2, (self.capped, self.base))

    def test_the_cap_buffer_is_a_trade(self):
        # the buffer carries a path at least as bad as the loop
        self.assertIsNotNone(self.capped[6], self.capped)

    def test_timing_repair_buffers_the_loop_as_a_trade(self):
        # at a 70 ps clock, every endpoint violating, repair leaves a buffer
        # on the loop because a data path worse than the loop rides on it,
        # and the floor does not set the period
        self.assertGreater(self.tight[3], 0, self.tight)
        self.assertIsNotNone(self.tight[6], self.tight)
        self.assertGreater(self.tight[6], self.tight[0], self.tight)
        self.assertFalse(self.tight[4], self.tight)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
