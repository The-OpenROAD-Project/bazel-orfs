"""The toy's extracts say what toy.sv is, and asap7's wire model agrees
with test/macro_select's calibration within its 50 % error bars."""

import json
import sys
import unittest

FILES = {}


def load(suffix):
    (path,) = [p for p in FILES if p.endswith(suffix)]
    with open(path) as f:
        return json.load(f)


class ExtractTest(unittest.TestCase):
    def ports(self, block):
        return {p["name"]: p for p in load(block + ".block.json")["ports"]}

    def test_over_wide_bus(self):
        p = self.ports("FpVec")["wide"]
        self.assertEqual((p["dir"], p["bits"]), ("in", 1024))
        self.assertEqual(self.ports("FpCore")["wide"]["bits"], 1024)

    def test_feedthrough(self):
        (ft,) = self.ports("FpCore")["ft_in"]["in2out"]
        self.assertEqual((ft["to"], ft["bits"]), ("ft_out", 16))

    def test_cross_macro_path_ends(self):
        self.assertGreater(self.ports("FpCore")["deep_out"]["reg2out_ps"]["max"], 150)
        self.assertGreater(self.ports("FpVec")["deep_in"]["in2reg_ps"]["max"], 150)

    def test_memories(self):
        b = load("FpMem.block.json")
        self.assertEqual(
            [m["master"] for m in b["area"]["macros"]], ["fakeram7_256x34"]
        )
        self.assertEqual(len(b["hard"]), 4)
        for h in b["hard"]:
            self.assertEqual(h["pins"]["rd_out"]["side"], "W")
            nets = {(n["pin"], n["port"], n["via"]) for n in h["nets"]}
            self.assertIn(("rd_out", "resp", "reg"), nets)
            self.assertIn(("addr_in", "req", "reg"), nets)
        self.assertGreater(b["area"]["hard_um2"], 10 * b["area"]["std_um2"])

    def test_die_rule(self):
        r = load("FpCore.block.json")["area"]["die_rule"]
        self.assertEqual(r["rule"], "CORE_UTILIZATION")
        self.assertAlmostEqual(r["util"], 0.4)
        self.assertAlmostEqual(
            load("FpMem.block.json")["area"]["die_rule"]["util"], 0.7
        )

    def test_parent_crossings(self):
        x = {
            (c["a"], c["a_bus"], c["b"], c["b_bus"]): c
            for c in load("fp_top_parent.parent.json")["crossings"]
        }
        self.assertEqual(x[("FpCore", "wide", "FpVec", "wide")]["bits"], 1024)
        self.assertEqual(x[("FpCore", "wide", "FpVec", "wide")]["via"], "wire")
        # through the glue's register: two crossings, each to the glue
        self.assertEqual(x[("FpMem", "resp", "fp_top", "")]["via"], "reg")
        self.assertEqual(x[("fp_top", "", "FpCore", "resp")]["via"], "reg")
        deep = x[("FpCore", "deep_out", "FpVec", "deep_in")]
        self.assertEqual(
            (deep["via"], deep["a_bits"], deep["b_bits"]), ("comb", 32, 32)
        )
        self.assertGreater(deep["glue_ps"], 50)
        self.assertIn(("fp_top", "in_top", "FpCore", "in_top"), x)

    def test_wire_model_against_calibration(self):
        # test/macro_select's measured facts, the 50 % error bars
        cal = load("floorplan_calibration.json")
        pdk = load("asap7.pdk.json")
        lowest = min(cal["facing_pin_wall"]["layers"], key=pdk["order"].index)
        self.assertIn("tracks_per_um", pdk["layers"][lowest])
        ps = cal["wire_ps_per_um"]["value"]
        for name in pdk["io"]["H"] + pdk["io"]["V"]:
            self.assertAlmostEqual(pdk["layers"][name]["ps_per_um"], ps, delta=0.5 * ps)
        # upper layers are faster
        self.assertLess(
            pdk["layers"]["M7"]["ps_per_um"], pdk["layers"]["M2"]["ps_per_um"]
        )


if __name__ == "__main__":
    FILES = sys.argv[1:]
    unittest.main(argv=sys.argv[:1])
