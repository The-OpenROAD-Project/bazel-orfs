"""plan_floorplan on a synthetic parent: legal, sized by the pins, timed."""

import ast
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_floorplan  # noqa: E402

TECH = {
    "pin_pitch_um": 0.096,
    "pin_layers": 2,
    "track_density_per_um": 48.6,
    "wire_ps_per_um": 0.6,
    "site_um": 0.054,
    "row_um": 0.27,
}
MARGINS = {
    "pin_side": 1.5,
    "channel_min_um": 40,
    "lateral": 0.5,
    "aspect_cap": 3.0,
    "gap_um": 10.8,
}


def plan(macros, cell_area=1.3e6, density=0.5):
    return {
        "tech": TECH,
        "parent": {
            "cell_area_um2": cell_area,
            "density": density,
            "core_margin_um": 10,
        },
        "margins": MARGINS,
        "macros": macros,
    }


class ShapeTest(unittest.TestCase):
    def test_square_when_the_pins_fit(self):
        # 3294 pins need 237 um; the square is 954: square, pins at 3.45/um
        s = plan_floorplan.shape(
            {"name": "a", "pins": 3294, "area_um2": 910000}, TECH, MARGINS
        )
        self.assertAlmostEqual(s["pin_side_um"], 954, 0)
        self.assertAlmostEqual(s["depth_um"], 954, 0)
        self.assertFalse(s["two_sides"])
        self.assertAlmostEqual(s["pins_per_um"], 3294 / 954.0, 1)

    def test_pins_stretch_the_side_when_the_square_is_too_short(self):
        # 6000 pins need 432 um; a 90000 um2 block is 300 square: 432 by 208
        s = plan_floorplan.shape(
            {"name": "b", "pins": 6000, "area_um2": 90000}, TECH, MARGINS
        )
        self.assertAlmostEqual(s["pin_side_um"], 6000 * 0.096 * 1.5 / 2, 0)
        self.assertAlmostEqual(s["pin_side_um"] * s["depth_um"], 90000, -1)
        self.assertFalse(s["two_sides"])

    def test_wide_interface_goes_on_two_sides(self):
        # 13000 pins need 936 um; a 140000 um2 block is 374 square, cap 3
        s = plan_floorplan.shape(
            {"name": "c", "pins": 13000, "area_um2": 140000}, TECH, MARGINS
        )
        self.assertTrue(s["two_sides"])
        self.assertAlmostEqual(s["pin_side_um"], 13000 * 0.096 * 1.5 / 2 / 2, 0)

    def test_channel_floor_and_lateral(self):
        s = plan_floorplan.shape(
            {"name": "d", "pins": 100, "area_um2": 250000}, TECH, MARGINS
        )
        self.assertEqual(s["channel_um"], 40)
        s = plan_floorplan.shape(
            {"name": "e", "pins": 10508, "area_um2": 990000}, TECH, MARGINS
        )
        self.assertAlmostEqual(s["channel_um"], 10508 / 48.6 * 0.5, 1)


LATTICE = dict(TECH, lattice_x_um=0.144, lattice_y_um=2.16)


class LatticeTest(unittest.TestCase):
    def test_outline_and_origins_on_the_lattice(self):
        p = plan(LayoutTest.MACROS)
        p["tech"] = LATTICE
        out = plan_floorplan.layout(p)
        self.assertEqual(plan_floorplan.check(out), [])
        for m in out["macros"]:
            for v in (m["w_um"], m["h_um"]):
                self.assertAlmostEqual(v / 2.16, round(v / 2.16), 6)
            self.assertAlmostEqual(m["x_um"] / 0.144, round(m["x_um"] / 0.144), 6)
            self.assertAlmostEqual(m["y_um"] / 2.16, round(m["y_um"] / 2.16), 6)
            self.assertGreaterEqual(m["w_um"] * m["h_um"], m["area_um2"])

    def test_no_lattice_no_rounding(self):
        s = plan_floorplan.shape(
            {"name": "a", "pins": 100, "area_um2": 250000}, TECH, MARGINS
        )
        self.assertEqual(s["pin_side_um"], 500.0)


