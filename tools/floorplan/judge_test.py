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

    def test_side_band_and_calibration(self):
        _, macros = judge.parse_macros(MACROS)
        report = REPORT + [
            "violation type: Vertical congestion",
            "\tcomment: capacity:10 usage:13 congestion:3",
            "\tbbox = (40.0000, 195.0000) - (42.0000, 197.0000) on Layer M3",
            "violation type: Vertical congestion",
            "\tcomment: capacity:10 usage:12 congestion:2",
            "\tbbox = (40.0000, 150.0000) - (42.0000, 152.0000) on Layer M3",
        ]
        verdict = {
            "channels": [
                {"channel": "A|B", "direction": "h", "utilisation": 1.4},
                {"channel": "A|die", "direction": "v", "utilisation": 1.1},
                {"channel": "B|die", "direction": "h", "utilisation": 0.5},
                {"channel": "die|die", "direction": "h", "utilisation": 0.2},
            ],
            "sides": [
                {
                    "macro": "B",
                    "side": "N",
                    "bits": 900,
                    "lowest": "M3",
                    "track_spacing": {"M3": 1.1},
                    "lateral": [],
                    "partners": ["GLUE"],
                },
                {
                    "macro": "A",
                    "side": "N",
                    "bits": 100,
                    "lowest": "M3",
                    "track_spacing": {"M3": 9.0},
                    "lateral": [],
                    "partners": ["B"],
                },
                {
                    "macro": "B",
                    "side": "S",
                    "bits": 100,
                    "lowest": "M3",
                    "track_spacing": {"M3": 6.0},
                    "lateral": [],
                    "partners": ["A"],
                },
            ],
        }
        out = judge.judge(
            judge.parse_report(report),
            macros,
            verdict,
            {"BlockA": "A", "BlockB": "B"},
            10.0,
        )
        self.assertEqual(out["route"]["B side N"]["overflow"], 3)
        self.assertEqual(out["route"]["over B"]["overflow"], 2)
        ch = out["calibration"]["channels"]
        self.assertEqual((ch["clean"], ch["overflowing"]), (2, 2))
        self.assertAlmostEqual(ch["limit"], (0.5 * 1.1) ** 0.5, places=3)
        sides = out["calibration"]["facing_sides"]
        self.assertAlmostEqual(sides["limit"], (1.1 * 6.0) ** 0.5, places=3)
        self.assertGreater(sides["tau_b"], 0)


if __name__ == "__main__":
    unittest.main()
