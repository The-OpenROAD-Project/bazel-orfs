"""The planner on the toy's frozen extracts (testdata/toy, from
test/floorplan_toy): each seeded fault is the first stop with the right
block, side and bus; the clean cut is feasible. Plus the pieces."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plan  # noqa: E402

TOY = os.path.join(HERE, "testdata", "toy")


def load(name):
    with open(os.path.join(TOY, name)) as f:
        return json.load(f)


_PLANS = {}


def toy(variant, remedies=False):
    """The planner's result on a variant, planned once per test run."""
    if (variant, remedies) not in _PLANS:
        blocks = [load("%s.block.json" % b) for b in ("FpCore", "FpMem", "FpVec")]
        _PLANS[(variant, remedies)] = plan.run(
            blocks,
            load("parent.json"),
            load("asap7.pdk.json"),
            load("cut.json"),
            load("constraints_%s.json" % variant),
            calibration=load("calibration.json"),
            remedies=remedies,
            netlists=[
                load("%s.netlist.json" % b) for b in ("FpCore", "FpMem", "FpVec")
            ],
        )
    return _PLANS[(variant, remedies)]


def fails(v):
    return [f for f in v["findings"] if f["status"] == "fail"]


class SeededFaults(unittest.TestCase):
    def test_clean_is_feasible(self):
        _, _, v, fp = toy("clean")
        self.assertEqual(v["verdict"], "feasible", fails(v))
        self.assertEqual(sorted(fp["macros"]), ["FpCore", "FpMem", "FpVec"])

    def test_over_wide_bus_stops_at_pins(self):
        _, _, v, fp = toy("pins")
        self.assertEqual(v["stopped_at"], "pins_per_um")
        (f,) = fails(v)
        self.assertEqual((f["block"], f["bus"]), ("FpVec", "wide"))
        self.assertEqual(f["contributors"][0]["partner"], "FpCore")
        self.assertGreater(f["excess"]["factor"], 1.0)
        self.assertIn("reshape", f["remedies"])
        self.assertIsNone(fp)

    def test_slot_under_the_flows_outline_stops_at_area(self):
        _, _, v, _ = toy("area")
        self.assertEqual(v["stopped_at"], "area")
        (f,) = fails(v)
        self.assertEqual(f["block"], "FpMem")
        self.assertGreater(f["excess_um2"], 0)
        self.assertIn("CORE_UTILIZATION 70", f["need"]["rule"])
        self.assertIn("resize_slot", f["remedies"])

    def test_no_aspect_holds_the_memories(self):
        _, _, v, _ = toy("aspect")
        self.assertEqual(v["stopped_at"], "aspect")
        (f,) = fails(v)
        self.assertEqual(f["block"], "FpMem")
        self.assertIn("reshape", f["remedies"])

    def test_memories_wall_the_forced_side(self):
        _, _, v, _ = toy("wall")
        self.assertEqual(v["stopped_at"], "internal_arrangement")
        (f,) = fails(v)
        self.assertEqual(
            (f["kind"], f["block"], f["side"]), ("side_blocked", "FpMem", "W")
        )
        self.assertEqual(len(f["walls"]), 4)
        self.assertLess(f["free_fraction"], 0.5)
        self.assertEqual({b["bus"] for b in f["buses_needing"]}, {"req", "resp"})
        self.assertIn("change_side", f["remedies"])

    def test_starved_channel_stops_at_channels(self):
        _, _, v, _ = toy("channel")
        self.assertEqual(v["stopped_at"], "channel_capacity")
        f = fails(v)[0]
        self.assertEqual(
            (f["kind"], f["block"], f["bus"]), ("over_capacity", "FpMem", "wide")
        )
        self.assertIn("FpMem|", f["channel"])
        self.assertGreater(f["demand_tracks"], f["capacity_tracks"])
        # the starved top layers are counted at their share
        self.assertLess(
            f["capacity_per_layer"].get("M6", f["capacity_per_layer"].get("M7")), 5
        )
        self.assertIn("move_slot", f["remedies"])

    def test_far_ends_stop_at_the_path_budget(self):
        _, _, v, _ = toy("path")
        self.assertEqual(v["stopped_at"], "path_budget")
        (f,) = fails(v)
        self.assertEqual(f["chain"], "FpCore.deep_out -> FpVec.deep_in")
        self.assertEqual(
            (f["block"], f["bus"], f["layer_needed"], f["dominates"]),
            ("FpVec", "deep_in", "none closes", "wire"),
        )
        self.assertEqual([l["kind"] for l in f["legs"]], ["reg2out", "glue", "in2reg"])
        self.assertLess(f["max_distance_um"], f["route"]["length_um"])

    def test_clean_chains_close_on_the_lowest_pair(self):
        _, _, v, _ = toy("clean")
        for c in v["chains"]:
            self.assertEqual(c["status"], "ok")
            self.assertGreater(c["slack_ps"], 0)

    def test_rung_a_reports_track_spacing(self):
        _, _, v, _ = toy("pins")
        (f,) = fails(v)
        # tracks per pin on each pin layer, against the calibrated facing
        # spacing on the lowest one
        self.assertEqual(set(f["track_spacing"]), {"M2", "M4"})
        self.assertLess(f["track_spacing"]["M2"], f["limit"]["track_spacing"])
        self.assertIn("route-0", f["limit"]["source"])

    def test_a_partner_beside_a_side_is_reported_not_failed(self):
        _, _, v, _ = toy("clean")
        lateral = [f for f in v["findings"] if f.get("kind") == "lateral"]
        self.assertTrue(lateral)
        for f in lateral:
            self.assertEqual(f["status"], "uncalibrated")
            self.assertTrue(f["lateral_partners"])

    def test_no_calibration_measures_and_fails_nothing(self):
        blocks = [load("%s.block.json" % b) for b in ("FpCore", "FpMem", "FpVec")]
        _, _, v, fp = plan.run(
            blocks,
            load("parent.json"),
            load("asap7.pdk.json"),
            load("cut.json"),
            load("constraints_pins.json"),
            remedies=False,
        )
        self.assertEqual([f for f in v["findings"] if f["status"] == "fail"], [])
        self.assertEqual(
            v["unjudged"], sorted(k for k in plan.CALIBRATION_KEYS if k in plan.RUNGS)
        )
        self.assertIsNotNone(fp)


