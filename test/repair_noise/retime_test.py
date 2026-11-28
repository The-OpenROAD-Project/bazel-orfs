"""The retime study's log parser and decision rule."""

import os
import tempfile
import unittest

import retime

LOG = """\
global_placement -timing_driven
retime
[INFO RET-0014] Retiming graph: 5774 gates, 9515 edges, 320 registers, 128 pinned gates, 0 fenced registers.
RETIME_CENSUS sequential=320 outside_graph=0 movable=318 fenced=2 sdc=0 held=0 dont_touch=0 shared_net=0 constant=0 supply=0
 Round | Proposed | Trials | Kept |         WNS |           TNS | Registers
---------------------------------------------------------------------------
 start |          |        |      |   -523.2018 |   -25756.9141 |       320
     1 |       70 |      1 |   70 |   -523.1923 |   -25521.7031 |       386
---------------------------------------------------------------------------
[INFO RET-0053] Retime: slides 70, rounds 1, WNS -523.1923, TNS -25521.7031, registers 386, placed 84, resized 0.
"""


class ParseTest(unittest.TestCase):
    def _parse(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
            fh.write(text)
        try:
            return retime.parse_retime_log(fh.name)
        finally:
            os.unlink(fh.name)

    def test_rounds_census_totals(self):
        r = self._parse(LOG)
        self.assertEqual([x["round"] for x in r["rounds"]], [0, 1])
        self.assertEqual(r["rounds"][1]["registers"], 386)
        self.assertAlmostEqual(r["rounds"][0]["wns"], -523.2018)
        self.assertEqual(r["census"]["movable"], 318)
        self.assertEqual(r["graph"]["pinned"], 128)
        self.assertEqual(r["totals"]["slides"], 70)
        self.assertEqual(r["totals"]["registers"], 386)

    def test_no_retime_is_none(self):
        # a base arm's log: the table of another command must not be read
        self.assertIsNone(self._parse("global_placement\n 1 | 2 | 3 | 4 | -1.0 | -2.0 | 5\n"))

    def test_refusal_is_an_error(self):
        r = self._parse("retime\n[ERROR RET-0040] The design has 2 clocks.\n")
        self.assertTrue(r["error"].startswith("[ERROR RET-0040]"))


class VerdictTest(unittest.TestCase):
    def test_paired_draw_and_scale(self):
        rows = [
            {
                "key": "k%d" % i,
                "sigma_ps": 10.0,
                "arms": {
                    "base": {"period_ps": 1000.0},
                    "seed2": {"period_ps": 1000.0 + (10 if i % 2 else -10)},
                    "rt": {"period_ps": 950.0},
                    "rt_seed2": {"period_ps": 950.0 + (10 if i % 2 else -10)},
                },
            }
            for i in range(4)
        ]
        v = retime.verdicts(rows)
        self.assertEqual(v["sigma_scale"], 1.0)  # seed RMS z < 1: no scaling
        self.assertEqual(v["rt"]["better"], 4)
        self.assertEqual(retime.verdict_word(v["rt"]), "better, above the floor")
        # rt_seed2 is judged against seed2, the same seed
        self.assertAlmostEqual(v["rt_seed2"]["per_design"]["k1"]["delta_ps"], -50.0)

    def test_headroom(self):
        self.assertAlmostEqual(retime.headroom_pct({"period": 10, "floor": 6}), 40.0)
        self.assertIsNone(retime.headroom_pct({"period": 10, "floor": None}))


if __name__ == "__main__":
    unittest.main()
