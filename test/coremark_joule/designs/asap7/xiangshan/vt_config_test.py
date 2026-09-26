"""Synthesis maps to RVT alone; every later stage may use LVT and SLVT.

ABC maps for area and every Vt class has the same area, so a synthesis
that sees all three picks among them by tie-break. The flow keeps LVT and
SLVT out of synthesis with DONT_USE_CELLS and lets them back in for the
stages after it, where the swap after CTS (vt_swap.tcl) puts them on the
critical paths. A stage's variables travel on into the stages after it,
so a later stage that does not restate the list inherits synthesis's and
the swap has nothing it may use: the case this test was written for.

Arguments: <design> <stage>.mk ... per design, "--" between designs.
"""

import re
import sys
import unittest

FASTER = ["*_ASAP7_75t_L", "*_ASAP7_75t_SL"]


def read_mk(path):
    with open(path) as f:
        return dict(re.findall(r"^export (\w+)\?=(.*)$", f.read(), re.M))


def designs(argv):
    out, cur = {}, []
    for a in argv + ["--"]:
        if a == "--":
            if cur:
                out[cur[0]] = cur[1:]
            cur = []
        else:
            cur.append(a)
    return out


class VtConfigTest(unittest.TestCase):
    def test_stages(self):
        found = designs(sys.argv[1:])
        self.assertTrue(found)
        for design, mks in found.items():
            stages = {m.rsplit("/", 1)[-1]: read_mk(m) for m in mks}
            self.assertIn("1_synth.mk", stages, design)
            self.assertIn("4_cts.mk", stages, design)
            for stage, v in stages.items():
                where = "%s %s" % (design, stage)
                self.assertEqual(v.get("ASAP7_USE_VT"), "RVT LVT SLVT", where)
                dont_use = v.get("DONT_USE_CELLS", "").split()
                if stage == "1_synth.mk":
                    for c in FASTER:
                        self.assertIn(c, dont_use, where)
                else:
                    for c in FASTER:
                        self.assertNotIn(c, dont_use, where)
            self.assertTrue(stages["4_cts.mk"].get("POST_CTS_TCL", "").endswith("/vt_swap.tcl"), design)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
