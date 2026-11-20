import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emit  # noqa: E402

FP = {
    "die": [100.0, 80.0],
    "core": [2, 2, 98, 78],
    "macros": {
        "A": {
            "block": "BlockA",
            "place": [10.08, 4.32],
            "shape": [40.032, 30.24],
            "orient": "R0",
            "pins": {
                "E": [
                    {
                        "bus": "q",
                        "partner": "B",
                        "bits": 64,
                        "range": [1.0, 6.0],
                        "layer": "M4",
                    }
                ],
                "N": [
                    {
                        "bus": "d",
                        "partner": "GLUE",
                        "bits": 8,
                        "range": [0.0, 1.5],
                        "layer": "M5",
                    }
                ],
            },
        }
    },
    "internal_placement": {
        "A": [
            {
                "inst": "ram\\[0\\]",
                "place": [5.0, 5.0],
                "shape": [10.0, 20.0],
                "walls": [],
            }
        ]
    },
}


class EmitTest(unittest.TestCase):
    def test_block_outline(self):
        a = emit.block_args(FP, "A", 1.0)
        self.assertEqual(a["DIE_AREA"], "0.000 0.000 40.032 30.240")
        self.assertEqual(a["CORE_AREA"], "1.000 1.000 39.032 29.240")

    def test_block_pins_per_bus(self):
        t = emit.block_pins(FP, "A")
        self.assertIn(
            "set_io_pin_constraint -region right:1.000-6.000 -pin_names [floorplan_pins {q}]",
            t,
        )
        self.assertIn("-region top:0.000-1.500", t)

    def test_guidance_around_the_rough_place(self):
        t = emit.block_guidance(FP, "A", 2.0)
        self.assertIn(
            "set_macro_guidance_region -macro_name {ram[0]} -region {3.000 3.000 17.000 27.000}",
            t,
        )

    def test_parent(self):
        self.assertEqual(emit.parent_args(FP)["CORE_AREA"], "2.000 2.000 98.000 78.000")
        t = emit.parent_place(FP)
        self.assertIn("eq {BlockA}", t)
        self.assertIn("-location {10.080 4.320} -orientation R0 -exact", t)

    def test_infeasible_plan_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.json")
            with open(p, "w") as f:
                json.dump({}, f)
            with self.assertRaises(SystemExit) as e:
                emit.main(
                    [
                        "parent",
                        p,
                        "--args",
                        os.path.join(d, "a"),
                        "--place",
                        os.path.join(d, "b"),
                    ]
                )
            self.assertIn("infeasible", str(e.exception))


if __name__ == "__main__":
    unittest.main()
