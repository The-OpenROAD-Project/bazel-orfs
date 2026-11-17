"""plan_floorplan on a synthetic parent: legal, sized by the pins, timed."""

import ast
import json
import os
import re
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

    def test_min_side_holds_a_wide_macro_of_its_own(self):
        # a 250000 um2 block is 500 square; one 577 um wide macro inside
        s = plan_floorplan.shape(
            {"name": "f", "pins": 100, "area_um2": 250000, "min_side_um": 600},
            TECH,
            MARGINS,
        )
        self.assertAlmostEqual(s["pin_side_um"], 600, 0)
        self.assertAlmostEqual(s["pin_side_um"] * s["depth_um"], 250000, -1)

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

    def test_gcell_on_the_lattice(self):
        # a block's gcells are the parent's: origin and die on 0.57 um too
        p = plan(LayoutTest.MACROS)
        p["tech"] = dict(LATTICE, gcell_um=0.57)
        out = plan_floorplan.layout(p)
        self.assertEqual(plan_floorplan.check(out), [])
        for m in out["macros"]:
            for v in (m["x_um"], m["y_um"], m["own_w_um"], m["own_h_um"]):
                self.assertAlmostEqual(v / 0.57, round(v / 0.57), 6)
            # the cells it dissolves into the top level land on its sites
            self.assertAlmostEqual(m["x_um"] / 0.054, round(m["x_um"] / 0.054), 6)
            self.assertAlmostEqual(m["x_um"] / 0.144, round(m["x_um"] / 0.144), 6)
            self.assertAlmostEqual(m["y_um"] / 2.16, round(m["y_um"] / 2.16), 6)

    def test_no_lattice_no_rounding(self):
        s = plan_floorplan.shape(
            {"name": "a", "pins": 100, "area_um2": 250000}, TECH, MARGINS
        )
        self.assertEqual(s["pin_side_um"], 500.0)


class EmitTest(unittest.TestCase):
    def test_files_for_the_flows(self):
        macros = [dict(m) for m in LayoutTest.MACROS]
        macros[0]["keep"] = ["Bpu", "Ftq"]
        macros.append({"name": "Leaf", "pins": 300, "area_um2": 20000, "keep": []})
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
        # a block that keeps nothing says so: it flattens everything
        self.assertEqual(plan_dict["macros"]["Leaf"]["SYNTH_KEEP_MODULES"], "")
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
        # each row carries the outline the plan made room for, and the script
        # stops before place_macro when the built macro is another size,
        # instead of place_macro blaming the neighbour it overlaps (MPL-0041)
        self.assertIn(
            "  Frontend {:.3f} {:.3f} {:.3f} {:.3f}".format(
                by["Frontend"]["x_um"],
                by["Frontend"]["y_um"],
                by["Frontend"]["w_um"],
                by["Frontend"]["h_um"],
            ),
            place,
        )
        self.assertIn("proc plan_check_size", place)
        self.assertIn("utl::error FLW 3", place)
        self.assertEqual(
            place.count("  plan_check_size "), place.count("  place_macro ")
        )
        self.assertIn("-orientation R0 -exact", place)
        self.assertIn("setPlacementStatus FIRM", place)
        self.assertIn(
            "rtl_macro_placer", place
        )  # the parent's own macros, around the plan's
        # the blocks' band: rows below the lowest top of the bottom row are
        # removed, so no parent cell lands in a pocket under a shorter block
        # or in a channel between two (take 23, 7 percent of the overflow)
        bottom = [m for m in out["macros"] if m["region_side"] == "bottom"]
        self.assertTrue(bottom)
        lowest_top = min(m["y_um"] + m["h_um"] for m in bottom)
        lowest_bottom = min(m["y_um"] for m in bottom)
        band = "  {:.3f} {:.3f}".format(lowest_bottom, lowest_top)
        self.assertIn(band, place)
        self.assertIn("odb::dbBlockage_create $block", place)
        self.assertIn("$bl setSoft", place)  # gpl blocks its sites, dpl skips it
        self.assertNotIn("dbRow_destroy", place)  # the rows stay: strays need sites
        self.assertEqual(plan_floorplan.block_bands(out)[0], band)
        # the port strip: rows between the band and the die edge for the
        # parent's port buffers (take 24: without it the legaliser carried
        # 4 309 of them a millimetre each)
        self.assertGreaterEqual(lowest_bottom, plan_floorplan.PORT_STRIP_UM + 10.0)


class RegionTest(unittest.TestCase):
    def _out(self):
        p = plan([dict(m) for m in LayoutTest.MACROS])
        return p, plan_floorplan.layout(p)

    def test_regions_in_place_macros_not_in_plan_bzl(self):
        p, out = self._out()
        x0, y0, x1, y1 = out["region_um"]
        box = [x0 + 10.0, y0 + 10.0, x0 + 110.0, y0 + 60.0]
        p["parent"]["regions"] = [
            {"name": "ctrl", "instance": "core/backend/inner_ctrlBlock", "box_um": box}
        ]
        d = tempfile.mkdtemp(prefix="plan_regions.")
        plan_floorplan.emit(out, p, d)
        place = open(os.path.join(d, "place_macros.tcl")).read()
        self.assertIn(
            "\n  ctrl core/backend/inner_ctrlBlock %.3f %.3f %.3f %.3f\n" % tuple(box),
            place,
        )
        self.assertIn("odb::dbGroup_create $region $name", place)
        # the Tcl around the rows, escapes and continuation as Tcl reads
        # them: a kept module's name holds its divider escaped
        self.assertIn('set iname [string map {\\\\ ""} [$inst getName]]', place)
        # and a flattened module's dotted names
        self.assertIn("[string first $prefix. $iname] == 0", place)
        self.assertIn("round($y0 * $dbu) }] \\\n    [expr", place)
        # plan.bzl feeds synthesis: a region must not re-key it
        self.assertNotIn("inner_ctrlBlock", open(os.path.join(d, "plan.bzl")).read())

    def test_no_regions_no_rows(self):
        p, out = self._out()
        d = tempfile.mkdtemp(prefix="plan_regions.")
        plan_floorplan.emit(out, p, d)
        place = open(os.path.join(d, "place_macros.tcl")).read()
        self.assertIn("foreach {name prefix x0 y0 x1 y1} {\n\n}", place)

    def test_a_region_over_a_block_stops_the_plan(self):
        p, out = self._out()
        m = out["macros"][0]
        p["parent"]["regions"] = [
            {
                "name": "bad",
                "instance": "core/x",
                "box_um": [m["x_um"], m["y_um"], m["x_um"] + 5.0, m["y_um"] + 5.0],
            }
        ]
        with self.assertRaises(SystemExit) as e:
            plan_floorplan.emit(out, p, tempfile.mkdtemp(prefix="plan_regions."))
        self.assertIn("overlaps block %s" % m["name"], str(e.exception))

    def test_a_region_outside_the_die_stops_the_plan(self):
        p, out = self._out()
        dx = out["die_um"][2]
        p["parent"]["regions"] = [
            {
                "name": "out",
                "instance": "core/x",
                "box_um": [dx - 5.0, 0.0, dx + 5.0, 5.0],
            }
        ]
        with self.assertRaises(SystemExit) as e:
            plan_floorplan.emit(out, p, tempfile.mkdtemp(prefix="plan_regions."))
        self.assertIn("not inside the die", str(e.exception))


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
        # ports and the unconnected pin on the outer side, a segment each,
        # the two not overlapping
        self.assertEqual(sorted(o["partner"] for o in outer), ["port", "unconnected"])
        self.assertEqual(
            {o["side"] for o in outer}, {plan_floorplan.OUTER[target["pin_side"]]}
        )
        a, b = sorted(outer, key=lambda o: o["lo_um"])
        self.assertLessEqual(a["hi_um"], b["lo_um"] + 1e-6)
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
        # the outer groups as intervals of the outer side, not the whole side
        self.assertNotIn(
            "-region %s:* -pin_names $seg" % plan_floorplan.OUTER[target["pin_side"]],
            text,
        )
        self.assertIn("-region %s:" % plan_floorplan.OUTER[target["pin_side"]], text)
        self.assertIn(
            "-region %s:%.3f-" % (target["pin_side"], plan_floorplan.SEGMENT_EDGE_UM),
            text,
        )