class EmitTest(unittest.TestCase):
    def test_files_for_the_flows(self):
        macros = [dict(m) for m in LayoutTest.MACROS]
        macros[0]["keep"] = ["Bpu", "Ftq"]
        macros.append({"name": "Wide", "pins": 13000, "area_um2": 140000})
        p = plan(macros)
        p["tech"] = LATTICE
        out = plan_floorplan.layout(p)
        d = tempfile.mkdtemp(prefix="plan_emit.")
        written = plan_floorplan.emit(out, p, d)
        names = sorted(os.path.basename(w) for w in written)
        self.assertEqual(
            names,
            sorted(
                [m["name"] + "_pins.tcl" for m in macros]
                + ["place_macros.tcl", "plan.bzl"]
            ),
        )
        bzl = open(os.path.join(d, "plan.bzl")).read()
        plan_dict = ast.literal_eval(bzl.split("PLAN = ", 1)[1])
        self.assertEqual(
            plan_dict["macros"]["Frontend"]["SYNTH_KEEP_MODULES"], "Bpu Ftq"
        )
        self.assertNotIn("SYNTH_KEEP_MODULES", plan_dict["macros"]["MemBlock"])
        x0, y0, x1, y1 = [float(v) for v in plan_dict["parent"]["CORE_AREA"].split()]
        self.assertEqual((x0, y0), (10.0, 10.0))
        self.assertAlmostEqual(x1, out["die_um"][2] - 10, 3)
        by = {m["name"]: m for m in out["macros"]}
        pins = open(os.path.join(d, "Frontend_pins.tcl")).read()
        self.assertIn("-region %s:*" % by["Frontend"]["pin_side"], pins)
        wide = open(os.path.join(d, "Wide_pins.tcl")).read()
        self.assertEqual(wide.count("set_io_pin_constraint"), 2)
        place = open(os.path.join(d, "place_macros.tcl")).read()
        self.assertIn(
            "  Frontend {:.3f} {:.3f}".format(
                by["Frontend"]["x_um"], by["Frontend"]["y_um"]
            ),
            place,
        )
        self.assertIn("-orientation R0 -exact", place)
        self.assertIn("setPlacementStatus FIRM", place)
        self.assertIn(
            "rtl_macro_placer", place
        )  # the parent's own macros, around the plan's


class SegmentTest(unittest.TestCase):
    def test_segments_face_the_partner(self):
        macros = [dict(m) for m in LayoutTest.MACROS]
        p = plan(macros)
        p["tech"] = LATTICE
        out = plan_floorplan.layout(p)
        by = {m["name"]: m for m in out["macros"]}
        # two partners on opposite ends of the region, and the parent's logic
        left = min(out["macros"], key=lambda m: m["x_um"] + m["w_um"] / 2)
        right = max(out["macros"], key=lambda m: m["x_um"] + m["w_um"] / 2)
        target = [m for m in out["macros"] if m not in (left, right)][0]
        d = tempfile.mkdtemp(prefix="plan_seg.")
        dump = os.path.join(d, "partners.txt")
        with open(dump, "w") as f:
            for i in range(10):
                f.write("pin %s a%d %s\n" % (target["name"], i, left["name"]))
            for i in range(30):
                f.write("pin %s b%d %s\n" % (target["name"], i, right["name"]))
            for i in range(20):
                f.write("pin %s c%d logic\n" % (target["name"], i))
            for i in range(7):
                f.write("pin %s d%d port\n" % (target["name"], i))
            f.write("pin %s e0 unconnected\n" % target["name"])
            f.write("pin %s VDD unconnected\n" % target["name"])  # dropped
        p["pin_partners"] = dump
        plan_floorplan.emit(out, p, d)
        all_segs = by[target["name"]]["pin_segments"]
        segs = [s_ for s_ in all_segs if s_["side"] == target["pin_side"]]
        outer = [s_ for s_ in all_segs if s_["side"] != target["pin_side"]]
        self.assertEqual(len(segs), 3)
        # ports and the unconnected pin on the outer side, whole side
        self.assertEqual(sorted(o["partner"] for o in outer), ["port", "unconnected"])
        self.assertEqual(
            {o["side"] for o in outer}, {plan_floorplan.OUTER[target["pin_side"]]}
        )
        self.assertTrue(all(o["lo_um"] is None for o in outer))
        if target["pin_side"] in ("top", "bottom"):
            # the left partner's segment comes first along x
            self.assertEqual(segs[0]["partner"], left["name"])
            self.assertEqual(segs[-1]["partner"], right["name"])
        edge = plan_floorplan.SEGMENT_EDGE_UM
        self.assertAlmostEqual(segs[0]["lo_um"], edge)
        side_len = (
            target["w_um"]
            if target["pin_side"] in ("top", "bottom")
            else target["h_um"]
        )
        self.assertAlmostEqual(segs[-1]["hi_um"], side_len - edge, 2)
        # lengths by pin count: 10:30:20
        lens = [s["hi_um"] - s["lo_um"] for s in segs]
        self.assertAlmostEqual(sum(lens), side_len - 2 * edge, 2)
        for s_, l in zip(segs, lens):
            self.assertAlmostEqual(l / (side_len - 2 * edge), s_["pins"] / 60.0, 3)
        text = open(os.path.join(d, target["name"] + "_pins.tcl")).read()
        # 3 segments, 2 outer-side groups, the rest
        self.assertEqual(text.count("set_io_pin_constraint -region"), 6)
        self.assertNotIn("VDD", text)
        self.assertIn("lsearch -exact $names $n", text)  # only the block's own pins
        self.assertIn(
            "-region %s:* -pin_names $seg" % plan_floorplan.OUTER[target["pin_side"]],
            text,
        )
        self.assertIn(
            "-region %s:%.3f-" % (target["pin_side"], plan_floorplan.SEGMENT_EDGE_UM),
            text,
        )


