"""The pin plan (//tools/pin_plan) puts the register file's pins where their
logic is: after it, fewer than one pin in ten faces away from its logic.
Fewer than before is not enough: the parent placing the base flow's
register file, not the planned one, still moved 240 to 59."""

import re
import sys
import unittest

TOTAL = re.compile(r"^total (\d+) pins, (\d+) facing away from their logic$", re.M)


def totals(path):
    with open(path) as f:
        text = f.read()
    m = TOTAL.search(text)
    if not m:
        raise ValueError("%s: no total line:\n%s" % (path, text))
    return int(m.group(1)), int(m.group(2)), text


class PinPlanTest(unittest.TestCase):
    def test_fewer_pins_face_away(self):
        pins0, away0, before = totals(sys.argv[1])
        pins1, away1, after = totals(sys.argv[2])
        self.assertEqual(pins0, pins1, before + after)
        self.assertGreater(away0, 0, "nothing to plan:\n" + before)
        self.assertLess(away1, away0, before + after)
        self.assertLess(away1 * 10, pins1, before + after)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