class FacingSideTest(unittest.TestCase):
    """pins_any_edge: a partner that is m's direct neighbour in its row gets
    the edge facing it; anything else, the region side (None)."""

    ROW = [
        {
            "name": "A",
            "region_side": "bottom",
            "x_um": 0.0,
            "y_um": 0.0,
            "w_um": 100.0,
            "h_um": 100.0,
        },
        {
            "name": "B",
            "region_side": "bottom",
            "x_um": 110.0,
            "y_um": 0.0,
            "w_um": 100.0,
            "h_um": 100.0,
        },
        {
            "name": "C",
            "region_side": "bottom",
            "x_um": 220.0,
            "y_um": 0.0,
            "w_um": 100.0,
            "h_um": 100.0,
        },
        {
            "name": "T",
            "region_side": "top",
            "x_um": 0.0,
            "y_um": 300.0,
            "w_um": 100.0,
            "h_um": 100.0,
        },
    ]

    def setUp(self):
        self.by = {m["name"]: dict(m) for m in self.ROW}

    def test_neighbours_face_each_other(self):
        self.assertEqual(
            plan_floorplan.facing_side(self.by["A"], "B", self.by), "right"
        )
        self.assertEqual(plan_floorplan.facing_side(self.by["B"], "A", self.by), "left")

    def test_a_block_between_keeps_the_region_side(self):
        self.assertIsNone(plan_floorplan.facing_side(self.by["A"], "C", self.by))

    def test_across_the_region_and_logic_keep_the_region_side(self):
        self.assertIsNone(plan_floorplan.facing_side(self.by["A"], "T", self.by))
        self.assertIsNone(plan_floorplan.facing_side(self.by["A"], "logic", self.by))

    def test_too_far_apart_keeps_the_region_side(self):
        self.by["B"]["x_um"] = 290.0
        self.by.pop("C")
        self.assertIsNone(plan_floorplan.facing_side(self.by["A"], "B", self.by))


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

    def test_pins_are_their_layers_wire_width(self):
        # at two widths, a parent's pin access found no access point on
        # any asap7 M3 pin (DRT-0073)
        widths = {
            l["name"]: l["width"]
            for l in self.LAYERS["pin_layers_v"] + self.LAYERS["pin_layers_h"]
        }
        for side, n in (("top", 0), ("right", 1)):
            m = {"name": "a", "pin_side": side, "w_um": 100.0, "h_um": 50.0}
            segs = [("b", 5.0, 25.0, ["p%d" % i for i in range(20)])]
            rows = plan_floorplan.place_exact(m, segs, dict(TECH, **self.LAYERS))
            for pin, layer, x, y, w, h in rows:
                self.assertAlmostEqual((w, h)[n], widths[layer], 6)

    def test_refuses_a_segment_too_short(self):
        m = {"name": "a", "pin_side": "top", "w_um": 100.0, "h_um": 50.0}
        segs = [("b", 5.0, 6.0, ["p%d" % i for i in range(200)])]
        with self.assertRaises(SystemExit):
            plan_floorplan.place_exact(m, segs, dict(TECH, **self.LAYERS))

    def test_ports_and_unconnected_share_the_outer_side_without_overlap(self):
        # each outer group used to take the whole side: MemBlock's 156 port
        # and 925 unconnected pins landed on the same tracks (GRT-0080)
        macros = [dict(m) for m in LayoutTest.MACROS]
        p = plan(macros)
        p["tech"] = dict(LATTICE, **self.LAYERS)
        out = plan_floorplan.layout(p)
        target = out["macros"][0]
        d = tempfile.mkdtemp(prefix="plan_outer.")
        dump = os.path.join(d, "partners.txt")
        with open(dump, "w") as f:
            for i in range(40):
                f.write("pin %s a%d logic\n" % (target["name"], i))
            for i in range(20):
                f.write("pin %s d%d port\n" % (target["name"], i))
            for i in range(20):
                f.write("pin %s u%d unconnected\n" % (target["name"], i))
        p["pin_partners"] = dump
        plan_floorplan.emit(out, p, d)
        text = open(os.path.join(d, target["name"] + "_pins.tcl")).read()
        rows = [
            l.split()
            for l in text.splitlines()
            if len(l.split()) == 6 and l.split()[0][0] in "adu"
        ]
        self.assertEqual(len({r[0] for r in rows}), 80)
        spots = [(r[1], r[2], r[3]) for r in rows]
        self.assertEqual(len(spots), len(set(spots)))

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
        # a pin the dump does not name stops the block: every pin is the plan's
        self.assertEqual(text.count("set_io_pin_constraint"), 0)
        self.assertIn("utl::error FLW 4", text)
        # and the parent's holes read the table alone
        self.assertIn("::plan_pins_only", text)
        self.assertEqual(target["pins_placed_exact"], 46)
        # a block whose pins the plan places is still a block of the plan:
        # one row in place_macros.tcl and one entry in plan.bzl, and none
        # of its pin rows leak into the macro rows (the emit once reused
        # the macro row list for the pins and skipped the block's entry)
        place = open(os.path.join(d, "place_macros.tcl")).read()
        for m in out["macros"]:
            self.assertIn(
                "\n  %s %.3f %.3f %.3f %.3f\n"
                % (m["name"], m["x_um"], m["y_um"], m["w_um"], m["h_um"]),
                place,
            )
        self.assertNotIn("\n  a0 ", place)
        scope = {}
        exec(open(os.path.join(d, "plan.bzl")).read(), scope)
        self.assertEqual(
            sorted(scope["PLAN"]["macros"]), sorted(m["name"] for m in out["macros"])
        )
        self.assertEqual(
            scope["PLAN"]["macros"][target["name"]]["pin_side"], target["pin_side"]
        )


