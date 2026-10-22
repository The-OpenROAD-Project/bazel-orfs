"""read.tcl on keep_census.v at placement. Its SDC sets a clock and no
IO delays, so only register-to-register paths are timed: reg2reg runs from
r1, and every other group has no paths. Selected by -path_group alone,
every group reported the worst path overall."""

import sys
import unittest


class ReadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ends = [l.rstrip("\n").split("\t") for l in open(sys.argv[1])]
        cls.report = {}
        for line in open(sys.argv[2]):
            words = line.split()
            if (
                words
                and words[0] in ("reg2reg", "in2reg", "reg2out", "in2out")
                and words[1] in ("worst", "no")
            ):
                cls.report[words[0]] = line
            elif words:
                cls.report[" ".join(words[:-1])] = words[-1]

    def start(self, group):
        return self.report[group].split(" -> ")[0].split()[-1]

    def test_each_group_is_selected_by_its_ends(self):
        self.assertTrue(self.start("reg2reg").startswith("r1["), self.report["reg2reg"])
        for group in ("in2reg", "reg2out", "in2out"):
            self.assertIn("no paths", self.report[group])

    def test_every_endpoint_is_a_register_with_a_period(self):
        self.assertGreater(len(self.ends), 0)
        for name, period in self.ends:
            self.assertTrue(name.endswith("/D"), name)
            self.assertGreater(float(period), 0)

    def test_the_summary(self):
        self.assertGreater(float(self.report["reg2reg min period"]), 0)
        self.assertEqual(self.report["hold buffers"], "0")


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
