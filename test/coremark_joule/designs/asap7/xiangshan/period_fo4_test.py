"""The SDC period is XiangShan's 333 ps on 7 nm, in fanouts of four.

333 ps divided by the published ASAP7 FO4 (Clark et al., MSE 2017: 8.1,
6.8 and 6 ps for RVT, LVT and SLVT) is the cycle in FO4. Times the FO4 of
the library the flow times with is the period at global route; 0.8 of
that is the synthesis period in the SDC. Change either side alone and
this fails.

The libraries are slower than the published figures by the same factor
in every Vt class, so the period does not depend on which class the
comparison is made in; a design that uses faster cells fits more logic
in it, the target stays.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fo4  # noqa: E402

XIANGSHAN_PERIOD_PS = 333.0
PUBLISHED_FO4_PS = {"R": 8.1, "L": 6.8, "SL": 6.0}
SYNTHESIS_FRACTION = 0.8
# How far the Vt classes may disagree on the period at global route.
VT_SPREAD = 0.01


def route_period(lib, cell, vt):
    """The period at global route, from one Vt class's inverter."""
    library_fo4 = fo4.fo4(fo4.read_lib(lib), cell)
    return library_fo4, XIANGSHAN_PERIOD_PS / PUBLISHED_FO4_PS[vt] * library_fo4


class PeriodFo4Test(unittest.TestCase):
    def setUp(self):
        # sdc, then (vt, lib, cell) triples, the flow's primary Vt first
        self.sdc = sys.argv[1]
        rest = sys.argv[2:]
        self.classes = [tuple(rest[k : k + 3]) for k in range(0, len(rest), 3)]

    def test_sdc_period_is_congruent(self):
        vt, lib, cell = self.classes[0]
        library_fo4, route = route_period(lib, cell, vt)
        route = round(route)
        with open(self.sdc) as f:
            period = float(re.search(r"^set clk_period (\S+)", f.read(), re.M).group(1))
        self.assertEqual(
            period,
            round(SYNTHESIS_FRACTION * route),
            "%sVT FO4 %.2f ps: route at %d ps, synthesise at %d ps, the SDC says %g"
            % (vt, library_fo4, route, round(SYNTHESIS_FRACTION * route), period),
        )

    def test_vt_classes_agree(self):
        routes = {vt: route_period(lib, cell, vt)[1] for vt, lib, cell in self.classes}
        self.assertEqual(len(routes), 3)
        spread = (max(routes.values()) - min(routes.values())) / min(routes.values())
        self.assertLessEqual(spread, VT_SPREAD, routes)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
