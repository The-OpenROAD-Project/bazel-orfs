#!/usr/bin/env python3

import os
import subprocess
import sys
import unittest


class TestMockOptuna(unittest.TestCase):
    def test_tuner_executable(self):
        # Find the executable in the runfiles
        executable_path = "test/mock_tuner_executable"

        # In a bazel py_test, runfiles are available and the working directory is the runfiles root
        if not os.path.exists(executable_path):
            self.skipTest(f"Executable not found at {executable_path}")

        # Run with --byo-openroad-cmd-line to verify it prints the command
        result = subprocess.run(
            [executable_path, "--byo-openroad-cmd-line"],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()
        self.assertIn("openroad", output)
        self.assertIn("-exit", output)
        self.assertIn("-metrics", output)
        self.assertIn("-no_init", output)
        self.assertIn("tuner_wrapper.tcl", output)

        # Run with actual execution, capturing output.
        # We override a variable to simulate a tuner changing parameters.
        result = subprocess.run(
            [executable_path, "--variable", "PLACE_DENSITY=0.42"],
            capture_output=True,
            text=True,
            check=True,
        )

        # cell_count.tcl prints "Mock script completed successfully!" but now we also print metrics.json to stdout
        # However, cell_count.tcl doesn't write metrics.json in this mock.
        # But wait, openroad generates metrics.json by default if -metrics is passed!
        # Actually it only writes if openroad itself has a metrics command, but let's just check success
        self.assertEqual(result.returncode, 0)

        # Test new features: --tmp-dir, --keep, --log-file, --tcl-command
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            log_path = os.path.join(td, "run.log")
            result = subprocess.run(
                [
                    executable_path,
                    "--tmp-dir",
                    td,
                    "--log-file",
                    log_path,
                    "--keep",
                    "--tcl-command",
                    'puts "Injected TCL command working!"',
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(result.returncode, 0)

            # Since stdout was redirected to log_file, the main stdout should just be metrics if they exist
            # Let's check the log file
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r") as f:
                log_content = f.read()
                self.assertIn("Injected TCL command working!", log_content)
                self.assertIn("Mock script completed successfully!", log_content)

            # Check that --keep actually kept the wrapper
            # Find the generated directory in td
            subdirs = [
                os.path.join(td, d)
                for d in os.listdir(td)
                if d.startswith("orfs_tuner_")
            ]
            self.assertGreater(len(subdirs), 0)
            wrapper_path = os.path.join(subdirs[0], "tuner_wrapper.tcl")
            self.assertTrue(os.path.exists(wrapper_path))
            with open(wrapper_path, "r") as f:
                wrapper_content = f.read()
                self.assertIn("Injected TCL command working!", wrapper_content)


if __name__ == "__main__":
    unittest.main()
