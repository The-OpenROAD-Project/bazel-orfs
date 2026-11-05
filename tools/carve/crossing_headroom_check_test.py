"""crossing_headroom_check.py on reports written here."""

import json
import os
import tempfile
import unittest

import crossing_headroom_check


def write(d, n, text):
    with open(os.path.join(d, "cross.txt.%d" % n), "w") as f:
        f.write(text)


TIME = """# reg2reg paths over 150 ps at global route; period 1000 ps
# need_ps kind from_macro to_macro startpoint endpoint through_macros slot
190.8 crossing u_A u_B a/q b/d - 0
170.0 inside u_A u_A a/q a/d - 0
crossing 1
inside 1
"""


def headroom(period=190.83, restored=190.83, skew=150.0):
    return json.dumps(
        {
            "period": {"period": period},
            "skew": {"skew": skew, "restored": restored},
            "wire": {"floor": 110.0, "restored": restored},
        }
    )


class Check(unittest.TestCase):
    def run_check(self, hr, time=TIME):
        with tempfile.TemporaryDirectory() as h, tempfile.TemporaryDirectory() as t:
            write(h, 0, hr)
            write(t, 0, time)
            return crossing_headroom_check.check(h, t)

    def test_agrees(self):
        self.assertEqual(self.run_check(headroom()), [])

    def test_period_not_the_worst_crossing(self):
        # the inside path is not a crossing: 170 is not the set's period
        errs = self.run_check(headroom(period=170.0, restored=170.0, skew=150.0))
        self.assertTrue(any("headroom period" in e for e in errs), errs)

    def test_not_undone(self):
        errs = self.run_check(headroom(restored=180.0))
        self.assertTrue(any("not undone" in e for e in errs), errs)

    def test_worse_than_built(self):
        errs = self.run_check(headroom(skew=200.0))
        self.assertTrue(any("worse than as built" in e for e in errs), errs)

    def test_no_reports(self):
        with tempfile.TemporaryDirectory() as h, tempfile.TemporaryDirectory() as t:
            self.assertTrue(crossing_headroom_check.check(h, t))


if __name__ == "__main__":
    unittest.main()
