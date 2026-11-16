"""The interface-logic-model view times the parent as the whole view does.

    ilm_sta_test.py <via_top_headroom_classes.txt> <via_top_ilm_sta.txt>
        <via_top_ilm_sta_paths.txt>

via_top_ilm_sta is orfs_flow's: Pass reduced to its interface logic
(//tools/headroom:sta_part.tcl, STA_ILM=1). via_top_headroom_classes is
orfs_headroom's view of the same parts with every cell of Pass. Both read
the same global routes and time with the same OpenSTA.

The interface logic model keeps every cell on a path that crosses Pass's
boundary, every load of the nets those cells drive and the clock tree of
the flops it keeps, so each such path has the same cells, loads, wires and
clock as in the whole block. A reg2reg endpoint in the parent has every
path to it in both views: its worst path, and so every class that ends in
the parent, its worst path and its histogram, agree exactly, with no
tolerance. An endpoint inside Pass loses the paths from flops Pass's model
leaves out; its worst is never worse than in the whole view.
"""

import re
import sys
import unittest

PARENT = "via_top"
WORST = re.compile(r"^class (\S+) worst (-?\d+) ps  (\S+) -> (\S+)$", re.M)
HIST = re.compile(r"^class (\S+) endpoints (.*)$", re.M)
PERIOD = re.compile(r"^reg2reg min period (-?\d+) ps$", re.M)


def ends_in_parent(c):
    return c == "parent" or c.endswith("->" + PARENT)


class IlmStaTest(unittest.TestCase):
    def setUp(self):
        whole, ilm, paths = sys.argv[1:4]
        with open(ilm) as f:
            self.ilm = f.read()
        with open(whole) as f:
            self.whole = f.read()
        with open(paths) as f:
            self.paths = f.read()

    def worst(self, text):
        return {m.group(1): m.groups()[1:] for m in WORST.finditer(text)}

    def hist(self, text):
        return {m.group(1): m.group(2) for m in HIST.finditer(text)}

    def test_classes_ending_in_the_parent_agree_exactly(self):
        ilm, whole = self.worst(self.ilm), self.worst(self.whole)
        classes = sorted(c for c in whole if ends_in_parent(c))
        self.assertIn("via_top->via:Pass->via_top", classes, self.whole)
        self.assertIn("Pass->via_top", classes, self.whole)
        self.assertEqual(classes, sorted(c for c in ilm if ends_in_parent(c)))
        for c in classes:
            self.assertEqual(ilm[c], whole[c], c)
            self.assertEqual(self.hist(self.ilm)[c], self.hist(self.whole)[c], c)

    def test_paths_inside_the_block_are_never_worse(self):
        ilm, whole = self.worst(self.ilm), self.worst(self.whole)
        for c in ilm:
            if not ends_in_parent(c):
                self.assertLessEqual(int(ilm[c][0]), int(whole[c][0]), c)

    def test_each_class_has_its_worst_path_cell_by_cell(self):
        for c, (period, _, _) in self.worst(self.ilm).items():
            self.assertIn("### class %s worst %s ps" % (c, period), self.paths)

    def test_min_period_is_the_worst_class(self):
        periods = PERIOD.findall(self.ilm)
        self.assertTrue(periods, self.ilm)
        worst = max(int(w[0]) for w in self.worst(self.ilm).values())
        self.assertEqual(int(periods[-1]), worst)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
