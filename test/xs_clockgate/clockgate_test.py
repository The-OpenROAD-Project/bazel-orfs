"""XiangShan's ClockGate becomes ASAP7's integrated clock gate.

With xs_icg.ys every clock gate of the design is one ICGx1 cell and no
transparent latch is left; without it the gates stay latches. The second
half is what makes the first mean something: a mapping that silently maps
nothing (a bare techmap under the slang frontend does exactly that, see
xs_icg.ys) would leave the two netlists alike.

Usage: clockgate_test.py <mapped 1_2_yosys.v> <behavioural 1_2_yosys.v>
"""

import re
import sys
import unittest

GATES = 3  # cg_top has three banks, one clock gate each
ICG = "ICGx1_ASAP7_75t_R"
LATCH = re.compile(r"^\s*(D[HL]Lx\d+_ASAP7_75t_\w+)\s", re.M)


def cells(path):
    with open(path) as f:
        text = f.read()
    icg = len(re.findall(r"^\s*%s\s" % ICG, text, re.M))
    latches = len(LATCH.findall(text))
    return icg, latches


MAPPED, BEHAVIOURAL = sys.argv[1:3]


class ClockGateTest(unittest.TestCase):
    def test_every_clock_gate_is_an_icg_cell(self):
        icg, latches = cells(MAPPED)
        self.assertEqual(icg, GATES, "one ICGx1 per clock gate")
        self.assertEqual(latches, 0, "no transparent latch left")

    def test_without_the_mapping_the_gates_are_latches(self):
        icg, latches = cells(BEHAVIOURAL)
        self.assertEqual(icg, 0)
        self.assertGreaterEqual(latches, GATES)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
