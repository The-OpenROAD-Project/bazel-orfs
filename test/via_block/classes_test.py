"""The stitched view's classes name the path through the block (via.sv).

A class names the parent by its module, as XiangShan's KPI does
(XSTile->MemBlock); a path within the parent alone is `parent`.
"""

import re
import sys
import unittest

WORST = re.compile(r"^class (\S+) worst (-?\d+) ps  (\S+) -> (\S+)$", re.M)


class ClassesTest(unittest.TestCase):
    def setUp(self):
        with open(sys.argv[1]) as f:
            self.text = f.read()
        self.worst = {m.group(1): m.groups()[1:] for m in WORST.finditer(self.text)}

    def test_the_path_through_the_block_is_its_own_class(self):
        self.assertIn("via_top->via:Pass->via_top", self.worst, self.text)
        _, start, end = self.worst["via_top->via:Pass->via_top"]
        self.assertRegex(start, r"^ra")
        self.assertRegex(end, r"^rb")

    def test_the_other_classes_stay(self):
        for c in ["parent", "Pass", "Pass->via_top"]:
            self.assertIn(c, self.worst, self.text)

    def test_no_path_through_the_block_counts_as_the_parents_own(self):
        _, start, end = self.worst["parent"]
        self.assertFalse(start.startswith("ra") and end.startswith("rb"), self.text)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
