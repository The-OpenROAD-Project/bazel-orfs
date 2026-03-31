"""Wrapper to run yosys_commands_test with correct import paths in Bazel."""

import os
import sys

# In Bazel runfiles, the modules live under their external repo dirs.
_RUNFILES = os.environ.get("RUNFILES_DIR", "")
for subdir in [
    os.path.join(_RUNFILES, "mock-openroad+", "src", "bin"),
    os.path.join(_RUNFILES, "mock-yosys+", "src", "bin"),
]:
    if os.path.isdir(subdir) and subdir not in sys.path:
        sys.path.insert(0, subdir)

# Now import and run via pytest
import pytest

sys.exit(
    pytest.main(
        [
            os.path.join(
                _RUNFILES, "mock-yosys+", "src", "bin", "yosys_commands_test.py"
            ),
            "-v",
        ]
    )
)
