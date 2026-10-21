"""The fanout-loop reproducer against the result worked out by hand.

v loops back to itself through one gate on a net that also drives 64 other
sinks. The correct loop is the flop and that gate, with no buffer on it,
whatever the 64 other sinks need: a buffer on the loop only adds delay. The
flow without a fanout cap builds exactly that. Under set_max_fanout 32 the
fanout tree puts a buffer on the loop's own sink, the loop's period grows,
and this test records it, as on XiangShan's decode buffer (ideas entry 55).
"""

import re
import sys
import unittest

FLOOR = re.compile(
    r"One-flop-loop floor: ([0-9.]+) at (\S+) \((\d+) stages, (\d+) buffers;"
)


def floor(path):
    with open(path) as f:
        m = FLOOR.search(f.read())
    assert m, "no floor line in " + path
    return float(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))


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
        cls.iso = floor(find(sys.argv[1:], "base_tight_iso"))

    def test_the_loop_is_v(self):
        self.assertTrue(self.base[1].startswith("v_out"), self.base)
        self.assertTrue(self.capped[1].startswith("v_out"), self.capped)

    def test_without_a_cap_the_loop_is_the_hand_result(self):
        # the flop and one gate, no buffer on the loop
        _, _, stages, buffers = self.base
        self.assertEqual(buffers, 0, self.base)
        self.assertLessEqual(stages, 3, self.base)

    def test_the_cap_puts_a_buffer_on_the_loop(self):
        # the reproduction: the fanout tree serves the critical sink through
        # a buffer, and the loop's period grows by it
        self.assertGreater(self.capped[3], 0, self.capped)
        self.assertGreater(self.capped[0], self.base[0] * 1.2, (self.capped, self.base))

    def test_timing_repair_still_buffers_the_loop(self):
        # at a 100 ps clock, with no cap, repair leaves a buffer on the loop
        # and the loop slower than the relaxed run's netlist, which has none:
        # the critical sink is not taken off the buffering. When OpenROAD
        # does, this fails, and the assertion flips to the hand result.
        self.assertGreater(self.tight[3], 0, self.tight)
        self.assertGreater(self.tight[0], self.base[0], (self.tight, self.base))

    def test_isolating_the_loop_sink_gives_the_hand_result(self):
        # tools/headroom/isolate_loop_sinks.tcl before CTS moves the loop's
        # sink ahead of the buffer: no buffer on the loop, and the loop
        # faster than the flow left it
        self.assertEqual(self.iso[3], 0, self.iso)
        self.assertLess(self.iso[0], self.tight[0], (self.iso, self.tight))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
