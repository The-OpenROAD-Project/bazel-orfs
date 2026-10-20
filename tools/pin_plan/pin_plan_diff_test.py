"""pin_plan_diff.py reads pin_plan.tcl's outputs and counts what moved."""

import os
import tempfile
import unittest

import pin_plan_diff


def write(d, name, text):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(text)
    return path


class PinPlanDiffTest(unittest.TestCase):
    def test_diff(self):
        with tempfile.TemporaryDirectory() as d:
            a_pins = write(
                d,
                "a_pins.tcl",
                "# header\n"
                "set_io_pin_constraint -region top:1.000-5.000 -pin_names {{x[0]} {x[1]}}\n"
                "set_io_pin_constraint -region right:2.000-4.000 -pin_names {y}\n",
            )
            b_pins = write(
                d,
                "b_pins.tcl",
                "set_io_pin_constraint -region top:1.500-5.000 -pin_names {x[0]}\n"
                "set_io_pin_constraint -region right:2.000-4.000 -pin_names {x[1] y}\n",
            )
            a_macros = write(
                d,
                "a_macros.tcl",
                "place_macro -macro_name {u/rf} -location {10.0 20.0} -orientation R0 -exact\n",
            )
            b_macros = write(
                d,
                "b_macros.tcl",
                "place_macro -macro_name {u/rf} -location {11.0 18.0} -orientation MX -exact\n",
            )
            a_rep = write(d, "a.txt", "total 3 pins, 2 facing away from their logic\n")
            b_rep = write(d, "b.txt", "total 3 pins, 1 facing away from their logic\n")
            out = os.path.join(d, "out.txt")
            pin_plan_diff.main(
                [out, "place", "grt", a_rep, b_rep, a_macros, b_macros, a_pins, b_pins]
            )
            with open(out) as f:
                text = f.read()
        self.assertIn("place: 3 pins, 2 facing away", text)
        self.assertIn("a_pins.tcl: 1 of 3 pins on another side", text)
        self.assertIn("x[1]: top -> right", text)
        self.assertIn("ends moved 0.500 um", text)
        self.assertIn(
            "u/rf: (10.000, 20.000) R0 -> (11.000, 18.000) MX, 3.000 um", text
        )
        self.assertIn(
            "summary: 1 of 3 planned pins on another side, macros moved at most 3.000 um",
            text,
        )

    def test_different_pins_stop(self):
        a = {"top": (0.0, 1.0, ["x"])}
        b = {"top": (0.0, 1.0, ["y"])}
        with self.assertRaises(ValueError):
            pin_plan_diff.diff_pins(a, b)


if __name__ == "__main__":
    unittest.main()