class MockFootprintTest(unittest.TestCase):
    """A block's outline is its own flow's; the parent places its footprint,
    the outline scaled so its core holds the measured content at
    block_density, and the block's mocked abstract gets its pins on that
    footprint from a pin file of its own."""

    def _plan(self, mocked):
        macros = [dict(m) for m in LayoutTest.MACROS]
        if mocked:
            for m in macros:
                m["content_um2"] = 0.45 * m["area_um2"]
        p = plan(macros)
        p["tech"] = dict(LATTICE, **ExactPinTest.LAYERS)
        if mocked:
            p["margins"] = dict(MARGINS, block_density=0.6)
        return p

    def test_footprint_for_the_parent_outline_for_the_block(self):
        plain = plan_floorplan.layout(self._plan(False))
        p = self._plan(True)
        out = plan_floorplan.layout(p)
        target = out["macros"][0]
        d = tempfile.mkdtemp(prefix="plan_mock.")
        dump = os.path.join(d, "partners.txt")
        with open(dump, "w") as f:
            for i in range(40):
                f.write("pin %s a%d logic\n" % (target["name"], i))
        p["pin_partners"] = dump
        written = [os.path.basename(w) for w in plan_floorplan.emit(out, p, d)]
        scope = {}
        exec(open(os.path.join(d, "plan.bzl")).read(), scope)
        by_content = 0
        for m in out["macros"]:
            entry = scope["PLAN"]["macros"][m["name"]]
            f = float(entry["MOCK_AREA"])
            self.assertLess(f, 1.0)
            # the block's own die is its outline, unscaled
            x0, y0, x1, y1 = [float(v) for v in entry["DIE_AREA"].split()]
            self.assertAlmostEqual(x1, m["own_w_um"], 3)
            self.assertAlmostEqual(y1, m["own_h_um"], 3)
            # the parent places the outline scaled by the factor
            self.assertAlmostEqual(m["w_um"], m["own_w_um"] * f, 1)
            self.assertAlmostEqual(m["h_um"], m["own_h_um"] * f, 1)
            # its core holds the content at block_density, unless its pins
            # need more side
            core = (m["w_um"] - 20) * (m["h_um"] - 20)
            content = plan_floorplan.plan_macro(p, m["name"])["content_um2"]
            need = (
                m["pins"]
                * TECH["pin_pitch_um"]
                * MARGINS["pin_side"]
                / TECH["pin_layers"]
            )
            if m["two_sides"]:
                need /= 2.0
            if f > need / m["own_side_um"] + 1e-3:
                self.assertAlmostEqual(core, content / 0.6, delta=0.01 * core)
                by_content += 1
            self.assertIn(m["name"] + "_mock_pins.tcl", written)
        self.assertGreater(by_content, 0)  # the content, not only the pins, sized some
        self.assertLess(out["die_area_mm2"], plain["die_area_mm2"])

        def rows(name):
            text = open(os.path.join(d, name)).read()
            return [l.split() for l in text.splitlines() if l.startswith("  a")]

        own, mock = rows(target["name"] + "_pins.tcl"), rows(
            target["name"] + "_mock_pins.tcl"
        )
        self.assertEqual(len(own), 40)
        self.assertEqual([r[0] for r in own], [r[0] for r in mock])  # same order
        for r in own:
            self.assertLessEqual(float(r[2]), target["own_w_um"])
            self.assertLessEqual(float(r[3]), target["own_h_um"])
        for r in mock:
            self.assertLessEqual(float(r[2]), target["w_um"])
            self.assertLessEqual(float(r[3]), target["h_um"])

    def test_pins_floor_the_footprint(self):
        m = {"name": "Wide", "pins": 13000, "area_um2": 400000, "content_um2": 1000}
        sh = plan_floorplan.shape(m, LATTICE, dict(MARGINS, block_density=0.6), 10)
        need = (
            13000
            * LATTICE["pin_pitch_um"]
            * MARGINS["pin_side"]
            / LATTICE["pin_layers"]
        )
        if sh["two_sides"]:
            need /= 2.0
        self.assertGreaterEqual(sh["fp_side_um"] + 0.01, need)

    def test_no_content_no_mock(self):
        sh = plan_floorplan.shape(LayoutTest.MACROS[0], LATTICE, MARGINS, 10)
        self.assertEqual(sh["mock_area"], 1.0)


class HeldSideTest(unittest.TestCase):
    def test_region_side_holds(self):
        free = plan_floorplan.layout(plan([dict(m) for m in LayoutTest.MACROS]))
        sides = {m["name"]: m["region_side"] for m in free["macros"]}
        held = [
            dict(m, region_side=OPPOSITE[sides[m["name"]]]) for m in LayoutTest.MACROS
        ]
        out = plan_floorplan.layout(plan(held))
        for m in out["macros"]:
            self.assertEqual(m["region_side"], OPPOSITE[sides[m["name"]]])
        self.assertGreaterEqual(
            out["die_area_mm2"], free["die_area_mm2"] - 1e-9
        )  # the free choice is the smallest


OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}


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


