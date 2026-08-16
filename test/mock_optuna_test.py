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
            check=True
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
            check=True
        )
        
        # cell_count.tcl is a real script in the repo, check that it executed successfully.
        # (It just counts cells and doesn't do much if we don't pass an output arg, but it succeeds)
        self.assertEqual(result.returncode, 0)

if __name__ == "__main__":
    unittest.main()
