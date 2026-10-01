"""A generated macro the plan does not name is placed beside the plan's netlists.

The planned parent holds both: the register files the plan places as FIRM
netlists at floorplan, and generated macros the plan does not name, which
place_macros.tcl hands to rtl_macro_placer. rtl_macro_placer refuses a FIRM
standard cell in its area (MPL-0050), so on XSTile, with the regions
flattened, the floorplan stopped. The miniature's FileM is such a macro.

What is checked on the floorplan checkpoint: FileM is placed, it overlaps
none of the netlists, and every netlist is FIRM again after the macro step,
where the plan put it and still an array (rtl_macro_placer moves a
cluster's cells to one point, so a netlist it saw as movable collapses),
but for its address inverters: the parent's resizer may change those, so
they are PLACED, for the legaliser to move (patch 0087).
"""

import json
import sys
import unittest


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class LeftoverMacrosTest(unittest.TestCase):
    def test_placed_beside_netlists(self):
        with open(sys.argv[1]) as f:
            d = json.load(f)
        names = [m["name"] for m in d["macros"]]
        self.assertTrue(
            any(n.startswith("u_filem") for n in names),
            "FileM, the macro the plan does not name, is in the parent: %s" % names,
        )
        self.assertEqual(len(d["netlists"]), 3, "the three placed netlists")
        for m in d["macros"]:
            self.assertIn(
                m["status"], ("PLACED", "FIRM", "LOCKED"), "%s is placed" % m["name"]
            )
            for n in d["netlists"]:
                self.assertFalse(
                    overlap(m["box"], n["box"]),
                    "%s overlaps the netlist %s" % (m["name"], n["name"]),
                )
        planned = {}
        with open(sys.argv[2]) as f:
            for line in f:
                p = line.split()
                if len(p) == 4 and not line.startswith("#"):
                    planned[p[1]] = (float(p[2]), float(p[3]))
        dbu = d["dbu"]
        for n in d["netlists"]:
            self.assertGreater(n["not_firm"], 0, "%s's address inverters are PLACED" % n["name"])
            self.assertEqual(
                n["not_firm_stray"],
                0,
                "%s's cells are FIRM but its PLACED address inverters" % n["name"],
            )
            x0, y0, x1, y1 = [v / dbu for v in n["box"]]
            px, py = planned[n["name"]]
            # where the plan put it, to the site and row grid it is snapped to
            self.assertLess(abs(x0 - px), 1.0, "%s at x %.3f, planned %.3f" % (n["name"], x0, px))
            self.assertLess(abs(y0 - py), 1.0, "%s at y %.3f, planned %.3f" % (n["name"], y0, py))
            # still an array, not its cells stacked at one point
            self.assertGreater(x1 - x0, 5.0, "%s is %.3f um wide" % (n["name"], x1 - x0))
            self.assertGreater(y1 - y0, 2.0, "%s is %.3f um tall" % (n["name"], y1 - y0))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
