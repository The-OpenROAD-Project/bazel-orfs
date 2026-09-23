"""Widening the gap between two blocks does not relieve a lateral interface wall.

Two 3000-pin blocks side by side, the whole interface crossing between
them from facing halves of their top sides, at a 10 um and a 60 um gap.
Both wall at route-0 (total congestion in the hundreds of thousands, a
gcell edge 190 wires over), and the wider gap is no better: every wire
leaves a top-side pin and turns along the block toward the gap, so the
strip above the pin sides is the wall, not the gap, as the pin-wall
calibration found for its lateral case. XiangShan's GRT-0228 in the 11 um
gap between Frontend and MemBlock (inventory entry 13) is therefore not
this mechanism; the parent's own route-0 gate at 60 um settles what it is.
"""

import json
import os
import sys
import unittest


def load(name):
    with open(os.path.join(os.path.dirname(__file__), name)) as f:
        return json.load(f)


class ChannelTest(unittest.TestCase):
    def test_the_gap_is_not_the_knob(self):
        rows = [(gap, load("route0_ch_p3000_g%d.json" % gap)) for gap in (10, 60)]
        print("| gap um | route-0 ok | usage % | max H / V overflow | total congestion | wirelength um | guard |")
        print("|---|---|---|---|---|---|---|")
        for gap, d in rows:
            print(
                "| %d | %s | %s | %s / %s | %s | %s | %s |"
                % (
                    gap,
                    d["ok"],
                    d["usage_percent"],
                    d["max_h_overflow"],
                    d["max_v_overflow"],
                    d["total_congestion"],
                    d["wirelength_um"],
                    d["guard"][:80],
                )
            )
        sys.stdout.flush()
        narrow, wide = rows[0][1], rows[1][1]
        for gap, d in rows:
            self.assertTrue(d["ok"], "route-0 at %d um runs to its report" % gap)
            self.assertGreater(d["total_congestion"], 100000, "the interface walls at %d um" % gap)
        ratio = wide["total_congestion"] / float(narrow["total_congestion"])
        self.assertTrue(0.67 < ratio < 1.5, "the gap is not the knob: congestion ratio %.2f" % ratio)


if __name__ == "__main__":
    unittest.main()
