import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import block_json  # noqa: E402

DUMP = """block\tB
var\tCORE_UTILIZATION\t40
var\tCORE_MARGIN\t1
site\t0.054\t0.27
area\t1000.0
clock\tclock\t1000.0
port\ta[0]\tinput
port\ta[1]\tinput
port\tq[0]\toutput
port\tft_in[0]\tinput
port\tft_out[0]\toutput
in2reg\ta\t10.0\ta[1]
reg2out\tq\t30.0\tq[0]
in2out\tft_in\tft_out\t50.0\t1
hard\tm0\tram\t10.0\t40.0\tmemory
hpin\tm0\trd_out\tW\t0.0\t17.5\t34\tM4
hnet\tm0\trd_out\tq\t1\treg\t2
""".splitlines()


class BlockJsonTest(unittest.TestCase):
    def setUp(self):
        self.b = block_json.build(block_json.parse(DUMP), "0", 25.0, 70.0, 2.0)
        self.ports = {p["name"]: p for p in self.b["ports"]}

    def test_buses_and_widths(self):
        self.assertEqual(self.ports["a"]["bits"], 2)
        self.assertEqual(self.ports["a"]["dir"], "in")
        self.assertEqual(self.ports["a"]["in2reg_ps"], {"max": 10.0, "bit": "a[1]"})

    def test_registered(self):
        self.assertTrue(self.ports["a"]["registered"])
        self.assertTrue(self.ports["q"]["registered"])
        self.assertFalse(self.ports["ft_in"]["registered"])
        self.assertFalse(self.ports["ft_out"]["registered"])

    def test_die_rule_is_the_flows_outline(self):
        # (1000 + 400) / 0.4 = 3500 um2, a 59.16 um square snapped to sites
        # and rows, plus 1 um margin per side
        r = self.b["area"]["die_rule"]
        self.assertAlmostEqual(r["core_w_um"], 59.184, places=3)
        self.assertAlmostEqual(r["core_h_um"], 59.4, places=3)
        self.assertAlmostEqual(r["w_um"], 61.184, places=3)

    def test_die_area_wins(self):
        r = block_json.die_rule({"DIE_AREA": "0 0 100 50"}, 0, 0, [1, 1])
        self.assertEqual((r["w_um"], r["h_um"]), (100.0, 50.0))

    def test_hard_objects(self):
        (m,) = self.b["hard"]
        self.assertEqual(m["pins"]["rd_out"]["side"], "W")
        self.assertEqual(m["nets"][0]["port"], "q")
        self.assertEqual(
            self.b["area"]["macros"], [{"master": "ram", "w": 10.0, "h": 40.0, "n": 1}]
        )

    def test_group_strips_index_suffix(self):
        self.assertEqual(block_json.group_of("io_in_3"), "io_in")


if __name__ == "__main__":
    unittest.main()
