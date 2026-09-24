"""The clock pin a parent sees on a block abstracted at cts.

A block abstracted at place has no clock tree yet, so its abstract's clock
pin carries the whole unbuffered clock net as capacitance and a zero
insertion delay, and every internal arc is timed through that net. On
XiangShan's planned parent that was 145 pF on MemBlock's clock pin, one
leaf buffer driving it, and a post-CTS worst slack of -46.6 ns at 800 ps
(ideas/xiangshan-timing.md, entry 17). Abstracted at cts, the clock pin is
the tree's root buffer input and the abstract carries the tree's insertion
delay.

The flow keeps both: the place-stage abstract (pre_layout) for the
parent's synthesis, floorplan and place, the cts-stage one from the
parent's CTS on. This reads the two .lib files of each block and checks
the clock pin moved from the net to a buffer.

Usage: clock_pin_test.py <block> <pre_layout.lib> <cts.lib> [...]
"""

import re
import sys
import unittest


def clock_pin(path):
    """Capacitance (fF) and min_clock_tree_path rise (ps) of pin("clock")."""
    with open(path) as f:
        text = f.read()
    m = re.search(r'pin\("clock"\)\s*\{(.*?)\n    \}', text, re.S)
    if not m:
        raise ValueError('%s: no pin("clock")' % path)
    body = m.group(1)
    cap = float(re.search(r"capacitance\s*:\s*([0-9.]+)", body).group(1))
    tree = re.search(
        r"timing_type\s*:\s*min_clock_tree_path;\s*cell_rise\(scalar\)\s*\{\s*"
        r'values\("([0-9.]+)"\)',
        body,
    )
    return cap, float(tree.group(1)) if tree else 0.0


ARGS = sys.argv[1:]


class ClockPinTest(unittest.TestCase):
    def test_clock_pin_is_a_buffer_after_cts(self):
        self.assertTrue(ARGS and len(ARGS) % 3 == 0, "block, pre_layout, cts ...")
        print("| block | clock pin at place fF | at cts fF | insertion delay ps |")
        print("|---|---|---|---|")
        for i in range(0, len(ARGS), 3):
            block, pre, cts = ARGS[i : i + 3]
            pre_cap, pre_tree = clock_pin(pre)
            cts_cap, cts_tree = clock_pin(cts)
            print("| %s | %.1f | %.2f | %.1f |" % (block, pre_cap, cts_cap, cts_tree))
            sys.stdout.flush()
            with self.subTest(block=block):
                self.assertEqual(pre_tree, 0.0, "no tree before the block's CTS")
                self.assertGreater(cts_tree, 0.0, "the tree's insertion delay")
                self.assertLess(
                    cts_cap * 10,
                    pre_cap,
                    "one buffer input, not the whole clock net",
                )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
