"""Every flow's synthesis maps for delay: ABC's speed script, not its area one.

ABC_AREA=1 came in as a turnaround setting while the flow was being put
together, one mapping round instead of the speed script's five, and was
never flipped back. On Region_1 at its place stage the area script's
netlist was 2,020 ps; the speed script's 1,624 ps, with fewer cells.

Arguments: <design> <1_synth.mk> per design.
"""

import re
import sys
import unittest


class SynthConfigTest(unittest.TestCase):
    def test_speed_script(self):
        args = sys.argv[1:]
        self.assertTrue(args and len(args) % 2 == 0, "design, 1_synth.mk ...")
        for i in range(0, len(args), 2):
            design, mk = args[i : i + 2]
            with open(mk) as f:
                v = dict(re.findall(r"^export (\w+)\?=(.*)$", f.read(), re.M))
            self.assertIn(v.get("ABC_AREA", "0"), ("0", ""), design)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
