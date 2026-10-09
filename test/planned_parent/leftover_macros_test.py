"""A generated macro the plan does not name is placed beside the plan's netlists.

The planned parent holds both: the register files the plan places, macros
until they dissolve into their cells after the macro step, and generated
macros the plan does not name, which place_macros.tcl hands to
rtl_macro_placer. The miniature's FileM is such a macro.

What is checked on the floorplan checkpoint: FileM is placed, it overlaps
none of the netlists, and every netlist's core is FIRM where the plan put
it and still an array, but for its periphery: the generator leaves the
address decode to the parent, to place and size like any logic.

    leftover_macros_test.py <leftover_macros.json> <instance>=<x>,<y>...
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
        for arg in sys.argv[2:]:
            inst, xy = arg.split("=")
            x, y = xy.split(",")
            planned[inst] = (float(x), float(y))
        dbu = d["dbu"]
        for n in d["netlists"]:
            self.assertGreater(
                n["not_firm"], 0, "%s has a periphery left to the parent" % n["name"]
            )
            self.assertEqual(
                n["not_firm_stray"],
                0,
                "%s's cells are FIRM but its periphery" % n["name"],
            )
            x0, y0, x1, y1 = [v / dbu for v in n["box"]]
            px, py = planned[n["name"]]
            # where the plan put it, to the site and row grid it is snapped
            # to; the box is the FIRM core, which starts past the header
            # column the periphery's decode was laid out in
            self.assertGreater(
                x0 - px, -1.0, "%s at x %.3f, planned %.3f" % (n["name"], x0, px)
            )
            self.assertLess(
                x0 - px, 10.0, "%s at x %.3f, planned %.3f" % (n["name"], x0, px)
            )
            self.assertLess(
                abs(y0 - py), 1.0, "%s at y %.3f, planned %.3f" % (n["name"], y0, py)
            )
            # still an array, not its cells stacked at one point
            self.assertGreater(
                x1 - x0, 5.0, "%s is %.3f um wide" % (n["name"], x1 - x0)
            )
            self.assertGreater(
                y1 - y0, 2.0, "%s is %.3f um tall" % (n["name"], y1 - y0)
            )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
