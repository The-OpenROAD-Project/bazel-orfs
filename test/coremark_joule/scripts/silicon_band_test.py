"""Tests for silicon_band.py — the measured x86/Arm core region."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from silicon_band import band, parts  # noqa: E402


def part(name="p", mhz=10.0, mj=5.0, **kw):
    d = {"part": name, "coremark_per_mhz": mhz, "coremark_per_mj_slope": mj}
    d.update(kw)
    return d


class TestParts(unittest.TestCase):
    def test_millijoule_becomes_joule(self):
        """silicon.json reports CoreMark per milliJoule; Figure 1's axis
        is per Joule."""
        self.assertAlmostEqual(parts({"parts": [part(mj=9.975)]})[0]["y"], 9975.0)

    def test_a_part_missing_a_coordinate_is_left_out(self):
        doc = {"parts": [part(), {"part": "no_energy", "coremark_per_mhz": 8.0}]}
        self.assertEqual([p["part"] for p in parts(doc)], ["p"])


class TestBand(unittest.TestCase):
    def test_spans_the_parts(self):
        b = band({"parts": [part(mhz=7.38, mj=9.975), part(mhz=12.53, mj=11.516)]})
        self.assertEqual(b["parts"], 2)
        self.assertAlmostEqual(b["x_min"], 7.38)
        self.assertAlmostEqual(b["x_max"], 12.53)
        self.assertAlmostEqual(b["y_min"], 9975.0)
        self.assertAlmostEqual(b["y_max"], 11516.0)

    def test_no_placeable_parts_gives_no_band(self):
        self.assertIsNone(band({"parts": []}))

    def test_a_document_without_parts_is_not_an_error(self):
        self.assertIsNone(band({}))


if __name__ == "__main__":
    unittest.main()
