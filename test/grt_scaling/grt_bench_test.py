"""The driver's command construction and the report's table, without a design."""
import json
import os
import tempfile
import unittest

import grt_bench
import report


class CommandTest(unittest.TestCase):
    def test_make_command(self):
        design = {"deps": "tmp/lab/deps", "odb": "results/asap7/x/base/4_cts.odb"}
        arm = {"args": "-congestion_iterations 5", "layers": "M2 M5", "openroad": "/opt/or/openroad", "pin_access": False}
        argv = grt_bench.make_command(design, arm, "/r/xs__a__r0.json", {"args": "-allow_congestion"})
        self.assertTrue(argv[0].endswith("tmp/lab/deps/make"))
        self.assertEqual(argv[1], "run")
        self.assertIn("GRT_BENCH_ARGS=-allow_congestion -congestion_iterations 5", argv)
        self.assertIn("GRT_BENCH_LAYERS=M2 M5", argv)
        self.assertIn("GRT_BENCH_PIN_ACCESS=0", argv)
        self.assertIn("OPENROAD_EXE=/opt/or/openroad", argv)
        self.assertTrue(any(a.startswith("ODB_FILE=") and a.endswith("/_main/results/asap7/x/base/4_cts.odb") for a in argv))
        self.assertIn("LOG_DIR=/r", argv)

    def test_scope_command_caps(self):
        cmd = grt_bench.scope_command(["make", "run"], "u", {"memory_max": "60G", "swap_max": "70G"})
        if cmd[0] == "systemd-run":
            self.assertIn("MemoryMax=60G", cmd)
            self.assertIn("MemorySwapMax=70G", cmd)
            self.assertEqual(cmd[-2:], ["make", "run"])

    def test_cell_name(self):
        self.assertEqual(grt_bench.cell_name("xs", "baseline", 0), "xs__baseline__r0")


class ReportTest(unittest.TestCase):
    def test_table_with_baseline_ratio(self):
        d = tempfile.mkdtemp(prefix="grt_report.")
        cells = [
            {"design": "wb", "arm": "baseline", "status": "ok", "wall_s": 100, "global_route_s": 80, "vm_hwm_kb": 2097152, "wirelength": 12345},
            {"design": "wb", "arm": "fast", "status": "ok", "wall_s": 60, "global_route_s": 40, "vm_hwm_kb": 1048576, "wirelength": 12400},
            {"design": "wb", "arm": "dead", "status": "timeout", "wall_s": 9000},
        ]
        for i, c in enumerate(cells):
            with open(os.path.join(d, "c%d.json" % i), "w") as f:
                json.dump(c, f)
        with open(os.path.join(d, "c0.metrics.json"), "w") as f:
            f.write("{}")
        t = report.table(report.load(d), "baseline")
        self.assertIn("| wb | fast | ok | 60.0 | - | 40.0 | 2.00x |", t)
        self.assertIn("| wb | dead | timeout | 9000 | - | - | - |", t)
        self.assertIn("| wb | baseline | ok | 100 | - | 80.0 | 1.00x |", t)


if __name__ == "__main__":
    unittest.main()
