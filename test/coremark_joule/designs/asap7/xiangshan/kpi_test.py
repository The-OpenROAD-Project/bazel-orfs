"""kpi.py's design period: the slowest part, and a lower bound until every
part, the Top of a carved run included, is measured."""

import unittest

import kpi


class DesignPeriodTest(unittest.TestCase):
    def test_slowest_part_sets_the_period(self):
        run = {"blocks": {"Rob": 2117, "XSTile_parent": 2111}, "top_ps": 2300}
        self.assertEqual(kpi.design_ps(run), 2300)
        run["top_ps"] = 1900
        self.assertEqual(kpi.design_ps(run), 2117)

    def test_carved_run_without_the_top_is_a_lower_bound(self):
        run = {"blocks": {"Rob": 2117, "XSTile_parent": 2111}}
        self.assertFalse(kpi.measured_all(run))
        run["top_ps"] = 2300
        self.assertTrue(kpi.measured_all(run))

    def test_flat_parent_run_needs_only_its_blocks(self):
        self.assertTrue(kpi.measured_all({"parent_ps": 2504, "blocks": {"Rob": 1939}}))
        self.assertFalse(kpi.measured_all({"parent_ps": 2504}))

    def test_table_marks_the_lower_bound(self):
        runs = [
            {
                "date": "2026-11-03",
                "note": "no Top",
                "blocks": {"Rob": 2117, "XSTile_parent": 2111},
            },
            {
                "date": "2026-11-04",
                "note": "Top",
                "blocks": {"Rob": 2117, "XSTile_parent": 2111},
                "top_ps": 2050,
            },
        ]
        rows = kpi.table(runs).splitlines()[2:]
        self.assertIn("| ≥ 2,117 |", rows[0])
        self.assertIn("| 2,117 | 2,050 |", rows[1])


if __name__ == "__main__":
    unittest.main()
