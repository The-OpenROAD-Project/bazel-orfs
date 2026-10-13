"""Every output the post-CTS abstract times, the pre-layout one times too.

A parent times its synthesis, floorplan and place against a block's
pre-layout abstract and switches to the CTS one at its own CTS. An
output with a timing arc in the CTS abstract and none in the pre-layout
one is a path the parent does not time until CTS. The two are written
from the same design a stage apart, so the arcs differ in value, not in
which outputs have one.

Usage: check_pre_layout_arcs.py <pre_layout .lib> <cts .lib>
"""

import re
import sys
import unittest


def timed_outputs(path):
    """Output pins of the abstract with a timing() group."""
    with open(path) as f:
        text = f.read()
    pins = re.findall(
        r'pin\("([^"]+)"\)\s*\{\s*direction : output;(.*?)\n    \}', text, re.S
    )
    if not pins:
        raise SystemExit("{}: no output pins".format(path))
    return {name for name, body in pins if "timing()" in body}


class PreLayoutArcs(unittest.TestCase):
    def test_pre_layout_times_what_cts_times(self):
        missing = sorted(CTS - PRE_LAYOUT)
        self.assertEqual(missing, [], "untimed in the pre-layout abstract")

    def test_memory_output_is_timed(self):
        # rdata comes straight from the AUTO_MEMORIES macro.
        self.assertIn("rdata[0]", PRE_LAYOUT)


if __name__ == "__main__":
    PRE_LAYOUT = timed_outputs(sys.argv[1])
    CTS = timed_outputs(sys.argv[2])
    unittest.main(argv=sys.argv[:1])
