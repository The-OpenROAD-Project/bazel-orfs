"""calibrate.py on synthetic points whose answer is known."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calibrate as C  # noqa: E402

with open(os.path.join(HERE, "testdata", "toy", "asap7.pdk.json")) as f:
    PDK = json.load(f)


def block(name, insts, side_um):
    return {
        "block": name,
        "area": {
            "hard_um2": 0.0,
            "die_rule": {
                "core_w_um": side_um,
                "core_h_um": side_um,
                "w_um": side_um,
                "h_um": side_um,
            },
        },
        "netlist": {"insts": insts, "seq": 0, "nets": insts, "pins": 3 * insts},
        "ports": [{"name": "a", "bits": 100}],
        "hard": [],
        "logic": {"ps": 900.0, "cells": 30, "from": "r0", "to": "r1"},
    }


def netlist(name, p):
    return {
        "block": name,
        "rent": {"p": p, "k": 3.0},
        "buses": {"a": {"bits": 100, "breadth_mean": 2.0}},
        "feedthrough": {"bits": 0, "cells": 0, "connections": 0},
    }


class Calibrate(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # the same logic in ever smaller outlines: the wire ratio rises, and
        # the two smallest overflow
        pts = []
        for i, (side, ovf) in enumerate(
            ((400.0, 0), (300.0, 0), (150.0, 500), (100.0, 9000))
        ):
            n = "b%d" % i
            for suffix, obj in (
                (".block.json", block(n, 200000, side)),
                (".netlist.json", netlist(n, 0.6)),
            ):
                with open(os.path.join(self.dir, n + suffix), "w") as f:
                    json.dump(obj, f)
            pts.append(
                {
                    "name": n,
                    "block": n + ".block.json",
                    "netlist": n + ".netlist.json",
                    "sides": {"N": 2000},
                    "measured": {
                        "overflow": ovf,
                        "wirelength_um": 2e6,
                        "grt_insts": 240000,
                        "grt_peak_gib": 4.0,
                        "period_ps": 1000.0,
                    },
                }
            )
        self.spec = {"design": "synthetic", "pdk": PDK, "worker_gib": 64, "points": pts}

    def test_limits_separate_clean_from_failing(self):
        cal, report, _ = C.calibrate(self.spec, self.dir)
        rows = {r["name"]: r for r in report["points"]}
        lim = cal["wire_demand"]["limit"]
        self.assertLess(rows["b1"]["wire_ratio"], lim)
        self.assertGreater(rows["b2"]["wire_ratio"], lim)
        # the two clean points tie on the overflow
        self.assertGreater(report["stats"]["wire_ratio"]["tau_b"], 0.9)
        self.assertGreater(report["stats"]["spacing_min"]["tau_b"], 0.9)
        self.assertIn("facing_track_spacing", cal["pins_per_um"])

    def test_factor_scales_to_measured_wire(self):
        cal, report, _ = C.calibrate(self.spec, self.dir)
        f = cal["wire_demand"]["wirelength_factor"]
        ratios = sorted(2e6 / r["wire_um_donath"] for r in report["points"])
        self.assertAlmostEqual(f, (ratios[1] + ratios[2]) / 2, places=3)

    def test_grt_capacity_from_memory(self):
        cal, _, _ = C.calibrate(self.spec, self.dir)
        g = cal["grt_capacity"]
        self.assertEqual(g["grt_per_synth_inst"], 1.2)
        # bytes per instance are reported to a tenth of a byte
        self.assertAlmostEqual(g["max_insts"], 64 * 240000 // 4, delta=2)

    def test_rent_is_unjudged_without_separation(self):
        _, report, _ = C.calibrate(self.spec, self.dir)
        # every block has the same pins and size: no Rent ratio separates
        self.assertIn("rent_terminals", report["unjudged"])

    def test_logic_bound(self):
        _, report, _ = C.calibrate(self.spec, self.dir)
        self.assertTrue(report["points"][0]["logic_bound"])

    def test_kendall(self):
        self.assertEqual(C.kendall_tau_b([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertIsNone(C.kendall_tau_b([1, 2], [1, 2]))


if __name__ == "__main__":
    unittest.main()
