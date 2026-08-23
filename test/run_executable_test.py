#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest


class TestRunExecutable(unittest.TestCase):
    def test_build_time_arguments(self):
        executable_path = "test/run_executable_with_args"
        if not os.path.exists(executable_path):
            self.skipTest(f"Executable not found at {executable_path}")

        result = subprocess.run(
            [executable_path, "--cmd", "print-PLACE_DENSITY"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("PLACE_DENSITY: 0.10", result.stdout)

    def test_cli_argument_overrides(self):
        executable_path = "test/run_executable_with_args"
        if not os.path.exists(executable_path):
            self.skipTest(f"Executable not found at {executable_path}")

        result = subprocess.run(
            [executable_path, "PLACE_DENSITY=0.42", "--cmd", "print-PLACE_DENSITY"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("PLACE_DENSITY: 0.42", result.stdout)

    def test_cli_cmd_override(self):
        executable_path = "test/mock_tuner_executable"
        if not os.path.exists(executable_path):
            self.skipTest(f"Executable not found at {executable_path}")

        result = subprocess.run(
            [executable_path, "--cmd", "print-PLACE_DENSITY"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Using default LB_ARGS since mock_tuner_executable relies on the default PLACE_DENSITY from the floorplan stage
        self.assertIn("PLACE_DENSITY: 0.65", result.stdout)

    def test_build_time_cmd_override(self):
        executable_path = "test/run_executable_custom_cmd"
        if not os.path.exists(executable_path):
            self.skipTest(f"Executable not found at {executable_path}")

        result = subprocess.run(
            [executable_path],
            capture_output=True,
            text=True,
            check=True,
        )
        # Since it executes `print-PLACE_DENSITY` instead of `run` which executes the tcl script, it should just print
        self.assertIn("PLACE_DENSITY: 0.65", result.stdout)


if __name__ == "__main__":
    unittest.main()
