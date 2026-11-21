"""Rungs 0 and 1 (ladder.py) on hand numbers and the toy's frozen
extracts."""

import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ladder as L  # noqa: E402

TOY = os.path.join(HERE, "testdata", "toy")


def load(name):
    with open(os.path.join(TOY, name)) as f:
        return json.load(f)


def block(insts=10000, nets=11000, pins=30000, w=100.0, h=100.0, ports=200, hard=()):
    return {
        "block": "B",
        "area": {
            "hard_um2": sum(o["w"] * o["h"] for o in hard),
            "die_rule": {"core_w_um": w, "core_h_um": h, "w_um": w, "h_um": h},
        },
        "netlist": {"insts": insts, "seq": 0, "nets": nets, "pins": pins},
        "ports": [{"name": "a", "bits": ports}],
        "hard": list(hard),
    }


class Donath(unittest.TestCase):
    def test_grows_with_size_above_a_half(self):
        self.assertLess(L.donath_length(0.6, 1e4), L.donath_length(0.6, 1e6))

    def test_continuous_through_a_half(self):
        self.assertAlmostEqual(
            L.donath_length(0.5, 1e5), L.donath_length(0.5001, 1e5), delta=0.05
        )

    def test_known_magnitude(self):
        # p 0.6, a million gates: about 13 gate pitches
        self.assertAlmostEqual(L.donath_length(0.6, 1e6), 13.2, delta=0.3)


class Rung0(unittest.TestCase):
    def test_supply_less_obstructed_layers(self):
        mem = {"w": 50.0, "h": 50.0, "obs": ["M2", "M3"]}
        b = block(hard=[mem])
        lt = {"M2": 10.0, "M3": 10.0, "M4": 10.0}
        s = L.wire_supply_um(b, 100.0, 100.0, lt)
        self.assertAlmostEqual(s, 10 * 7500 * 2 + 10 * 10000)

    def test_wire_ratio_falls_with_the_outline(self):
        lt = {"M2": 10.0}
        small = L.wire_demand(block(w=100, h=100), lt, 0.6)
        big = L.wire_demand(block(w=200, h=200), lt, 0.6)
        self.assertAlmostEqual(small["ratio"] / big["ratio"], 2.0, places=2)

    def test_feedthrough_is_a_crossing_not_logic(self):
        lt = {"M2": 10.0}
        nl = {"feedthrough": {"bits": 100, "cells": 0, "connections": 100}}
        a = L.wire_demand(block(), lt, 0.6)
        b = L.wire_demand(block(), lt, 0.6, netlist=nl)
        self.assertEqual(b["connections"], a["connections"] - 100)
        r = L.rent_terminals(block(ports=300), 0.6, 2.5, nl)
        self.assertEqual(r["pins"], 100)

    def test_rent_terminals(self):
        r = L.rent_terminals(block(insts=10000, ports=500), 0.5, 2.0)
        self.assertAlmostEqual(r["predicted"], 200.0)
        self.assertAlmostEqual(r["ratio"], 2.5)

    def test_grt_capacity(self):
        g = L.grt_capacity(block(insts=1000), 1.25, 1000)
        self.assertEqual((g["grt_insts"], g["ratio"]), (1250, 1.25))
        self.assertNotIn("ratio", L.grt_capacity(block(), None, None))

    def test_logic_bound(self):
        b = block()
        b["clock"] = {"period_ps": 1000.0}
        b["logic"] = {"ps": 1200.0, "cells": 40, "from": "r0", "to": "r1"}
        self.assertEqual(L.logic_bound(b)["over_period"], 1.2)


class Rung1(unittest.TestCase):
    def setUp(self):
        self.pdk = load("asap7.pdk.json")

    def test_escape_counts_cone_breadth(self):
        nl = {"buses": {"a": {"breadth_mean": 4.0}}}
        e = L.escape(
            "N", 10.0, [("a", 100), ("b", 50)], nl, self.pdk, {"M3": 10.0, "M2": 10.0}
        )
        self.assertEqual(e["demand"], 450.0)
        # only the vertical layer crosses a north side
        self.assertEqual(e["supply"], 100.0)

    def test_layers_by_distance(self):
        per, rows = L.assign_layers(
            [
                ("near", 10, 20.0, True),
                ("far", 20, 5000.0, True),
                ("beside", 5, 1.0, False),
            ],
            ["M3", "M5"],
            self.pdk,
        )
        self.assertEqual(per, {"M3": 10, "M5": 25})

    def test_via_stacks_load_the_layers_below(self):
        vs = L.via_stack(10.0, {"M3": 10, "M5": 20}, self.pdk, 1.0)
        self.assertEqual((vs["M3"]["pins"], vs["M3"]["stacks"]), (10, 20))
        self.assertEqual((vs["M4"]["pins"], vs["M4"]["stacks"]), (0, 20))
        self.assertEqual(vs["M5"]["stacks"], 0)
        self.assertAlmostEqual(vs["M3"]["track_spacing"], 10.0 * 27.7778 / 30, places=2)
        self.assertNotIn("demand", L.via_stack(10.0, {"M3": 10}, self.pdk, None)["M3"])

    def test_fanout_against_budget(self):
        nl = {"fanout": [{"net": "n", "sinks": 100, "driver": "register"}]}
        self.assertEqual(L.fanout(nl, 10.0, 500.0)[0]["chain_ps"], 1000.0)
        self.assertEqual(L.fanout(nl, 1.0, 500.0), [])

    def test_min_outline(self):
        self.assertEqual(L.min_outline(10.0, 10.0, 400.0, {}), [20.0, 20.0])
        w, h = L.min_outline(10.0, 10.0, 100.0, {"N": 25.0})
        self.assertEqual(w, 25.0)
        self.assertTrue(math.isclose(w * h, 100.0))


class Toy(unittest.TestCase):
    def test_extracts_carry_the_ladders_inputs(self):
        for b in ("FpCore", "FpMem", "FpVec"):
            self.assertGreater(load(b + ".block.json")["netlist"]["insts"], 100)
            self.assertIsNotNone(load(b + ".netlist.json")["rent"]["p"])
        self.assertEqual(load("FpVec.netlist.json")["feedthrough"]["bits"], 16)


if __name__ == "__main__":
    unittest.main()
