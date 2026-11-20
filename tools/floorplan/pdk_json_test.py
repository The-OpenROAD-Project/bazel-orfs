import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdk_json  # noqa: E402

DUMP = """platform\tasap7
site\t0.054\t0.27
io\tM4\tM5
range\tM2\tM5
layer\tM1\tV\t0.036\t0.018\t70\t0.0
via\tV1\t17.2
layer\tM2\tH\t0.036\t0.018\t30\t0.17
via\tV2\t17.2
layer\tM3\tV\t0.036\t0.018\t31\t0.16
via\tV3\t17.2
layer\tM4\tH\t0.048\t0.024\t18\t0.18
via\tV4\t11.8
layer\tM5\tV\t0.048\t0.024\t19\t0.16
wire\tM4\tBUFx2\t10.0\t20.0
wire\tM4\tBUFx2\t100.0\t40.0
wire\tM4\tBUFx12\t100.0\t30.0
wire\tM4\tBUFx12\t200.0\t70.0
wire\tM5\tBUFx12\t100.0\t35.0
""".splitlines()


class PdkJsonTest(unittest.TestCase):
    def setUp(self):
        self.pdk = pdk_json.build(pdk_json.parse(DUMP), "0")

    def test_repeater_minimises_delay_per_um(self):
        m4 = self.pdk["layers"]["M4"]
        self.assertEqual(m4["buffer"], "BUFx12")
        self.assertAlmostEqual(m4["ps_per_um"], 0.3)
        self.assertEqual(m4["spacing_um"], 100.0)
        self.assertEqual(m4["unrepeated"], [[100.0, 30.0], [200.0, 70.0]])

    def test_tracks_per_um(self):
        self.assertAlmostEqual(
            self.pdk["layers"]["M4"]["tracks_per_um"], 20.8333, places=3
        )
        self.assertNotIn("pins_per_um", self.pdk["layers"]["M4"])

    def test_via_stack_from_pin_layer(self):
        # M2 is two cuts (V2, V3) below the pin layer M4; M4 itself none
        self.assertEqual(self.pdk["layers"]["M4"]["via_ps"], 0.0)
        self.assertGreater(self.pdk["layers"]["M5"]["via_ps"], 0.0)
        self.assertEqual(pdk_json.cuts_above(pdk_json.parse(DUMP)["seq"])["M2"], "V2")

    def test_routable_range(self):
        layers = self.pdk["layers"]
        self.assertFalse(layers["M1"]["routable"])
        self.assertTrue(layers["M2"]["routable"])
        self.assertTrue(layers["M5"]["routable"])


if __name__ == "__main__":
    unittest.main()
