"""The keep census on keep_census.v: the cone through kc_mid crosses its
boundary between logic cells; kc_reg, registered at its input, is crossed
only at a register and gets no cross row."""

import sys
import unittest


class KeepCensusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [line.rstrip("\n").split("\t") for line in open(sys.argv[1])]

    def kind(self, k):
        return [r for r in self.rows if r[0] == k]

    def test_the_cut_cone_crosses_kc_mid(self):
        cross = {r[2]: r for r in self.kind("cross")}
        self.assertIn("kc_mid", cross, self.rows)
        self.assertGreater(int(cross["kc_mid"][3]), 0)

    def test_a_registered_boundary_is_not_a_crossing(self):
        self.assertNotIn("kc_reg", [r[2] for r in self.kind("cross")], self.rows)

    def test_the_logic_inside_kc_mid_is_counted(self):
        inside = {r[2]: r for r in self.kind("inside")}
        self.assertIn("kc_mid", inside, self.rows)
        self.assertGreater(float(inside["kc_mid"][4]), 0)

    def test_the_summary(self):
        (paths,) = self.kind("paths")
        self.assertGreater(int(paths[1]), 0)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
