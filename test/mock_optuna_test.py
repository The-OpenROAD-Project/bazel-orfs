#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest


class TestMockOptuna(unittest.TestCase):
    def test_tuner_executable(self):
        # Find the executable in the runfiles
        executable_path = "test/mock_tuner_executable"

        if not os.path.exists(executable_path):
            self.skipTest(f"Executable not found at {executable_path}")

        with tempfile.TemporaryDirectory() as td:
            metrics_out = os.path.join(td, "metrics.json")

            # Run with actual execution, capturing output.
            # We override variables to simulate a tuner changing parameters and passing an absolute path.
            result = subprocess.run(
                [executable_path, "PLACE_DENSITY=0.42", f"METRICS_OUT={metrics_out}"],
                capture_output=True,
                text=True,
                check=True,
            )

            # check that it ran cell_count.tcl and output success
            self.assertIn("Mock script completed successfully!", result.stdout)
            self.assertIn(f"Wrote metrics to {metrics_out}", result.stdout)

            # verify the metrics file was written to the absolute path
            self.assertTrue(os.path.exists(metrics_out))
            with open(metrics_out, "r") as f:
                data = json.load(f)
                self.assertEqual(data["density"], 0.42)
                self.assertIn("tns", data)
                self.assertIn("wns", data)
                self.assertEqual(data["cell_count"], 32)

            self.assertEqual(result.returncode, 0)

        # Test that failing to provide METRICS_OUT fails the script (because we didn't use `info exists`)
        result = subprocess.run(
            [executable_path, "PLACE_DENSITY=0.42"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            'can\'t read "::env(METRICS_OUT)": no such variable',
            result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