class Ladder(unittest.TestCase):
    def test_grid_taking_half_the_tracks_stops_at_wire_demand(self):
        _, _, v, fp = toy("wire", remedies=True)
        self.assertEqual(v["stopped_at"], "wire_demand")
        f = fails(v)[0]
        self.assertEqual(f["block"], "FpCore")
        self.assertGreater(f["excess"]["factor"], 1.0)
        self.assertEqual(f["best_remedy"]["kind"], "resize_slot")
        mo = v["ladder"]["macros"]["FpCore"]["min_outline"]
        self.assertEqual(mo["binding"], ["wire_demand"])
        self.assertGreater(mo["w"] * mo["h"], mo["now"][0] * mo["now"][1])
        self.assertIsNone(fp)

    def test_clean_reports_every_rung(self):
        _, _, v, _ = toy("clean")
        core = v["ladder"]["macros"]["FpCore"]
        for k in ("wire_demand", "rent_terminals", "rent_wire", "rent", "logic"):
            self.assertIsNotNone(core[k], k)
        self.assertEqual(max(core["partners"], key=core["partners"].get), "FpVec")
        side = v["ladder"]["sides"]["FpCore N"]
        self.assertIn("escape", side)
        self.assertTrue(side["via_stack"]["layers"])

    def test_rung_1_judged_once_calibrated(self):
        blocks = [load("%s.block.json" % b) for b in ("FpCore", "FpMem", "FpVec")]
        nls = [load("%s.netlist.json" % b) for b in ("FpCore", "FpMem", "FpVec")]
        cal = dict(load("calibration.json"))
        cal["via_stack"] = {"via_cost": 3.0, "source": "a test"}
        _, _, v, _ = plan.run(
            blocks,
            load("parent.json"),
            load("asap7.pdk.json"),
            load("cut.json"),
            load("constraints_clean.json"),
            calibration=cal,
            remedies=False,
            netlists=nls,
        )
        self.assertEqual(v["stopped_at"], "via_stack")
        self.assertTrue(fails(v)[0]["layer"])
        cal = dict(load("calibration.json"))
        cal["escape"] = {"limit": 0.5, "source": "a test"}
        _, _, v, _ = plan.run(
            blocks,
            load("parent.json"),
            load("asap7.pdk.json"),
            load("cut.json"),
            load("constraints_clean.json"),
            calibration=cal,
            remedies=False,
            netlists=nls,
        )
        self.assertEqual(v["stopped_at"], "escape")