class NetlistTest(unittest.TestCase):
    def test_netlists_in_a_row_along_the_region_top(self):
        p = plan([dict(m) for m in LayoutTest.MACROS])
        p["tech"] = LATTICE
        p["netlists"] = [
            {"module": "A", "instance": "top/a", "w_um": 300.0, "h_um": 200.0},
            {"module": "B", "instance": "top/b", "w_um": 400.0, "h_um": 250.0},
            {
                "module": "C",
                "instance": "top/c",
                "w_um": 100.0,
                "h_um": 100.0,
                "x_um": 50.0,
                "y_um": 60.0,
            },
        ]
        out = plan_floorplan.layout(p)
        rows = plan_floorplan.place_netlists(out, p)
        x0, y0, x1, y1 = out["region_um"]
        gap = p["margins"]["gap_um"]
        self.assertEqual([r[0] for r in rows], ["A", "B", "C"])
        self.assertAlmostEqual(rows[0][2], x0 + gap, 3)
        self.assertAlmostEqual(rows[0][3], y1 - gap - 200.0, 3)
        self.assertAlmostEqual(rows[1][2], x0 + gap + 300.0 + gap, 3)
        self.assertEqual(rows[2][2:4], (50.0, 60.0))
        d = tempfile.mkdtemp(prefix="plan_netlists.")
        plan_floorplan.emit(out, p, d)
        text = open(os.path.join(d, "place_macros.tcl")).read()
        self.assertIn(
            "  top/a %.3f %.3f %.3f %.3f\n" % (rows[0][2], rows[0][3], 300.0, 200.0),
            text,
        )
        bzl = open(os.path.join(d, "plan.bzl")).read()
        self.assertIn('"netlists"', bzl)

    def test_region_grows_to_hold_the_row(self):
        p = plan([dict(m) for m in LayoutTest.MACROS])
        p["netlists"] = [
            {"module": "Big", "instance": "top/big", "w_um": 5000.0, "h_um": 700.0}
        ]
        out = plan_floorplan.layout(p)
        x0, y0, x1, y1 = out["region_um"]
        gap = p["margins"]["gap_um"]
        self.assertGreaterEqual(x1 - x0, 5000.0 + 2 * gap - 1e-6)
        self.assertGreaterEqual(y1 - y0, 700.0 + 2 * gap - 1e-6)
        rows = plan_floorplan.place_netlists(out, p)
        self.assertEqual([r[0] for r in rows], ["Big"])
        self.assertEqual(plan_floorplan.check(out), [])

    def test_refuses_when_the_row_overflows(self):
        # a region laid out without the netlist cannot take it afterwards
        out = plan_floorplan.layout(plan([dict(m) for m in LayoutTest.MACROS]))
        p = plan([dict(m) for m in LayoutTest.MACROS])
        p["netlists"] = [
            {"module": "Big", "instance": "top/big", "w_um": 5000.0, "h_um": 10.0}
        ]
        with self.assertRaises(SystemExit):
            plan_floorplan.place_netlists(out, p)

    def _owner_plan(self, netlists):
        p = plan([dict(m) for m in LayoutTest.MACROS])
        p["netlists"] = netlists
        out = plan_floorplan.layout(p)
        return p, out, plan_floorplan.place_netlists(out, p)

    def test_netlist_centred_on_its_owner(self):
        out = plan_floorplan.layout(plan([dict(m) for m in LayoutTest.MACROS]))
        x0, y0, x1, y1 = out["region_um"]
        owner = [x0 + 0.7 * (x1 - x0), y0 + 0.4 * (y1 - y0)]
        p, out, rows = self._owner_plan(
            [
                {
                    "module": "A",
                    "instance": "top/rob/a",
                    "w_um": 300.0,
                    "h_um": 200.0,
                    "owner_um": owner,
                }
            ]
        )
        (r,) = rows
        self.assertAlmostEqual(r[2] + 150.0, owner[0], 2)
        self.assertAlmostEqual(r[3] + 100.0, owner[1], 2)

    def test_owner_outside_the_region_stays_inside(self):
        p, out, rows = self._owner_plan(
            [
                {
                    "module": "A",
                    "instance": "top/a",
                    "w_um": 300.0,
                    "h_um": 200.0,
                    "owner_um": [-1000.0, 1e6],
                }
            ]
        )
        x0, y0, x1, y1 = out["region_um"]
        gap = p["margins"]["gap_um"]
        (r,) = rows
        self.assertAlmostEqual(r[2], x0 + gap, 3)
        self.assertAlmostEqual(r[3], y1 - gap - 200.0, 3)

    def test_netlists_sharing_an_owner_do_not_overlap(self):
        out = plan_floorplan.layout(plan([dict(m) for m in LayoutTest.MACROS]))
        x0, y0, x1, y1 = out["region_um"]
        owner = [(x0 + x1) / 2.0, (y0 + y1) / 2.0]
        items = [
            {
                "module": "A",
                "instance": "top/rob/a",
                "w_um": 300.0,
                "h_um": 200.0,
                "owner_um": owner,
            },
            {
                "module": "B",
                "instance": "top/rob/b",
                "w_um": 200.0,
                "h_um": 100.0,
                "owner_um": owner,
            },
            # in the row along the top, which the owners' files keep clear of
            {"module": "C", "instance": "top/c", "w_um": 100.0, "h_um": 100.0},
        ]
        p, out, rows = self._owner_plan(items)
        gap = p["margins"]["gap_um"]
        x0, y0, x1, y1 = out["region_um"]
        boxes = [r[2:] for r in rows]
        for i in range(len(boxes)):
            x, y, w, h = boxes[i]
            self.assertGreaterEqual(x, x0 + gap - 1e-6)
            self.assertGreaterEqual(y, y0 + gap - 1e-6)
            self.assertLessEqual(x + w, x1 - gap + 1e-6)
            self.assertLessEqual(y + h, y1 - gap + 1e-6)
            for j in range(i):
                self.assertFalse(plan_floorplan._overlaps(boxes[i], boxes[j], gap))
        # the first is on its owner; the second as near as the first allows
        self.assertAlmostEqual(boxes[0][0] + 150.0, owner[0], 2)
        d = abs(boxes[1][0] + 100.0 - owner[0]) + abs(boxes[1][1] + 50.0 - owner[1])
        self.assertLessEqual(d, 150.0 + 50.0 + 2 * gap + gap)

    def test_region_holds_a_netlist_at_its_owner(self):
        p, out, rows = self._owner_plan(
            [
                {
                    "module": "Big",
                    "instance": "top/big",
                    "w_um": 5000.0,
                    "h_um": 700.0,
                    "owner_um": [0.0, 0.0],
                }
            ]
        )
        x0, y0, x1, y1 = out["region_um"]
        gap = p["margins"]["gap_um"]
        self.assertGreaterEqual(x1 - x0, 5000.0 + 2 * gap - 1e-6)
        self.assertGreaterEqual(y1 - y0, 700.0 + 2 * gap - 1e-6)
        self.assertEqual(plan_floorplan.check(out), [])

    def test_a_fixed_corner_wins_over_the_owner(self):
        p, out, rows = self._owner_plan(
            [
                {
                    "module": "A",
                    "instance": "top/a",
                    "w_um": 100.0,
                    "h_um": 100.0,
                    "x_um": 50.0,
                    "y_um": 60.0,
                    "owner_um": [900.0, 900.0],
                }
            ]
        )
        self.assertEqual(rows[0][2:4], (50.0, 60.0))


class LoadTest(unittest.TestCase):
    def test_partners_relative_to_the_plan(self):
        d = tempfile.mkdtemp(prefix="plan_load.")
        with open(os.path.join(d, "plan.json"), "w") as f:
            json.dump({"pin_partners": "pin_partners.txt"}, f)
        p = plan_floorplan.load_plan(os.path.join(d, "plan.json"))
        self.assertEqual(p["pin_partners"], os.path.join(d, "pin_partners.txt"))


class FoldTest(unittest.TestCase):
    def test_unplanned_partners_are_logic(self):
        g = {
            "MemBlock": ["a"],
            "logic": ["b"],
            "array_256x66": ["c"],
            "port": ["d"],
            "unconnected": ["e"],
            "Me": ["f"],
        }
        f = plan_floorplan.fold_partners(g, {"MemBlock", "Me"}, "Me")
        self.assertEqual(sorted(f), ["Me", "MemBlock", "logic", "port", "unconnected"])
        self.assertEqual(f["logic"], ["b", "c"])


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

    def test_region_aspect_cap(self):
        """A strip of a region is what two rows of blocks make; the cap
        trades die area for a squarer region, and without it nothing moves."""
        free = plan_floorplan.layout(plan(self.MACROS, cell_area=0.45e6, density=0.2))
        x0, y0, x1, y1 = free["region_um"]
        free_aspect = max(x1 - x0, y1 - y0) / min(x1 - x0, y1 - y0)
        self.assertGreater(free_aspect, 1.2)
        cap = (1 + free_aspect) / 2
        p = plan(self.MACROS, cell_area=0.45e6, density=0.2)
        p["margins"] = dict(MARGINS, region_aspect_max=cap)
        capped = plan_floorplan.layout(p)
        x0, y0, x1, y1 = capped["region_um"]
        self.assertLessEqual(max(x1 - x0, y1 - y0) / min(x1 - x0, y1 - y0), cap + 1e-6)
        self.assertEqual(plan_floorplan.check(capped), [])

    def test_per_macro_pin_side_margin_and_channel(self):
        """One block's own margin lengthens its pin side and widens its
        channel; the other blocks keep the plan's."""
        base = plan_floorplan.layout(plan([dict(m) for m in self.MACROS]))
        macros = [dict(m) for m in self.MACROS]
        macros[1]["pin_side_margin"] = 2.5
        macros[1]["channel_min_um"] = 150
        out = plan_floorplan.layout(plan(macros))
        by = {m["name"]: m for m in out["macros"]}
        was = {m["name"]: m for m in base["macros"]}
        self.assertGreater(
            by["MemBlock"]["pin_side_um"], was["MemBlock"]["pin_side_um"]
        )
        self.assertEqual(by["MemBlock"]["channel_um"], 150)
        for n in ("Frontend", "VecRegion", "FpRegion"):
            self.assertEqual(by[n]["pin_side_um"], was[n]["pin_side_um"])
            self.assertEqual(by[n]["channel_um"], was[n]["channel_um"])
        self.assertEqual(plan_floorplan.check(out), [])

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