class ExactPinTest(unittest.TestCase):
    LAYERS = {
        "pin_layers_v": [
            {"name": "M3", "pitch": 0.036, "offset": 0.009, "width": 0.018},
            {"name": "M5", "pitch": 0.048, "offset": 0.012, "width": 0.024},
        ],
        "pin_layers_h": [
            {"name": "M4", "pitch": 0.048, "offset": 0.012, "width": 0.024}
        ],
    }

    def test_pins_on_tracks_two_apart_inside_the_segment(self):
        m = {"name": "a", "pin_side": "top", "w_um": 100.0, "h_um": 50.0}
        segs = [("b", 5.0, 25.0, ["p%d" % i for i in range(60)])]
        rows = plan_floorplan.place_exact(m, segs, dict(TECH, **self.LAYERS))
        self.assertEqual(len(rows), 60)
        self.assertEqual({r[1] for r in rows}, {"M3", "M5"})
        for pin, layer, x, y, w, h in rows:
            lay = [l for l in self.LAYERS["pin_layers_v"] if l["name"] == layer][0]
            self.assertAlmostEqual(
                (x - lay["offset"]) / lay["pitch"],
                round((x - lay["offset"]) / lay["pitch"]),
                6,
            )
            self.assertGreaterEqual(x, 5.0 - lay["pitch"])
            self.assertLessEqual(x, 25.0 + lay["pitch"])
            self.assertAlmostEqual(y, 50.0 - 0.18)
        for layer in ("M3", "M5"):
            xs = sorted(r[2] for r in rows if r[1] == layer)
            lay = [l for l in self.LAYERS["pin_layers_v"] if l["name"] == layer][0]
            for a, b in zip(xs, xs[1:]):
                self.assertGreaterEqual(b - a, 2 * lay["pitch"] - 1e-6)

    def test_refuses_a_segment_too_short(self):
        m = {"name": "a", "pin_side": "top", "w_um": 100.0, "h_um": 50.0}
        segs = [("b", 5.0, 6.0, ["p%d" % i for i in range(200)])]
        with self.assertRaises(SystemExit):
            plan_floorplan.place_exact(m, segs, dict(TECH, **self.LAYERS))

    def test_emit_places_exactly_when_the_tech_has_layers(self):
        macros = [dict(m) for m in LayoutTest.MACROS]
        p = plan(macros)
        p["tech"] = dict(LATTICE, **self.LAYERS)
        out = plan_floorplan.layout(p)
        target = out["macros"][0]
        d = tempfile.mkdtemp(prefix="plan_exact.")
        dump = os.path.join(d, "partners.txt")
        with open(dump, "w") as f:
            for i in range(40):
                f.write("pin %s a%d logic\n" % (target["name"], i))
            for i in range(6):
                f.write("pin %s d%d port\n" % (target["name"], i))
        p["pin_partners"] = dump
        plan_floorplan.emit(out, p, d)
        text = open(os.path.join(d, target["name"] + "_pins.tcl")).read()
        self.assertEqual(text.count("\n  a"), 40)
        self.assertEqual(text.count("\n  d"), 6)
        self.assertIn("place_pin -pin_name $pin -layer $layer", text)
        self.assertIn("-force_to_die_boundary", text)
        self.assertEqual(text.count("set_io_pin_constraint"), 1)  # the rest, whole side
        self.assertEqual(target["pins_placed_exact"], 46)