class Floorplan(unittest.TestCase):
    def test_pins_are_whole_buses_inside_their_side(self):
        _, _, v, fp = toy("clean")
        for m, mac in fp["macros"].items():
            w, h = mac["shape"]
            seen = set()
            for side, pins in mac["pins"].items():
                for p in pins:
                    self.assertNotIn(p["bus"], seen, (m, p["bus"]))
                    seen.add(p["bus"])
                    lo, hi = p["range"]
                    self.assertLessEqual(0.0, lo)
                    self.assertLessEqual(hi, (w if side in "NS" else h) + 1e-6)
            die = fp["die"]
            x, y = mac["place"]
            self.assertTrue(
                0 <= x and x + w <= die[0] + 1e-6 and 0 <= y and y + h <= die[1] + 1e-6
            )

    def test_internal_placement_inside_the_outline(self):
        _, _, v, fp = toy("clean")
        w, h = fp["macros"]["FpMem"]["shape"]
        for o in v["internal_placement"]["FpMem"]:
            x, y = o["place"]
            ow, oh = o["shape"]
            self.assertTrue(0 <= x and x + ow <= w and 0 <= y and y + oh <= h)

    def test_main_writes_verdict_and_floorplan(self):
        with tempfile.TemporaryDirectory() as d:
            args = [
                "--pdk",
                os.path.join(TOY, "asap7.pdk.json"),
                "--cut",
                os.path.join(TOY, "cut.json"),
                "--parent",
                os.path.join(TOY, "parent.json"),
                "--constraints",
                os.path.join(TOY, "constraints_wall.json"),
                "--calibration",
                os.path.join(TOY, "calibration.json"),
                "--verdict",
                os.path.join(d, "v.json"),
                "--verdict-md",
                os.path.join(d, "v.md"),
                "--floorplan",
                os.path.join(d, "f.json"),
            ]
            for b in ("FpCore", "FpMem", "FpVec"):
                args += ["--block", os.path.join(TOY, "%s.block.json" % b)]
            self.assertEqual(plan.main(args), 0)
            with open(os.path.join(d, "v.json")) as f:
                self.assertEqual(json.load(f)["verdict"], "infeasible")
            with open(os.path.join(d, "f.json")) as f:
                self.assertEqual(json.load(f), {})
            with open(os.path.join(d, "v.md")) as f:
                self.assertIn("side_blocked", f.read())


class Pieces(unittest.TestCase):
    def test_pack_shelves_away_from_base(self):
        objs = [{"w": 10, "h": 40, "halo_um": 1}] * 3
        rects = plan.pack(objs, [0, 0, 100, 50], "S")
        self.assertEqual([r[0] for r in rects], [0, 12, 24])
        self.assertTrue(all(r[1] == 0 for r in rects))
        self.assertIsNone(plan.pack(objs, [0, 0, 30, 50], "S"))
        rects = plan.pack(objs, [0, 0, 100, 50], "N")
        self.assertTrue(all(r[1] == 10 for r in rects))

    def test_free_spans(self):
        free, walls = plan.free_spans(100, 50, "S", [[10, 0, 20, 30]], 5, 1)
        self.assertEqual(walls, [[9, 31]])
        self.assertEqual(free, [[0.0, 9], [31, 100]])
        free, walls = plan.free_spans(100, 50, "N", [[10, 0, 20, 30]], 5, 1)
        self.assertEqual(walls, [])

    def test_place_buses_keeps_each_bus_whole(self):
        segs = [("N", 0, 10, 100), ("E", 0, 10, 60)]
        buses = [
            {"bus": "a", "bits": 90},
            {"bus": "b", "bits": 50},
            {"bus": "c", "bits": 20},
        ]
        out = plan.place_buses(segs, buses)
        sides = {c["bus"]: s for s, _, _, g in out for c in g}
        self.assertEqual(sides, {"a": "N", "b": "E", "c": "N"})

    def test_identity_names_every_input(self):
        _, _, v, _ = toy("clean")
        self.assertEqual(
            set(v["identity"]),
            {
                "tool",
                "blocks",
                "netlists",
                "parent",
                "pdk",
                "cut",
                "constraints",
                "calibration",
            },
        )


if __name__ == "__main__":
    unittest.main()