def _dump(d, lines):
    path = os.path.join(d, "pin_partners.txt")
    with open(path, "w") as f:
        for block, partner, n in lines:
            for i in range(n):
                f.write("pin %s p%d_%s %s -\n" % (block, i, partner, partner))
    return path


class PartnerLayoutTest(unittest.TestCase):
    """Blocks that talk to each other sit close, and the ones that talk to
    the parent's ports sit on its port side, facing them."""

    MACROS = LayoutTest.MACROS

    def _distance(self, out, a, b):
        by = {m["name"]: m for m in out["macros"]}

        def centre(m):
            return (m["x_um"] + m["w_um"] / 2.0, m["y_um"] + m["h_um"] / 2.0)

        (xa, ya), (xb, yb) = centre(by[a]), centre(by[b])
        return abs(xa - xb) + abs(ya - yb)

    def test_partners_sit_close_within_the_die_bound(self):
        base = plan_floorplan.layout(plan(self.MACROS))
        with tempfile.TemporaryDirectory() as d:
            p = plan(self.MACROS)
            p["pin_partners"] = _dump(
                d,
                [
                    ("MemBlock", "VecRegion", 1000),
                    ("VecRegion", "MemBlock", 1000),
                    ("MemBlock", "logic", 5000),
                    ("VecRegion", "logic", 3000),
                ],
            )
            out = plan_floorplan.layout(p)
        self.assertEqual(plan_floorplan.check(out), [])
        # the smallest die puts these two in opposite rows, 3.4 mm apart
        self.assertLess(
            self._distance(out, "MemBlock", "VecRegion"),
            self._distance(base, "MemBlock", "VecRegion") / 2,
        )
        self.assertLessEqual(
            out["die_area_mm2"],
            base["die_area_mm2"] * (1 + plan_floorplan.DIE_SLACK) + 1e-6,
        )
        self.assertIsNotNone(out["partner_pin_um"])

    def test_port_block_on_the_port_side(self):
        with tempfile.TemporaryDirectory() as d:
            p = plan(self.MACROS)
            p["parent"]["port_side"] = "bottom"
            p["parent"]["ports"] = 1500
            p["pin_partners"] = _dump(
                d,
                [
                    ("VecRegion", "port", 1200),
                    ("VecRegion", "logic", 2000),
                    ("MemBlock", "logic", 5000),
                    ("Frontend", "logic", 3000),
                    ("FpRegion", "logic", 3000),
                ],
            )
            out = plan_floorplan.layout(p)
            self.assertEqual(out["port_side"], "bottom")
            by = {m["name"]: m for m in out["macros"]}
            self.assertEqual(by["VecRegion"]["region_side"], "bottom")
            written = plan_floorplan.emit(out, p, d)
            names = [os.path.basename(w) for w in written]
            self.assertIn("parent_pins.tcl", names)
            with open(os.path.join(d, "parent_pins.tcl")) as f:
                self.assertIn("-region bottom:*", f.read())
            with open(os.path.join(d, "plan.bzl")) as f:
                self.assertIn('"pins": "parent_pins.tcl"', f.read())
        self.assertEqual(plan_floorplan.check(out), [])

    def test_partner_layout_off_keeps_the_smallest_die(self):
        """With partner_layout false the partners only report their wire;
        the arrangement is the smallest die's, the port side still holds."""
        base = plan_floorplan.layout(plan(self.MACROS))
        with tempfile.TemporaryDirectory() as d:
            p = plan(self.MACROS)
            p["parent"]["partner_layout"] = False
            p["pin_partners"] = _dump(
                d,
                [
                    ("MemBlock", "VecRegion", 1000),
                    ("VecRegion", "MemBlock", 1000),
                    ("MemBlock", "logic", 5000),
                    ("VecRegion", "logic", 3000),
                ],
            )
            out = plan_floorplan.layout(p)
        self.assertEqual(
            [
                (m["name"], m["region_side"], m["x_um"], m["y_um"])
                for m in out["macros"]
            ],
            [
                (m["name"], m["region_side"], m["x_um"], m["y_um"])
                for m in base["macros"]
            ],
        )
        self.assertIsNotNone(out["partner_pin_um"])

    def test_port_pins_of_a_block_off_the_port_side_face_the_region(self):
        """A block that is not on the port side reaches the ports through
        the region: its port pins share its pin side, none on its outer."""
        groups = {"logic": ["a", "b"], "port": ["p0", "p1"], "unconnected": ["u"]}
        inner, outer = plan_floorplan.split_groups(groups, ports_outer=False)
        self.assertEqual(sorted(inner), ["logic", "port"])
        self.assertEqual(sorted(outer), ["unconnected"])
        inner, outer = plan_floorplan.split_groups(groups)
        self.assertEqual(sorted(outer), ["port", "unconnected"])

    def test_port_side_keeps_room_for_the_parents_own_ports(self):
        """300 ports the parent's logic drives need their stretch of the
        port side open to the region, beside the blocks there."""
        with tempfile.TemporaryDirectory() as d:
            lines = [("VecRegion", "port", 1200), ("VecRegion", "logic", 2000)]
            p = plan(self.MACROS)
            p["parent"]["port_side"] = "bottom"
            p["parent"]["ports"] = 1200
            p["pin_partners"] = _dump(d, lines)
            tight = plan_floorplan.layout(p)
            p["parent"]["ports"] = 1200 + 30000
            roomy = plan_floorplan.layout(p)
        x0, _, x1, _ = roomy["region_um"]
        spans = sum(m["w_um"] for m in roomy["macros"] if m["region_side"] == "bottom")
        free = 30000 * TECH["pin_pitch_um"] * MARGINS["pin_side"] / TECH["pin_layers"]
        self.assertGreaterEqual(x1 - x0, spans + free - 1e-3)
        self.assertGreaterEqual(roomy["die_area_mm2"], tight["die_area_mm2"])


class CornerTest(unittest.TestCase):
    """region_order and side_align hold blocks at a corner of the region:
    the plan puts the blocks whose crossings end in one unit of the parent
    (XiangShan's decode buffer) next to each other at the corner nearest it,
    instead of centred along their sides, where a crossing would run half
    the region."""

    def _plan(self):
        macros = [
            {
                "name": "Rob",
                "pins": 300,
                "area_um2": 40000,
                "region_side": "left",
                "region_order": 1,
            },
            {
                "name": "Vec",
                "pins": 300,
                "area_um2": 40000,
                "region_side": "left",
                "region_order": 0,
            },
            {
                "name": "Flt",
                "pins": 300,
                "area_um2": 40000,
                "region_side": "top",
                "region_order": 0,
            },
            {
                "name": "Mem",
                "pins": 300,
                "area_um2": 40000,
                "region_side": "top",
                "region_order": 1,
            },
        ]
        p = plan(macros, cell_area=1.0e6)
        p["margins"] = dict(MARGINS, side_align={"left": "end", "top": "start"})
        return p

    def test_held_at_the_top_left_corner(self):
        out = plan_floorplan.layout(self._plan())
        self.assertEqual(plan_floorplan.check(out), [])
        by = {m["name"]: m for m in out["macros"]}
        x0, y0, x1, y1 = out["region_um"]
        # left side, bottom to top: Vec, then Rob, Rob's top at the corner
        self.assertLess(by["Vec"]["y_um"], by["Rob"]["y_um"])
        self.assertAlmostEqual(by["Rob"]["y_um"] + by["Rob"]["h_um"], y1, delta=3)
        # top side, left to right: Flt at the corner, then Mem
        self.assertLess(by["Flt"]["x_um"], by["Mem"]["x_um"])
        self.assertAlmostEqual(by["Flt"]["x_um"], x0, delta=3)

    def test_without_them_the_blocks_are_centred(self):
        p = self._plan()
        p["margins"] = MARGINS
        for m in p["macros"]:
            del m["region_order"]
        out = plan_floorplan.layout(p)
        by = {m["name"]: m for m in out["macros"]}
        x0, y0, x1, y1 = out["region_um"]
        self.assertGreater(by["Flt"]["x_um"] - x0, 3)


