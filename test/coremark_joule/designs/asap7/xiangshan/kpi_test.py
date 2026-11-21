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


class SdcTest(unittest.TestCase):
    """A period is measured against its row's SDC; the table says which,
    with the parent's worst slack, and the chart marks where it changes."""

    def test_parent_wns_recorded_or_derived(self):
        self.assertEqual(
            kpi.parent_wns(
                {"sdc_ps": 1800, "parent_ps": 2377, "wns_ps": {"parent": -577}}
            ),
            -577,
        )
        # period = SDC - WNS
        self.assertEqual(kpi.parent_wns({"sdc_ps": 473, "parent_ps": 1822}), -1349)
        self.assertIsNone(kpi.parent_wns({"parent_ps": 1822}))
        self.assertIsNone(kpi.parent_wns({"sdc_ps": 473}))

    def test_sdc_changes(self):
        runs = [{"sdc_ps": 800}, {"sdc_ps": 473}, {"sdc_ps": 473}, {"sdc_ps": 1800}]
        self.assertEqual(kpi.sdc_changes(runs), [(1, 473), (3, 1800)])

    def test_table_gives_sdc_and_parent_wns(self):
        runs = [
            {
                "date": "2026-11-21",
                "sdc_ps": 1800,
                "note": "n",
                "parent_ps": 2377,
                "blocks": {"Frontend": 1858},
                "wns_ps": {"parent": -577, "Frontend": -58},
            }
        ]
        head, _, row = kpi.table(runs).splitlines()
        self.assertIn("| date | SDC | design | Top | parent | parent WNS |", head)
        self.assertIn("| 2026-11-21 | 1,800 | 2,377 |  | 2,377 | -577 |", row)


if __name__ == "__main__":
    unittest.main()
