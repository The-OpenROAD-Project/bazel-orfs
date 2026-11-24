"""Unit tests for //pdk/asap7:inject_vt_obs."""

import unittest

import inject_vt_obs

_WITH_OBS = """\
MACRO AO21Bx1_ASAP7_75t_L
    CLASS CORE ;
    SIZE 0.378 BY 0.27 ;
    SYMMETRY X Y ;
    SITE asap7sc7p5t ;
    PIN Y
        DIRECTION OUTPUT ;
    END Y
    OBS
        LAYER M1 ;
            RECT 0.018 0.095 0.072 0.175 ;
    END
END AO21Bx1_ASAP7_75t_L
"""

_WITHOUT_OBS = """\
MACRO INVx12_ASAP7_75t_SL
    CLASS CORE ;
    SIZE 0.864 BY 0.27 ;
    SITE asap7sc7p5t ;
    PIN Y
        DIRECTION OUTPUT ;
    END Y
END INVx12_ASAP7_75t_SL
"""


class InjectVtObsTest(unittest.TestCase):
    def test_appends_into_existing_obs(self):
        out = inject_vt_obs.transform_lef(_WITH_OBS, "L")
        self.assertIn("LAYER LVTN ;\n\t\t\tRECT 0 0 0.378 0.135 ;", out)
        self.assertIn("LAYER LVTP ;\n\t\t\tRECT 0 0.135 0.378 0.27 ;", out)
        self.assertEqual(out.count("OBS"), 1)
        # Idempotent if run twice.
        self.assertEqual(inject_vt_obs.transform_lef(out, "L"), out)

    def test_creates_obs_when_absent(self):
        out = inject_vt_obs.transform_lef(_WITHOUT_OBS, "SL")
        self.assertIn("\tOBS\n\t\tLAYER SLVTN ;", out)
        self.assertIn("RECT 0 0 0.864 0.135 ;", out)
        self.assertIn("LAYER SLVTP ;\n\t\t\tRECT 0 0.135 0.864 0.27 ;", out)
        self.assertTrue(out.rstrip().endswith("END INVx12_ASAP7_75t_SL"))

    def test_sram_passthrough(self):
        self.assertEqual(
            inject_vt_obs.transform_lef(_WITHOUT_OBS, "SRAM"), _WITHOUT_OBS
        )


if __name__ == "__main__":
    unittest.main()
