"""pin_plan.py: partners at one offset, every pin on its layer's tracks."""

import unittest

import pin_plan

PORTS = {
    "a_in": {"bits": [2, 3]},
    "clk": {"bits": [4]},
    "a_out": {"bits": [5, 6]},
    "clk_out": {"bits": [7]},
    "w_in": {"bits": [8, 9, 10]},
    "w_out": {"bits": [11, 12, 13]},
    "clk_south": {"bits": [14]},
}
SIDES = {
    "west": ["a_in", "clk"],
    "east": ["a_out", "clk_out"],
    "north": ["w_in"],
    "south": ["w_out", "clk_south"],
}


def parse(lines):
    out = {}
    for line in lines:
        pin, side, layer, *rect = line.split()
        out[pin] = (side, layer, [float(v) for v in rect])
    return out


class PinPlan(unittest.TestCase):
    def setUp(self):
        self.w, self.h = 10.08, 8.64
        self.p = parse(pin_plan.plan(PORTS, SIDES, self.w, self.h))

    def test_every_bit_once(self):
        self.assertEqual(len(self.p), 13)
        self.assertIn("a_in[1]", self.p)
        self.assertIn("clk", self.p)

    def test_partners_meet(self):
        # a pin and its partner at the same offset along their edges
        for a, b in [("a_in[0]", "a_out[0]"), ("clk", "clk_out")]:
            ra, rb = self.p[a][2], self.p[b][2]
            self.assertEqual((ra[1], ra[3]), (rb[1], rb[3]))
            self.assertEqual(ra[0], 0.0)
            self.assertAlmostEqual(rb[2], self.w)
        ra, rb = self.p["w_in[2]"][2], self.p["w_out[2]"][2]
        self.assertEqual((ra[0], ra[2]), (rb[0], rb[2]))
        self.assertAlmostEqual(ra[3], self.h)
        self.assertEqual(rb[1], 0.0)

    def test_on_tracks(self):
        for pin, (side, layer, r) in self.p.items():
            off, pitch, width = pin_plan.TRACKS[layer]
            centre = (
                (r[0] + r[2]) / 2 if side in ("north", "south") else (r[1] + r[3]) / 2
            )
            k = (centre - off) / pitch
            self.assertAlmostEqual(k, round(k), places=6, msg=pin)
            self.assertAlmostEqual(
                abs(r[2] - r[0]) if side in ("north", "south") else abs(r[3] - r[1]),
                width,
            )

    def test_too_short_a_side(self):
        many = {"x": {"bits": list(range(400))}, "y": {"bits": list(range(400))}}
        with self.assertRaises(ValueError):
            pin_plan.plan(many, {"west": ["x"], "east": ["y"]}, 5.0, 4.32)


if __name__ == "__main__":
    unittest.main()
