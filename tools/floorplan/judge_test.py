import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge  # noqa: E402

REPORT = """violation type: Horizontal congestion
\tsrcs: net:a net:b
\tcomment: capacity:10 usage:14 congestion:4
\tbbox = (50.0000, 105.0000) - (52.0000, 107.0000) on Layer M4
violation type: Vertical congestion
\tsrcs: net:c
\tcomment: capacity:10 usage:11 congestion:1
\tbbox = (205.0000, 10.0000) - (207.0000, 12.0000) on Layer M5
""".splitlines()

MACROS = """die 300 300
macro u_a BlockA 0 0 100 100
macro u_b BlockB 0 110 100 200
""".splitlines()


class JudgeTest(unittest.TestCase):
    def test_regions(self):
        r = judge.parse_report(REPORT)
        self.assertEqual(r[0], ("h", "M4", 50.0, 105.0, 52.0, 107.0, 4))
        self.assertEqual(r[1][0], "v")

    def test_agreement(self):
        _, macros = judge.parse_macros(MACROS)
        verdict = {
            "findings": [
                {
                    "rung": "channel_capacity",
                    "status": "fail",
                    "kind": "over_capacity",
                    "channel": "A|B",
                },
                {
                    "rung": "channel_capacity",
                    "status": "fail",
                    "kind": "over_capacity",
                    "channel": "B|die",
                },
            ]
        }
        out = judge.judge(
            judge.parse_report(REPORT), macros, verdict, {"BlockA": "A", "BlockB": "B"}
        )
        self.assertEqual(out["route"]["A|B"]["overflow"], 4)
        self.assertEqual(out["agree"], ["A|B"])
        self.assertEqual(out["missed"], ["A|die"])
        self.assertEqual(out["false_alarms"], ["B|die"])


if __name__ == "__main__":
    unittest.main()
