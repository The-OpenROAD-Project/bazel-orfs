import json
import os
import tempfile
import unittest
from unittest import mock

import pin_plan as P

TECH = {
    "pitch_um": {"H": 0.048, "V": 0.048},
    "min_tracks": 2,
    "margin": 1.5,
    "track_density_per_um": 48.6,
    "usable": 0.5,
}


def plan(macros, nets, **kw):
    p = {
        "tech": TECH,
        "growth": 1.0,
        "util": 1.0,
        "channel_um": 40,
        "gcell_um": 20,
        "macros": macros,
        "nets": nets,
    }
    p.update(kw)
    return p


class PinsPerUm(unittest.TestCase):

    def test_one_layer_two_tracks_margin(self):
        self.assertAlmostEqual(P.pins_per_um(TECH, "E"), 1 / (0.048 * 2 * 1.5))
        self.assertAlmostEqual(P.pins_per_um(TECH, "N"), 1 / (0.048 * 2 * 1.5))


class Sides(unittest.TestCase):

    def test_side_toward(self):
        a = [0, 0, 100, 100]
        self.assertEqual(P.side_toward(a, [140, 20, 100, 50]), "E")
        self.assertEqual(P.side_toward(a, [-200, 0, 100, 100]), "W")
        self.assertEqual(P.side_toward(a, [0, 140, 100, 100]), "S")
        self.assertEqual(P.side_toward(a, [0, -300, 100, 100]), "N")


class Abutment(unittest.TestCase):

    def setUp(self):
        self.p = plan(
            {"A": {"fixed_shape": [100, 100]}, "B": {"fixed_shape": [100, 100]}},
            [["A", "B", 300]],
            die={"w": 280, "h": 140},
            placement={"A": [20, 20, 100, 100], "B": [140, 20, 100, 100]},
        )

    def test_facing_edges_line_up(self):
        r = P.evaluate(self.p, self.p["placement"], P.die_for(self.p))
        sides = {(e["macro"], e["side"]): e for e in r["edges"]}
        a, b = sides[("A", "E")]["order"][0], sides[("B", "W")]["order"][0]
        self.assertLess(max(a[2], b[2]), min(a[3], b[3]))
        self.assertEqual(r["routes"][0]["kind"], "facing")

    def test_over_one_layer_needs_two(self):
        self.p["nets"] = [["A", "B", 900]]
        r = P.evaluate(self.p, self.p["placement"], P.die_for(self.p))
        e = [e for e in r["edges"] if e["macro"] == "A"][0]
        self.assertEqual(e["layers"], 2)
        self.assertGreater(e["util_one_layer"], 1)


class Routing(unittest.TestCase):

    def test_wall_forces_channel(self):
        p = plan(
            {
                "A": {"fixed_shape": [100, 100]},
                "W": {"fixed_shape": [100, 300]},
                "B": {"fixed_shape": [100, 100]},
            },
            [["A", "B", 100]],
            die={"w": 420, "h": 400},
            placement={
                "A": [20, 120, 100, 100],
                "W": [160, 0, 100, 340],
                "B": [300, 120, 100, 100],
            },
        )
        r = P.evaluate(p, p["placement"], P.die_for(p))
        route = [x for x in r["routes"] if {x["a"], x["b"]} == {"A", "B"}][0]
        self.assertEqual(route["kind"], "channel")
        self.assertGreater(route["len_um"], 280)

    def test_enclosed_is_over_a_macro(self):
        p = plan(
            {
                "A": {"fixed_shape": [100, 100]},
                "W": {"fixed_shape": [100, 400]},
                "B": {"fixed_shape": [100, 100]},
            },
            [["A", "B", 100]],
            die={"w": 420, "h": 400},
            placement={
                "A": [20, 120, 100, 100],
                "W": [160, 0, 100, 400],
                "B": [300, 120, 100, 100],
            },
        )
        r = P.evaluate(p, p["placement"], P.die_for(p))
        self.assertEqual(r["routes"][0]["kind"], "OVER A MACRO")

    def test_memory_blocks_routing(self):
        p = plan(
            {"A": {"fixed_shape": [100, 100]}, "B": {"fixed_shape": [100, 100]}},
            [["A", "B", 100]],
            die={"w": 420, "h": 400},
            memories=[[160, 0, 100, 400]],
            placement={"A": [20, 120, 100, 100], "B": [300, 120, 100, 100]},
        )
        r = P.evaluate(p, p["placement"], P.die_for(p))
        self.assertEqual(r["routes"][0]["kind"], "OVER A MACRO")

    def test_overflow_counted(self):
        p = plan(
            {
                "A": {"fixed_shape": [100, 100]},
                "W": {"fixed_shape": [100, 300]},
                "B": {"fixed_shape": [100, 100]},
            },
            [["A", "B", 3000]],
            die={"w": 420, "h": 360},
            placement={
                "A": [20, 120, 100, 100],
                "W": [160, 0, 100, 330],
                "B": [300, 120, 100, 100],
            },
        )
        r = P.evaluate(p, p["placement"], P.die_for(p))
        self.assertGreater(r["max_gcell_util"], 1)