class StablePinTest(unittest.TestCase):
    """--previous keeps a previous plan's pins: a block whose interface did
    not change gets a byte-identical pins file, so its flow stays a cache
    hit when a neighbour gains ports (each regenerated plan used to slide
    every pin of every block and rebuild them all)."""

    def _emit(self, d, dump_lines, previous=None):
        macros = [dict(m) for m in LayoutTest.MACROS]
        p = plan(macros)
        p["tech"] = dict(LATTICE, **ExactPinTest.LAYERS)
        out = plan_floorplan.layout(p)
        dump = os.path.join(d, "partners.txt")
        with open(dump, "w") as f:
            f.write("".join(dump_lines))
        p["pin_partners"] = dump
        plan_floorplan.emit(out, p, d, previous)
        return out

    def _dump(self, names, extra=0):
        a, b = names[0], names[1]
        lines = ["pin %s a%d logic\n" % (a, i) for i in range(40)]
        lines += ["pin %s x%d %s\n" % (a, i, b) for i in range(10)]
        lines += ["pin %s x%d %s\n" % (b, i, a) for i in range(10)]
        lines += ["pin %s b%d logic\n" % (b, i) for i in range(30)]
        # the change: a gains pins toward its logic
        lines += ["pin %s n%d logic\n" % (a, i) for i in range(extra)]
        return lines

    def _rows(self, d, name):
        text = open(os.path.join(d, name + "_pins.tcl")).read()
        body = text.split("set ::plan_pins(%s) {\n" % name, 1)[1].split("\n}", 1)[0]
        return {l.split()[0]: l for l in body.splitlines() if l.strip()}

    def test_unchanged_interface_is_byte_identical(self):
        names = [m["name"] for m in LayoutTest.MACROS]
        d = tempfile.mkdtemp(prefix="plan_stable.")
        self._emit(d, self._dump(names))
        before = {n: open(os.path.join(d, n + "_pins.tcl")).read() for n in names[:2]}
        self._emit(d, self._dump(names), previous=d)
        for n in names[:2]:
            self.assertEqual(open(os.path.join(d, n + "_pins.tcl")).read(), before[n])

    def test_new_pins_take_free_tracks_and_the_rest_stay(self):
        names = [m["name"] for m in LayoutTest.MACROS]
        d = tempfile.mkdtemp(prefix="plan_stable.")
        self._emit(d, self._dump(names))
        old_a, old_b = self._rows(d, names[0]), self._rows(d, names[1])
        b_text = open(os.path.join(d, names[1] + "_pins.tcl")).read()
        self._emit(d, self._dump(names, extra=12), previous=d)
        new_a = self._rows(d, names[0])
        # every pin a had keeps its row; the other block is untouched
        for pin, row in old_a.items():
            self.assertEqual(new_a[pin], row)
        self.assertEqual(open(os.path.join(d, names[1] + "_pins.tcl")).read(), b_text)
        self.assertEqual(self._rows(d, names[1]), old_b)
        # the new pins are placed, on their layer's tracks, two tracks
        # from any other pin on their edge
        added = [r.split() for p, r in new_a.items() if p.startswith("n")]
        self.assertEqual(len(added), 12)
        pitch = {
            l["name"]: (l["pitch"], l["offset"])
            for l in ExactPinTest.LAYERS["pin_layers_v"]
            + ExactPinTest.LAYERS["pin_layers_h"]
        }
        rows = [r.split() for r in new_a.values()]
        for pin, layer, x, y, w, h in added:
            step, off = pitch[layer]
            slide = float(x) if float(h) > float(w) else float(y)
            self.assertAlmostEqual((slide - off) / step, round((slide - off) / step), 4)
            for q in rows:
                if q[0] == pin or q[1] != layer:
                    continue
                same_edge = (q[3] == y) if float(h) > float(w) else (q[2] == x)
                if same_edge:
                    other = float(q[2]) if float(h) > float(w) else float(q[3])
                    self.assertGreaterEqual(abs(other - slide), 2 * step - 1e-6)

    def test_gone_pins_are_dropped(self):
        names = [m["name"] for m in LayoutTest.MACROS]
        d = tempfile.mkdtemp(prefix="plan_stable.")
        self._emit(d, self._dump(names, extra=12))
        self._emit(d, self._dump(names), previous=d)
        self.assertFalse(any(p.startswith("n") for p in self._rows(d, names[0])))

    def test_a_full_edge_stops(self):
        rows = ["  p0 M3 5.0090 49.8200 0.0180 0.3600"]
        prev = {"p0": rows[0]}
        fresh = rows + ["  q0 M3 5.0090 49.8200 0.0180 0.3600"]
        with self.assertRaises(SystemExit):
            # an edge one pitch long: no free track for q0
            plan_floorplan.stable_rows(
                "a",
                fresh,
                prev,
                dict(TECH, **ExactPinTest.LAYERS),
                plan_floorplan.SEGMENT_EDGE_UM * 2 + 0.01,
                50.0,
            )