class MirroredOrderTest(unittest.TestCase):
    def test_both_ends_of_an_interface_share_one_order(self):
        d = tempfile.mkdtemp(prefix="plan_mirror.")
        dump = os.path.join(d, "partners.txt")
        # A's pins a0..a2 talk to B's pins in scrambled correspondence
        pairs = [("a0", "b2"), ("a1", "b0"), ("a2", "b1")]
        with open(dump, "w") as f:
            for a, b in pairs:
                f.write("pin A %s B %s\n" % (a, b))
                f.write("pin B %s A %s\n" % (b, a))
            f.write("pin B c9 logic -\n")
        groups = plan_floorplan.read_partners(dump)
        self.assertEqual(groups["A"]["B"], ["a0", "a1", "a2"])  # A leads, name order
        self.assertEqual(groups["B"]["A"], ["b2", "b0", "b1"])  # B follows A's order
        self.assertEqual(groups["B"]["logic"], ["c9"])


class LayoutTest(unittest.TestCase):
    MACROS = [
        {"name": "Frontend", "pins": 3294, "area_um2": 910000, "slack_ps": 300},
        {"name": "MemBlock", "pins": 10508, "area_um2": 990000, "slack_ps": 120},
        {"name": "VecRegion", "pins": 9253, "area_um2": 650000, "slack_ps": 500},
        {"name": "FpRegion", "pins": 5099, "area_um2": 440000, "slack_ps": 50},
    ]

    def test_legal_and_facing(self):
        out = plan_floorplan.layout(plan(self.MACROS))
        self.assertEqual(plan_floorplan.check(out), [])
        for m in out["macros"]:
            self.assertEqual(m["orient"], "R0")
            self.assertEqual(m["pin_side"], plan_floorplan.FACING[m["region_side"]])
        # two squares per side on two opposite sides is the smallest die here
        self.assertEqual(len({m["region_side"] for m in out["macros"]}), 2)

    def test_region_holds_the_cells_and_the_die_holds_all(self):
        out = plan_floorplan.layout(plan(self.MACROS))
        x0, y0, x1, y1 = out["region_um"]
        self.assertGreaterEqual((x1 - x0) * (y1 - y0), 1.3e6 / 0.5 * 0.999)
        self.assertGreater(out["utilisation"], 0.5)
        self.assertLess(out["utilisation"], 0.9)

    def test_wire_delay_flags_the_tight_cut(self):
        out = plan_floorplan.layout(plan(self.MACROS))
        by = {m["name"]: m for m in out["macros"]}
        self.assertIn(
            "FpRegion", out["timing_failures"]
        )  # 50 ps cannot pay ~450 ps of wire
        self.assertGreater(by["VecRegion"]["slack_after_wire_ps"], 0)
        self.assertNotIn("VecRegion", out["timing_failures"])

    def test_no_macros(self):
        out = plan_floorplan.layout(plan([]))
        self.assertEqual(out["macros"], [])
        self.assertEqual(plan_floorplan.check(out), [])


if __name__ == "__main__":
    unittest.main()
