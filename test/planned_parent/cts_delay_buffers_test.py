"""CTS on a parent with hardened blocks: what insertion-delay balancing costs.

clock_tree_synthesis pads every register's clock path with delay buffers
until it matches the macros' insertion delay. On XiangShan's planned
parent that was 49 736 buffers for four blocks and a 2.6 h legaliser
(take 23, 2026-09-22), with the blocks abstracted at place: an abstract
taken before the block's own CTS has an unbuffered clock net behind its
clock pin, so the insertion delay CTS balanced to was that net's. The
miniature showed the same at its own scale, 7 delay buffers.

With the blocks abstracted at cts the abstract's clock pin is one buffer
input and its insertion delay is a real tree's, and balancing to it
costs at most one buffer: the macro tree arrives about 11 ps after the
register tree, less than one buffer's delay. Whether CTS pads that
residual with one buffer or leaves it is a rounding decision that
differs between machines on the same placement, so the test allows
either. -no_insertion_delay is now a choice rather than a bypass. The
numbers are printed so the ratio is on record when the parent's are read.
"""

import json
import os
import sys
import unittest


def load(name):
    with open(os.path.join(os.path.dirname(__file__), name)) as f:
        return json.load(f)


class DelayBuffersTest(unittest.TestCase):
    def test_blocks_abstracted_at_cts_need_no_delay_buffers(self):
        base = load("cts_buffers_base.json")
        nid = load("cts_buffers_nid.json")
        print(
            "| variant | cts args | macro sinks | clock buffers | delay buffers | dummy loads |"
        )
        print("|---|---|---|---|---|---|")
        for tag, d in (("base", base), ("no_insertion_delay", nid)):
            print(
                "| %s | %s | %d | %d | %d | %d |"
                % (
                    tag,
                    d["cts_args"],
                    d["macro_sinks"],
                    d["clock_buffers"],
                    d["delay_buffers"],
                    d["dummy_loads"],
                )
            )
        sys.stdout.flush()
        self.assertEqual(
            base["macro_sinks"], 4, "the four blocks are the macro clock's sinks"
        )
        self.assertLessEqual(
            base["delay_buffers"],
            1,
            "the blocks' insertion delay is a buffered tree's: at most one"
            " buffer of residual to pad",
        )
        self.assertIn("-no_insertion_delay", nid["cts_args"])
        self.assertEqual(
            nid["delay_buffers"], 0, "-no_insertion_delay: no delay buffers at all"
        )
        self.assertGreater(
            nid["clock_buffers"], 0, "the trees themselves are still built"
        )


if __name__ == "__main__":
    unittest.main()
