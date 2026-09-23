"""CTS on a parent with hardened blocks: what insertion-delay balancing costs.

clock_tree_synthesis pads every register's clock path with delay buffers
until it matches the macros' insertion delay. On XiangShan's planned
parent that was 49 736 buffers for four blocks and a 2.6 h legaliser
(take 23, 2026-09-22); the miniature here shows the same mechanism at its
own scale, and that -no_insertion_delay removes it entirely. The numbers
are printed so the ratio is on record when the parent's are read.
"""

import json
import os
import sys
import unittest


def load(name):
    with open(os.path.join(os.path.dirname(__file__), name)) as f:
        return json.load(f)


class DelayBuffersTest(unittest.TestCase):
    def test_no_insertion_delay_removes_the_delay_buffers(self):
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
        self.assertGreater(
            base["delay_buffers"],
            0,
            "with macros, CTS balances to their insertion delay",
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
