"""Tests for the report generator.

The property under test is the one that keeps a partial campaign from
reading as a complete one: a rung that was never run has to appear in the
table as missing, and a report with no results at all has to refuse to
render rather than emit an empty but well-formed document.
"""

import json
import tempfile
import unittest
from pathlib import Path

import report


def probe(arm, endpoints, **kwargs):
    data = {
        "arm": arm,
        "stage": kwargs.pop("stage", "4_1_cts"),
        "parasitics": kwargs.pop("parasitics", "global_routing"),
        "clock_period": kwargs.pop("clock_period", 1000.0),
        "wns": min(endpoints.values()),
        "min_period": kwargs.pop("min_period", 900.0),
        "seconds": kwargs.pop("seconds", 1.0),
        "pin_access_seconds": kwargs.pop("pin_access_seconds", 0.5),
        "nets_with_guides": kwargs.pop("nets_with_guides", 10),
        "endpoints": [{"endpoint": e, "slack": s} for e, s in endpoints.items()],
    }
    data.update(kwargs)
    return data


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, name, data):
        (self.dir / (name + ".json")).write_text(json.dumps(data))

    def test_arm_name_is_split_into_design_and_rung(self):
        self.write("gcd_gr_stock", probe("gcd_gr_stock", {"a": 1.0}))
        found = report.discover(self.dir)
        self.assertIn(("gcd", "gr_stock"), found)

    def test_a_rung_that_was_not_run_is_named_as_missing(self):
        eps = {"a": -1.0, "b": 2.0, "c": 3.0}
        self.write("gcd_spef", probe("gcd_spef", eps, parasitics="spef"))
        self.write("gcd_placement", probe("gcd_placement", eps))
        found = report.discover(self.dir)
        text = report.section_ladder(found)
        self.assertIn("not run", text)
        self.assertIn("gr_stock", text)

    def test_floors_report_the_unmeasured_sigma_as_unmeasured(self):
        self.write("gcd_spef", probe("gcd_spef", {"a": 1.0}, parasitics="spef"))
        text = report.section_floors(report.discover(self.dir))
        # 5% of a 1000 ps clock.
        self.assertIn("50.00", text)
        self.assertIn("not measured", text)

    def test_a_design_without_the_reference_renders_nothing_for_it(self):
        # Without the SPEF there is nothing to score against, and a table
        # row scored against a different instrument would be a silent
        # change of question.
        self.write("gcd_placement", probe("gcd_placement", {"a": 1.0}))
        found = report.discover(self.dir)
        self.assertEqual(report.section_ladder(found), report.MISSING)

    def test_render_covers_every_section(self):
        eps = {"a": -1.0, "b": 2.0, "c": 3.0, "d": 4.0}
        self.write("gcd_spef", probe("gcd_spef", eps, parasitics="spef"))
        self.write("gcd_placement", probe("gcd_placement", eps))
        self.write("gcd_gr_stock", probe("gcd_gr_stock", eps))
        text = report.render(report.discover(self.dir))
        self.assertIn("A0 -- the two floors", text)
        self.assertIn("Spearman", text)
        self.assertIn("what it is", text)


if __name__ == "__main__":
    unittest.main()