class Solve(unittest.TestCase):

    def mock_plan(self):
        return plan(
            {
                "A": {"std_um2": 10000},
                "B": {"std_um2": 10000},
                "C": {"std_um2": 10000},
                "T": {"std_um2": 10000, "soft": True},
            },
            [["A", "B", 500], ["B", "C", 500], ["A", "T", 200], ["C", "T", 200]],
            die_slack=[3.0],
            die_aspects=[1.0],
            tune_dies=1,
            aspects=[0.5, 1.0],
        )

    def test_deterministic(self):
        self.assertEqual(P.solve(self.mock_plan()), P.solve(self.mock_plan()))

    def test_heavy_pair_adjacent(self):
        r = P.solve(self.mock_plan())
        a, b = r["rects"]["A"], r["rects"]["B"]
        self.assertLessEqual(P.gap_between(a, b), self.mock_plan()["channel_um"] + 1e-6)

    def test_no_overlap(self):
        r = P.solve(self.mock_plan())
        names = sorted(r["rects"])
        for i, x in enumerate(names):
            for y in names[i + 1 :]:
                ra, rb = r["rects"][x], r["rects"][y]
                ox = min(ra[0] + ra[2], rb[0] + rb[2]) - max(ra[0], rb[0])
                oy = min(ra[1] + ra[3], rb[1] + rb[3]) - max(ra[1], rb[1])
                self.assertFalse(ox > 1e-6 and oy > 1e-6, (x, y))


class Placer(unittest.TestCase):

    def toy(self):
        return plan(
            {
                "A": {"fixed_shape": [100, 100]},
                "B": {"fixed_shape": [100, 100]},
                "C": {"fixed_shape": [100, 100]},
                "D": {"fixed_shape": [200, 100]},
                "T": {"std_um2": 20000, "soft": True, "whitespace": True},
            },
            [["A", "B", 1000], ["B", "C", 50], ["C", "D", 50], ["A", "T", 100]],
            die={"w": 600, "h": 600},
        )

    def test_overlap_free_and_inside(self):
        p = self.toy()
        rects = P.place(p, P.shapes_for(p, {}), (600, 600))
        names = sorted(rects)
        for i, x in enumerate(names):
            r = rects[x]
            self.assertTrue(
                r[0] >= 0 and r[1] >= 0 and r[0] + r[2] <= 600 and r[1] + r[3] <= 600
            )
            for y in names[i + 1 :]:
                self.assertLessEqual(min(P.overlap_pen(r, rects[y], 0)), 1e-6, (x, y))

    def test_deterministic(self):
        p = self.toy()
        self.assertEqual(
            P.place(p, P.shapes_for(p, {}), (600, 600)),
            P.place(p, P.shapes_for(p, {}), (600, 600)),
        )

    def test_heavy_pair_close(self):
        p = self.toy()
        rects = P.place(p, P.shapes_for(p, {}), (600, 600))
        (ax, ay), (bx, by) = P.center(rects["A"]), P.center(rects["B"])
        halo = P.halos(p, P.shapes_for(p, {}))
        self.assertLessEqual(
            abs(ax - bx) + abs(ay - by), 100 + halo["A"] + halo["B"] + 1e-6
        )

    def test_bounded_wirelength(self):
        p = self.toy()
        rects = P.place(p, P.shapes_for(p, {}), (600, 600))
        worst = sum(w for _, _, w in p["nets"]) * 1200
        self.assertLess(P.wirelength(p, rects, (600, 600)), 0.25 * worst)

    def test_too_small_die_is_none(self):
        p = self.toy()
        self.assertIsNone(P.place(p, P.shapes_for(p, {}), (150, 150)))


class Main(unittest.TestCase):

    def test_main_writes_result(self):
        p = plan(
            {"A": {"fixed_shape": [100, 100]}, "B": {"fixed_shape": [100, 100]}},
            [["A", "B", 10]],
            die={"w": 280, "h": 140},
            placement={"A": [20, 20, 100, 100], "B": [140, 20, 100, 100]},
        )
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "p.json"), os.path.join(d, "r.json")
            with open(src, "w") as f:
                json.dump(p, f)
            with mock.patch("builtins.print"):
                self.assertEqual(P.main([src, "--evaluate", "--out", out]), 0)
            with open(out) as f:
                self.assertIn("edges", json.load(f))


if __name__ == "__main__":
    unittest.main()
