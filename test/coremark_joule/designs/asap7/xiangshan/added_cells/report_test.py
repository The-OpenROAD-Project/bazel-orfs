"""Unit tests for added_cells report statistics and Markdown formatting."""

import unittest

import report


class ReportTest(unittest.TestCase):
    def test_compare_metric_resolution(self):
        # Clear separation well outside 2*sigma*sqrt(2/3)
        res = report.compare_metric([1025.0, 1030.0, 1028.0], [980.0, 985.0, 982.0])
        self.assertTrue(res["resolved"])
        self.assertLess(res["delta"], -40.0)

        # Difference buried inside placement seed noise -> did not resolve
        noisy = report.compare_metric(
            [1020.0, 1040.0, 1030.0], [1022.0, 1038.0, 1027.0]
        )
        self.assertFalse(noisy["resolved"])

    def test_render_markdown(self):
        base = {
            "sdc_period_ps": 473.0,
            "reg2reg_wns_ps": -554.0,
            "reg2reg_min_period_ps": 1027.0,
            "ff_only_min_period_ps": 753.0,
            "reg2reg_tns_ns": -410.0,
            "reg2reg_violating_endpoints": 3200,
            "reg2reg_total_endpoints": 28000,
            "stdcell_count": 180000,
            "stdcell_area_um2": 42000.0,
            "flops": 22000,
            "buf_count": 15000,
            "inv_count": 28000,
            "added_cell_count": 0,
            "added_cell_area_um2": 0.0,
            "vt_counts": {"RVT": 100000, "LVT": 50000, "SLVT": 30000, "other": 0},
            "vt_areas_um2": {
                "RVT": 22000.0,
                "LVT": 12000.0,
                "SLVT": 8000.0,
                "other": 0.0,
            },
            "guide_wl_um": 4500000.0,
            "report_power": {
                "Total": {
                    "internal": 0.090,
                    "switching": 0.060,
                    "leakage": 0.005,
                    "total": 0.155,
                }
            },
            "added_by_stem": {},
        }
        added = dict(
            base,
            reg2reg_min_period_ps=995.0,
            stdcell_count=165000,
            stdcell_area_um2=40500.0,
            inv_count=19000,
            added_cell_count=24000,
            added_cell_area_um2=6200.0,
            added_by_stem={"NAND2Bx2": 4100, "AO21Bx2": 3200},
        )
        records = [
            dict(base, arm="stock", seed=1, stage="1_synth"),
            dict(added, arm="added", seed=1, stage="1_synth"),
            dict(base, arm="stock", seed=1, stage="5_1_grt"),
            dict(added, arm="added", seed=1, stage="5_1_grt"),
        ]
        md = report.render_markdown(records)
        self.assertIn("### Synthesis", md)
        self.assertIn("### Global Route", md)
        self.assertIn("`NAND2Bx2`", md)


if __name__ == "__main__":
    unittest.main()
