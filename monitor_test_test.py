"""Unit tests for monitor_test.py."""

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from monitor_test import (
    format_duration,
    get_active_stages,
    get_stage_timings,
    print_timings,
)


class TestFormatDuration(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(format_duration(5), "5s")
        self.assertEqual(format_duration(59), "59s")

    def test_minutes(self):
        self.assertEqual(format_duration(60), "1m00s")
        self.assertEqual(format_duration(90), "1m30s")
        self.assertEqual(format_duration(3599), "59m59s")

    def test_hours(self):
        self.assertEqual(format_duration(3600), "1h00m00s")
        self.assertEqual(format_duration(3661), "1h01m01s")


class TestGetActiveStages(unittest.TestCase):
    @patch("monitor_test.subprocess.run")
    def test_parses_tee_processes(self, mock_run):
        mock_run.return_value.stdout = textwrap.dedent("""\
            oyvind 123 0 06:00 ? 00:00:00 tee -a /long/path/logs/asap7/lb_32x128/base/3_3_place_gp.tmp.log
            oyvind 456 0 06:00 ? 00:00:00 tee -a /long/path/logs/asap7/regfile/base/2_1_floorplan.tmp.log
            oyvind 789 0 06:00 ? 00:00:00 grep tee
        """)
        stages = get_active_stages()
        self.assertEqual(
            stages,
            [
                "asap7/lb_32x128/base/3_3_place_gp",
                "asap7/regfile/base/2_1_floorplan",
            ],
        )

    @patch("monitor_test.subprocess.run")
    def test_no_tee_processes(self, mock_run):
        mock_run.return_value.stdout = "oyvind 123 0 06:00 ? 00:00:00 bash\n"
        self.assertEqual(get_active_stages(), [])

    @patch("monitor_test.subprocess.run")
    def test_deduplicates(self, mock_run):
        mock_run.return_value.stdout = textwrap.dedent("""\
            a tee -a /x/logs/asap7/lb/base/3_3_place_gp.tmp.log
            b tee -a /y/logs/asap7/lb/base/3_3_place_gp.tmp.log
        """)
        stages = get_active_stages()
        self.assertEqual(stages, ["asap7/lb/base/3_3_place_gp"])


class TestGetStageTimings(unittest.TestCase):
    def test_extracts_timings(self):
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "asap7" / "lb_32x128" / "base"
            log_dir.mkdir(parents=True)

            (log_dir / "3_3_place_gp.log").write_text(
                "some output\n"
                "Took 201 seconds: global_placement -density 0.2\n"
                "more output\n"
            )
            (log_dir / "2_1_floorplan.log").write_text("Took 3 seconds: something\n")
            # tmp logs should be ignored
            (log_dir / "3_3_place_gp.tmp.log").write_text(
                "Took 999 seconds: should be ignored\n"
            )

            timings = get_stage_timings(tmpdir)
            self.assertEqual(len(timings), 2)
            self.assertEqual(timings[0], (201, "asap7/lb_32x128/base", "3_3_place_gp"))
            self.assertEqual(timings[1], (3, "asap7/lb_32x128/base", "2_1_floorplan"))

    def test_empty_dir(self):
        with TemporaryDirectory() as tmpdir:
            self.assertEqual(get_stage_timings(tmpdir), [])

    def test_nonexistent_dir(self):
        self.assertEqual(get_stage_timings("/nonexistent/path"), [])

    def test_no_took_line(self):
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "design"
            log_dir.mkdir()
            (log_dir / "stage.log").write_text("no timing info here\n")
            self.assertEqual(get_stage_timings(tmpdir), [])


class TestPrintTimings(unittest.TestCase):
    def test_prints_table(self):
        """Smoke test that print_timings doesn't crash."""
        timings = [
            (201, "asap7/lb_32x128/base", "3_3_place_gp"),
            (55, "asap7/lb_32x128_top/base", "3_3_place_gp"),
            (3, "asap7/lb_32x128/base", "2_1_floorplan"),
        ]
        # Should not raise
        print_timings(timings)

    def test_empty_timings(self):
        print_timings([])


if __name__ == "__main__":
    unittest.main()
