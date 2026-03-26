"""Unit tests for gui.metrics — ORFS metrics reading with mocked filesystem."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from gui_src.metrics import (
    MetricsReader,
    PPA_FIELDS,
    STAGE_JSONS,
    STAGE_OUTPUTS,
    STAGE_REPORTS,
    STAGE_SUBSTEPS,
)


class TestMetricsReader(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.bazel_bin = Path(self.tmpdir)
        self.reader = MetricsReader(self.bazel_bin)
        self.design = "test/ibex"
        self.design_dir = self.bazel_bin / self.design

    def _write_json(self, rel_path, data):
        path = self.design_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def _write_text(self, rel_path, text):
        path = self.design_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_get_metrics_reads_json(self):
        self._write_json("logs/6_report.json", {
            "finish__power__total": 0.0228,
            "finish__design__instance__area": 705.7,
            "finish__timing__setup__ws": -289.5,
            "finish__design__instance__count": 5491,
            "finish__design__instance__utilization": 0.427,
            "finish__design__die__area": 1834.5,
        })
        result = self.reader.get_metrics(self.design)
        self.assertIn("ppa", result)
        self.assertIn("power", result["ppa"])
        self.assertAlmostEqual(result["ppa"]["power"], 0.0228)

    def test_get_metrics_fmax(self):
        self._write_json("logs/6_report.json", {
            "finish__timing__fmax__clock:clk": 2.79e9,
        })
        result = self.reader.get_metrics(self.design)
        self.assertIn("fmax", result["ppa"])

    def test_get_metrics_empty_dir(self):
        result = self.reader.get_metrics(self.design)
        self.assertEqual(result["stages"], {})
        self.assertEqual(result["ppa"], {})

    def test_get_metrics_invalid_json(self):
        self._write_text("logs/6_report.json", "not json{{{")
        result = self.reader.get_metrics(self.design)
        # Should not crash, just return empty PPA
        self.assertEqual(result["ppa"], {})

    def test_get_log_concatenates_substeps(self):
        self._write_text("logs/2_1_floorplan.log", "Step 1 output")
        self._write_text("logs/2_4_floorplan_pdn.log", "PDN output")
        result = self.reader.get_log(self.design, "floorplan")
        self.assertIn("Step 1 output", result)
        self.assertIn("PDN output", result)
        self.assertIn("=== 2_1_floorplan ===", result)

    def test_get_log_direct_substep(self):
        self._write_text("logs/5_1_grt.log", "GRT log content")
        result = self.reader.get_log(self.design, "5_1_grt")
        self.assertEqual(result, "GRT log content")

    def test_get_log_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.reader.get_log(self.design, "synth")

    def test_get_report(self):
        self._write_text("reports/6_finish.rpt", "Timing report")
        self._write_text("reports/VDD.rpt", "VDD power")
        result = self.reader.get_report(self.design, "final")
        self.assertIn("Timing report", result)
        self.assertIn("VDD power", result)

    def test_get_report_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.reader.get_report(self.design, "synth")

    def test_get_stage_status_done(self):
        self._write_text("results/2_floorplan.odb", "binary")
        status = self.reader.get_stage_status(self.design, "floorplan")
        self.assertEqual(status, "done")

    def test_get_stage_status_missing(self):
        status = self.reader.get_stage_status(self.design, "floorplan")
        self.assertEqual(status, "missing")

    def test_get_all_status(self):
        # Create output files for a design
        odb_dir = self.design_dir
        odb_dir.mkdir(parents=True, exist_ok=True)
        (odb_dir / "1_synth.odb").write_text("x")
        (odb_dir / "2_floorplan.odb").write_text("x")

        result = self.reader.get_all_status()
        # Should find the design with synth and floorplan done
        found = False
        for design_path, stages in result.items():
            if "synth" in stages and "floorplan" in stages:
                found = True
        self.assertTrue(found, f"Expected synth+floorplan in status, got: {result}")

    def test_check_changes_detects_new_files(self):
        import time
        before = time.time()
        time.sleep(0.01)
        odb_dir = self.design_dir
        odb_dir.mkdir(parents=True, exist_ok=True)
        (odb_dir / "1_synth.odb").write_text("x")

        changes = self.reader.check_changes(since=before)
        self.assertTrue(len(changes) > 0)
        self.assertEqual(changes[0]["stage"], "synth")


class TestStageConstants(unittest.TestCase):
    """Verify our mirrored constants are consistent."""

    def test_all_stage_outputs_have_odb(self):
        for stage, filename in STAGE_OUTPUTS.items():
            self.assertTrue(filename.endswith(".odb"), f"{stage}: {filename}")

    def test_stage_substeps_keys_valid(self):
        valid_stages = {"synth", "floorplan", "place", "cts", "grt", "route", "final"}
        for stage in STAGE_SUBSTEPS:
            self.assertIn(stage, valid_stages, f"Unknown stage: {stage}")

    def test_ppa_fields_have_required_keys(self):
        required = {"power", "area", "worst_slack", "instances"}
        self.assertTrue(required.issubset(set(PPA_FIELDS.keys())))


if __name__ == "__main__":
    unittest.main()