class KeepTest(unittest.TestCase):
    """--keep: a plan emitted before stays as it was, its die, its blocks
    and every pins file byte for byte, and only the parent's netlists move
    or change size (a register file generate_ram built at another size),
    each at its own corner and checked against the kept floorplan."""

    def _plan(self):
        macros = [dict(m) for m in LayoutTest.MACROS]
        for m in macros:
            m["content_um2"] = 0.45 * m["area_um2"]
            m["keep"] = ["%sInner" % m["name"]]
        p = plan(macros)
        p["tech"] = dict(LATTICE, **ExactPinTest.LAYERS)
        p["margins"] = dict(MARGINS, block_density=0.6)
        p["parent"]["keep"] = ["Backend"]
        return p

    def _emit(self):
        p = self._plan()
        out = plan_floorplan.layout(p)
        x0, y0, x1, y1 = out["region_um"]
        p["netlists"] = [
            {
                "module": "A",
                "instance": "top/a",
                "w_um": 100.0,
                "h_um": 80.0,
                "x_um": round(x0 + 20.0, 3),
                "y_um": round(y0 + 20.0, 3),
            },
            {
                "module": "B",
                "instance": "top/b",
                "w_um": 60.0,
                "h_um": 60.0,
                "x_um": round(x0 + 200.0, 3),
                "y_um": round(y0 + 20.0, 3),
            },
        ]
        d = tempfile.mkdtemp(prefix="plan_keep.")
        a, b = out["macros"][0]["name"], out["macros"][1]["name"]
        dump = os.path.join(d, "partners.txt")
        with open(dump, "w") as f:
            f.write("".join("pin %s a%d logic\n" % (a, i) for i in range(40)))
            f.write("".join("pin %s x%d %s\n" % (a, i, b) for i in range(10)))
            f.write("".join("pin %s x%d %s\n" % (b, i, a) for i in range(10)))
        p["pin_partners"] = dump
        plan_floorplan.emit(out, p, d)
        return p, out, d

    def _files(self, d):
        return {
            f: open(os.path.join(d, f)).read()
            for f in os.listdir(d)
            if f.endswith((".tcl", ".bzl"))
        }

    def _plan_bzl(self, d):
        scope = {}
        exec(open(os.path.join(d, "plan.bzl")).read(), scope)
        return scope["PLAN"]

    def test_netlists_change_and_the_rest_is_kept(self):
        p, out, d = self._emit()
        before = self._files(d)
        self.assertTrue(any(f.endswith("_mock_pins.tcl") for f in before))
        p["netlists"][0].update(w_um=120.0, h_um=150.0)
        kept = plan_floorplan.kept_layout(p, d)
        self.assertEqual(plan_floorplan.check(kept), [])
        e = tempfile.mkdtemp(prefix="plan_kept.")
        plan_floorplan.emit_kept(kept, p, e)
        after = self._files(e)
        self.assertEqual(sorted(after), sorted(before))
        for f in before:
            if f.endswith("_pins.tcl"):
                self.assertEqual(after[f], before[f], f)
        old, new = self._plan_bzl(d), self._plan_bzl(e)
        self.assertEqual(new["parent"]["netlists"][0]["h_um"], 150.0)
        self.assertEqual(new["parent"]["netlists"][1], old["parent"]["netlists"][1])
        old["parent"].pop("netlists")
        new["parent"].pop("netlists")
        self.assertEqual(new, old)
        # the blocks and their bands where they were, the netlist resized
        for m in out["macros"]:
            self.assertIn(plan_floorplan.macro_row(m) + "\n", after["place_macros.tcl"])
        for band in plan_floorplan.block_bands(out):
            self.assertIn(band + "\n", after["place_macros.tcl"])
        self.assertIn(
            "  top/a %.3f %.3f 120.000 150.000\n"
            % (p["netlists"][0]["x_um"], p["netlists"][0]["y_um"]),
            after["place_macros.tcl"],
        )

    def test_in_place_and_idempotent(self):
        p, out, d = self._emit()
        p["netlists"][1].update(w_um=70.0)
        path = os.path.join(d, "plan.json")
        with open(path, "w") as f:
            json.dump(p, f)
        pins = {f: t for f, t in self._files(d).items() if f.endswith("_pins.tcl")}
        argv = ["plan_floorplan.py", path, "--keep", d, "--emit", d]
        self.assertEqual(plan_floorplan.main(argv), 0)
        once = self._files(d)
        self.assertEqual(plan_floorplan.main(argv), 0)
        self.assertEqual(self._files(d), once)
        for f, t in pins.items():
            self.assertEqual(once[f], t)
        self.assertEqual(self._plan_bzl(d)["parent"]["netlists"][1]["w_um"], 70.0)

    def test_refuses_what_the_kept_floorplan_cannot_hold(self):
        p, out, d = self._emit()
        a = p["netlists"][0]
        block = out["macros"][0]
        for change, why in [
            (
                {"x_um": p["netlists"][1]["x_um"] - 50.0},
                "B at .* gap of register file A",
            ),
            ({"x_um": block["x_um"], "y_um": block["y_um"]}, "gap of block "),
            ({"x_um": out["die_um"][2] - 50.0}, "not inside the core"),
        ]:
            q = json.loads(json.dumps(p))
            q["netlists"][0].update(change)
            with self.assertRaisesRegex(SystemExit, why):
                plan_floorplan.kept_layout(q, d)
        # no corner of its own: the kept files record no region
        q = json.loads(json.dumps(p))
        q["netlists"][0].pop("x_um")
        q["netlists"][0]["owner_um"] = [a["x_um"], a["y_um"]]
        with self.assertRaisesRegex(SystemExit, "its own x_um and y_um"):
            plan_floorplan.kept_layout(q, d)
        # a keep list or a block that is not the kept plan's
        q = json.loads(json.dumps(p))
        q["macros"][0]["keep"] = ["Other"]
        with self.assertRaisesRegex(SystemExit, "keep list is not the plan's"):
            plan_floorplan.kept_layout(q, d)
        q = json.loads(json.dumps(p))
        q["macros"].pop()
        with self.assertRaisesRegex(SystemExit, "plans the blocks"):
            plan_floorplan.kept_layout(q, d)


def _edge_rows(names, pitch=0.144, y=0.18, start=5.0):
    """A bottom edge's rows, one pin per slot, M3/M5 alternating."""
    rows = []
    for i, n in enumerate(names):
        layer, w = ("M3", 0.018) if i % 2 == 0 else ("M5", 0.024)
        rows.append(
            "  %s %s %.4f %.4f %.4f 0.3600" % (n, layer, start + i * pitch, y, w)
        )
    return rows


def _slot_order(rows):
    """{side: [pin names by position]} and the set of slots."""
    by = {}
    for r in rows:
        side, pos = plan_floorplan._row_side(r)
        by.setdefault(side, []).append((pos, r.split()[0]))
    slots = sorted(tuple(r.split()[1:]) for r in rows)
    return {s: [n for _, n in sorted(v)] for s, v in by.items()}, slots


class PinOrderTest(unittest.TestCase):
    """pin_order: pins the probe placed for the wrong partner move along
    their side to the end facing the right one, trading slots with the
    rest, so no pin leaves its side or its track and every other pin keeps
    its order (XSTile's load write-back, MemBlock to Vec and Flt)."""

    NAMES = ["a0", "a1", "g0", "a2", "a3", "g1", "a4", "clock", "a5", "a6"]

    def _order(self, anchor_x, fixed=()):
        rows = _edge_rows(self.NAMES)
        order, report = plan_floorplan.order_pins(
            rows, [("^g", (anchor_x, 0.0))], (100.0, 0.0), fixed, "blk"
        )
        new = plan_floorplan.reordered_rows(rows, order, "blk")
        return rows, new, report

    def test_the_group_takes_the_end_facing_the_anchor(self):
        rows, new, report = self._order(-1000.0)
        order, slots = _slot_order(new)
        self.assertEqual(order["bottom"][:2], ["g0", "g1"])
        # everyone else in the order they had
        self.assertEqual(
            [n for n in order["bottom"] if not n.startswith("g")],
            [n for n in self.NAMES if not n.startswith("g")],
        )
        # the same slots: tracks, layers and sizes, only the names moved
        self.assertEqual(slots, _slot_order(rows)[1])
        self.assertIn("2 pins /^g/ to bottom", report[0])
        _, new, _ = self._order(1e6)
        self.assertEqual(_slot_order(new)[0]["bottom"][-2:], ["g0", "g1"])

    def test_an_anchor_along_the_side_takes_the_run_nearest_it(self):
        # slot 6 of the edge sits at 100 + 5 + 6 * 0.144 in the parent
        _, new, _ = self._order(100.0 + 5.0 + 6.5 * 0.144)
        order = _slot_order(new)[0]["bottom"]
        self.assertEqual(order[6:8], ["g0", "g1"])

    def test_fixed_pins_keep_their_slots(self):
        rows, new, _ = self._order(1e6, fixed=("clock",))
        self.assertIn(rows[self.NAMES.index("clock")], new)
        self.assertEqual(_slot_order(new)[0]["bottom"][-2:], ["g0", "g1"])

    def test_in_place_is_a_no_op(self):
        rows, new, _ = self._order(-1000.0)
        order, _ = plan_floorplan.order_pins(
            new, [("^g", (-1000.0, 0.0))], (100.0, 0.0), (), "blk"
        )
        self.assertEqual(plan_floorplan.reordered_rows(new, order, "blk"), new)

    def test_a_stale_order_stops(self):
        rows = _edge_rows(self.NAMES)
        with self.assertRaisesRegex(SystemExit, "names no pin"):
            plan_floorplan.order_pins(rows, [("^renamed", (0.0, 0.0))], (0.0, 0.0))

    def test_the_outline_gets_the_footprints_order(self):
        rows, new, _ = self._order(-1000.0)
        order = _slot_order(new)[0]
        # the outline's own file: the same pins, slots further apart
        outline = _edge_rows(self.NAMES, pitch=0.192)
        moved = plan_floorplan.reordered_rows(outline, order, "blk")
        self.assertEqual(_slot_order(moved)[0], order)
        with self.assertRaisesRegex(SystemExit, "differ between"):
            plan_floorplan.reordered_rows(outline[:-1], order, "blk")


