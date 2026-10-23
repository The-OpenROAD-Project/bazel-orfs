import json
import os
import tempfile
import unittest

import report


class ReportTest(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(report.seconds("Elapsed time: 1:02:03.5[h:]min:sec"), 3723.5)
        self.assertEqual(report.seconds("Elapsed time: 0:05.25[h:]min:sec"), 5.25)

    def test_load_power(self):
        text = "[WARNING STA-2402] power activity ...\n" + '{"Total": {"total": 1e-3}}'
        self.assertEqual(report.total_power(report.load_power(text)), 1e-3)
        with self.assertRaises(ValueError):
            report.load_power("Error: no design\n{}")

    def test_split_arm(self):
        self.assertEqual(
            report.split_arm("coralnpu_exmem_inline_1700"),
            ("coralnpu_exmem", "inline", 1700),
        )
        self.assertEqual(report.split_arm("ibex_flops_1468"), ("ibex", "flops", 1468))

    def test_dominates_and_unmeasured(self):
        with tempfile.TemporaryDirectory() as d:

            def put(arm, period, area, power):
                with open(os.path.join(d, arm + ".json"), "w") as f:
                    json.dump(
                        {
                            "period_ps": 1000,
                            "wns_ps": 1000 - period,
                            "min_period_ps": period,
                            "stdcell_um2": area,
                            "cells": 1,
                        },
                        f,
                    )
                with open(os.path.join(d, arm + "_power.json"), "w") as f:
                    json.dump({"total": {"total": power}}, f)

            put("x_flops_1000", 900.0, 100.0, 0.010)
            put("x_inline_1000", 850.0, 90.0, 0.009)
            put("x_mux_1000", 950.0, 80.0, 0.008)
            arms = ["x_flops_1000", "x_inline_1000", "x_mux_1000", "x_netlist_1000"]
            m, _ = report.collect([os.path.join(d, n) for n in os.listdir(d)], arms)
            r = {row["shape"]: row for row in report.rows(arms, m)}
            self.assertTrue(r["inline"]["dominates"])
            self.assertFalse(r["mux"]["dominates"])
            self.assertEqual(r["netlist"]["note"], "not yet measured")


if __name__ == "__main__":
    unittest.main()
