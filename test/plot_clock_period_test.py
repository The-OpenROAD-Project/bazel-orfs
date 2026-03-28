"""Functional test for plot_clock_period.py.

Creates fixture YAML files, runs the tool, and verifies CSV/YAML outputs.
"""

import csv
import os
import subprocess
import sys
import tempfile
import unittest

import yaml


class TestPlotClockPeriod(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_pdf = os.path.join(self.tmpdir, "out.pdf")
        self.output_yaml = os.path.join(self.tmpdir, "out.yaml")
        self.output_csv = os.path.join(self.tmpdir, "out.csv")

        # Create fixture YAML files matching the expected filename pattern:
        # <series><index>_<word>_stats
        self.input_files = []
        fixtures = [
            (
                "foo_1_synth_stats",
                {"name": "foo_1", "power": 1.0, "clock_period": 10.0, "area": 100.0},
            ),
            (
                "foo_2_synth_stats",
                {"name": "foo_2", "power": 2.0, "clock_period": 20.0, "area": 200.0},
            ),
            (
                "bar_1_synth_stats",
                {"name": "bar_1", "power": 0.5, "clock_period": 5.0, "area": 50.0},
            ),
        ]
        for filename, data in fixtures:
            path = os.path.join(self.tmpdir, filename)
            with open(path, "w") as f:
                yaml.dump(data, f)
            self.input_files.append(path)

    def _find_tool(self):
        """Locate the plot_clock_period_tool binary from runfiles."""
        runfiles = os.environ.get("TEST_SRCDIR", "")
        candidate = os.path.join(runfiles, "_main", "plot_clock_period_tool")
        if os.path.isfile(candidate):
            return candidate
        # Fallback: search in data deps
        for path in sys.argv:
            if "plot_clock_period" in path:
                return path
        self.skipTest("plot_clock_period_tool not found in runfiles")

    def test_generates_csv_and_yaml(self):
        tool = self._find_tool()
        result = subprocess.run(
            [
                tool,
                self.output_pdf,
                self.output_yaml,
                self.output_csv,
                "Test Title",
            ]
            + self.input_files,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Tool failed:\n{result.stderr}")

        # Verify CSV output exists and has expected rows
        self.assertTrue(os.path.isfile(self.output_csv))
        with open(self.output_csv) as f:
            lines = f.read().strip().split("\n")
        self.assertEqual(len(lines), 3, f"Expected 3 CSV rows, got {len(lines)}")

        # Verify YAML output exists and is parseable
        self.assertTrue(os.path.isfile(self.output_yaml))
        with open(self.output_yaml) as f:
            data = yaml.safe_load(f)
        self.assertIsInstance(data, dict)

        # Verify PDF was created
        self.assertTrue(os.path.isfile(self.output_pdf))
        self.assertGreater(os.path.getsize(self.output_pdf), 0)


if __name__ == "__main__":
    unittest.main()
