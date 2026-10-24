"""carve_hops.py: a path whose logic sits in one macro is inside it, wire
anywhere; the rest are bundles by their macros in order."""

import io
import unittest

import carve_hops

CARVE = "core/ctrl/rob=ROB core/ctrl=DISP core/vec=VEC core=GLUE"
CROSSINGS = [
    # dispatch only, a wire stretch through the parent between
    "2300\tparent\tX:a:b:2300\tW=400\tU=core/ctrl/dispatch:900:10,core:300:0,core/ctrl/decode:800:5\tE=x\tH=50\n",
    # vec into dispatch
    "2200\tparent\tX:a:b:2200\tW=200\tU=core/vec/iq:200:7,core/ctrl/dispatch:1500:20\tE=y\tH=40\n",
    # dispatch into the ROB: the longer prefix wins
    "2100\tparent\tX:a:b:2100\tW=100\tU=core/ctrl:400:2,core/ctrl/rob/vtype:1300:20\tE=z\tH=30\n",
]
CONES = ["VEC>DISP\t1\t1\t12\t3.5\t4\t0\n"]


class CarveHops(unittest.TestCase):
    def test_longest_prefix(self):
        carve = carve_hops.parse_carve(CARVE)
        self.assertEqual(carve_hops.macro("core/ctrl/rob/vtype", carve), "ROB")
        self.assertEqual(carve_hops.macro("core/ctrl", carve), "DISP")
        self.assertEqual(carve_hops.macro("core/backend", carve), "GLUE")
        self.assertEqual(carve_hops.macro("l2top", carve), "TOP")

    def test_inside_and_bundles(self):
        carve = carve_hops.parse_carve(CARVE)
        inside, floors, bundles = carve_hops.score(
            carve_hops.read_paths(CROSSINGS), carve, wire=0.5
        )
        self.assertEqual(inside["DISP"], [2300])  # the wire stretch is not a hop
        self.assertEqual(floors["DISP"], (2300, 2100))
        self.assertEqual(sorted(bundles), ["DISP>ROB", "VEC>DISP"])
        _, seq = bundles["VEC>DISP"][0]
        self.assertEqual(seq, [["VEC", 200, 7], ["DISP", 1500, 20]])

    def test_render(self):
        carve = carve_hops.parse_carve(CARVE)
        out = io.StringIO()
        carve_hops.render(
            *carve_hops.score(carve_hops.read_paths(CROSSINGS), carve, 0.5),
            carve_hops.read_cones(CONES),
            0.5,
            out,
        )
        text = out.getvalue()
        self.assertIn("inside one macro: 1 endpoints, crossing: 2", text)
        self.assertIn("VEC>DISP", text)


if __name__ == "__main__":
    unittest.main()
