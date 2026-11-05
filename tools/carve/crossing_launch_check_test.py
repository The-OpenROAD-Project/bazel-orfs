"""crossing_launch_check.py on reports written here."""

import json
import os
import tempfile
import unittest

import crossing_launch_check

TIME = """# reg2reg paths over 150 ps at global route; period 1000 ps
# need_ps kind from_macro to_macro startpoint endpoint through_macros slot
190.8 crossing u_A u_B a/q b/d - 0
170.0 inside u_A u_A a/q a/d - 0
crossing 1
inside 1
"""


def launcher(**kw):
    e = {
        "flop": "u_A/r",
        "crossing_ps": 190.83,
        "setup_d": 612.0,
        "hold_fanout": 80.0,
        "room": 80.0,
        "bound": 110.83,
        "fanout": 10,
        "hold_under_100": 1,
        "hold_under_300": 2,
        "hold_under_to": 3,
        "pad_ps": 1200.0,
    }
    e.update(kw)
    return e


class Check(unittest.TestCase):
    def run_check(self, launchers, time=TIME):
        with tempfile.TemporaryDirectory() as l, tempfile.TemporaryDirectory() as t:
            with open(os.path.join(l, "cross.txt.0"), "w") as f:
                json.dump({"launchers": launchers}, f)
            with open(os.path.join(t, "cross.txt.0"), "w") as f:
                f.write(time)
            return crossing_launch_check.check(l, t)

    def test_agrees(self):
        self.assertEqual(self.run_check([launcher()]), [])

    def test_unconstrained_setup(self):
        # an INF setup slack is written as null: hold alone limits the room
        self.assertEqual(self.run_check([launcher(setup_d=None)]), [])
        errs = self.run_check([launcher(setup_d=None, room=0.0, bound=190.83)])
        self.assertTrue(any("not min(setup, hold)" in e for e in errs), errs)

    def test_not_the_worst_crossing(self):
        errs = self.run_check([launcher(crossing_ps=170.0, bound=90.0)])
        self.assertTrue(any("worst launched crossing" in e for e in errs), errs)

    def test_room_is_the_smaller(self):
        errs = self.run_check([launcher(room=612.0, bound=-421.17)])
        self.assertTrue(any("not min(setup, hold)" in e for e in errs), errs)

    def test_room_never_negative(self):
        errs = self.run_check([launcher(setup_d=-40.0, room=-40.0, bound=230.83)])
        self.assertTrue(any("not min(setup, hold)" in e for e in errs), errs)

    def test_bound(self):
        errs = self.run_check([launcher(bound=190.83)])
        self.assertTrue(any("crossing less room" in e for e in errs), errs)

    def test_counts_nest(self):
        errs = self.run_check([launcher(hold_under_100=5)])
        self.assertTrue(any("do not nest" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