class PinOrderPlanTest(unittest.TestCase):
    """pin_order in a plan, fresh and kept: the kept plan's pins files
    change in their pin names only, the rest of the plan not at all, and a
    second run changes nothing."""

    _plan = KeepTest._plan
    _emit = KeepTest._emit
    _files = KeepTest._files

    # a's pins to its logic, a10 to a29, the middle of their segment
    GROUP = "^a[12][0-9]$"

    def _with_order(self, p, out, partner_pins=False):
        a, b = out["macros"][0]["name"], out["macros"][1]["name"]
        q = json.loads(json.dumps(p))
        for m in q["macros"]:
            if m["name"] == a:
                m["pin_order"] = [{"pins": self.GROUP, "toward": b}]
                if partner_pins:
                    m["pin_order"][0]["partner_pins"] = "^x"
            if m["name"] == b and partner_pins:
                m["pin_order"] = [{"pins": "^x", "toward": a, "partner_pins": "^a"}]
        return q, a, b

    def _check_group(self, d, out, a, b, anchor=None):
        """a's group in one run, the run nearest the anchor (b's centre by
        default) among every run of its length."""
        by = {m["name"]: m for m in out["macros"]}
        m, q = by[a], by[b]
        rows = [
            l
            for l in open(os.path.join(d, a + "_mock_pins.tcl")).read().split("\n")
            if plan_floorplan.PIN_ROW.match(l)
        ]
        order, _ = _slot_order(rows)
        group = re.compile(self.GROUP)
        (side,) = [s for s, v in order.items() if any(group.search(n) for n in v)]
        along = 0 if side in ("bottom", "top") else 1
        if anchor is None:
            anchor = (q["x_um"] + q["w_um"] / 2.0, q["y_um"] + q["h_um"] / 2.0)
        pos = sorted(
            plan_floorplan._row_side(r)[1] + (m["x_um"], m["y_um"])[along]
            for r in rows
            if plan_floorplan._row_side(r)[0] == side
        )
        names = order[side]
        at = [i for i, n in enumerate(names) if group.search(n)]
        self.assertEqual(at, list(range(at[0], at[0] + len(at))))
        k = len(at)

        def miss(i):
            return abs((pos[i] + pos[i + k - 1]) / 2.0 - anchor[along])

        self.assertEqual(
            min(range(len(pos) - k + 1), key=lambda i: (miss(i), i)), at[0]
        )
        return order

    def test_kept_plan_moves_names_only_and_twice_is_once(self):
        p, out, d = self._emit()
        before = self._files(d)
        q, a, b = self._with_order(p, out)
        path = os.path.join(d, "plan.json")
        with open(path, "w") as f:
            json.dump(q, f)
        argv = ["plan_floorplan.py", path, "--keep", d, "--emit", d]
        self.assertEqual(plan_floorplan.main(argv), 0)
        once = self._files(d)
        changed = sorted(f for f in before if once[f] != before[f])
        self.assertEqual(changed, sorted([a + "_pins.tcl", a + "_mock_pins.tcl"]))
        for f in changed:
            old, new = before[f].split("\n"), once[f].split("\n")
            self.assertEqual(len(old), len(new))
            for lo, ln in zip(old, new):
                if lo != ln:
                    # a row whose slot text stayed and whose pin changed
                    self.assertTrue(plan_floorplan.PIN_ROW.match(lo), lo)
                    self.assertEqual(lo.split()[1:], ln.split()[1:])
            self.assertEqual(
                sorted(l.split()[0] for l in old if plan_floorplan.PIN_ROW.match(l)),
                sorted(l.split()[0] for l in new if plan_floorplan.PIN_ROW.match(l)),
            )
        order = self._check_group(d, out, a, b)
        rows_own = [
            l
            for l in once[a + "_pins.tcl"].split("\n")
            if plan_floorplan.PIN_ROW.match(l)
        ]
        self.assertEqual(_slot_order(rows_own)[0], order)
        self.assertEqual(plan_floorplan.main(argv), 0)
        self.assertEqual(self._files(d), once)

    def test_fresh_plan_agrees_with_the_kept_one(self):
        p, out, d = self._emit()
        q, a, b = self._with_order(p, out)
        e = tempfile.mkdtemp(prefix="plan_order.")
        plan_floorplan.emit(out, q, e)
        self._check_group(e, out, a, b)
        fresh = self._files(e)
        kept = plan_floorplan.kept_layout(q, e)
        plan_floorplan.emit_kept(kept, q, e)
        for f, t in self._files(e).items():
            if f.endswith("_pins.tcl"):
                self.assertEqual(t, fresh[f], f)

    def test_partner_pins_face_where_the_partner_put_them(self):
        p, out, d = self._emit()
        q, a, b = self._with_order(p, out, partner_pins=True)
        # a's anchor reads b's x pins, b's reads a's: a circle
        with self.assertRaisesRegex(SystemExit, "circle"):
            plan_floorplan.emit_kept(plan_floorplan.kept_layout(q, d), q, d)
        for m in q["macros"]:
            if m["name"] == b:
                m.pop("pin_order")
        out_k = plan_floorplan.kept_layout(q, d)
        plan_floorplan.emit_kept(out_k, q, d)
        by = {m["name"]: m for m in out_k["macros"]}
        pts = [
            (by[b]["x_um"] + float(r.split()[2]), by[b]["y_um"] + float(r.split()[3]))
            for r in open(os.path.join(d, b + "_mock_pins.tcl")).read().split("\n")
            if plan_floorplan.PIN_ROW.match(r) and r.split()[0].startswith("x")
        ]
        mean = (
            sum(x for x, _ in pts) / len(pts),
            sum(y for _, y in pts) / len(pts),
        )
        self._check_group(d, out_k, a, b, anchor=mean)

    def test_toward_a_block_the_plan_does_not_have_stops(self):
        p, out, d = self._emit()
        q, a, b = self._with_order(p, out)
        for m in q["macros"]:
            if m["name"] == a:
                m["pin_order"][0]["toward"] = "Elsewhere"
        with self.assertRaisesRegex(SystemExit, "not another planned block"):
            plan_floorplan.emit_kept(plan_floorplan.kept_layout(q, d), q, d)


if __name__ == "__main__":
    unittest.main()
