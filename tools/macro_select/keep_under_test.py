"""keep_under on a hand-written boundary dump."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keep_under  # noqa: E402

BOUNDARIES = """module top/fe master Frontend in 10 out 10 cells 1000 flops 1
module top/fe/bpu master Bpu in 4 out 4 cells 600 flops 1
module top/fe/bpu/tage master Tage in 2 out 2 cells 300 flops 1
module top/fe/icache master ICache in 4 out 4 cells 50 flops 1
module top/be master Backend in 3 out 3 cells 900 flops 1
module top/be/tage2 master Tage in 2 out 2 cells 300 flops 1
"""


class KeepTest(unittest.TestCase):
    def test_masters_under_the_block_above_the_floor(self):
        d = tempfile.mkdtemp(prefix="keep_under.")
        p = os.path.join(d, "b.txt")
        with open(p, "w") as f:
            f.write(BOUNDARIES)
        rows = keep_under.read(p)
        self.assertEqual(keep_under.keep_under(rows, "Frontend", 100), ["Bpu", "Tage"])
        self.assertEqual(keep_under.keep_under(rows, "Frontend", 0), ["Bpu", "Tage", "ICache"])
        self.assertEqual(keep_under.keep_under(rows, "Backend", 100), ["Tage"])
        self.assertEqual(keep_under.keep_under(rows, "Bpu", 100), ["Tage"])


if __name__ == "__main__":
    unittest.main()
