"""Shared helpers for mock binary unit tests."""

import importlib.util
import os


def load_mock(module_name):
    """Load a mock module from runfiles or source tree.

    Args:
        module_name: e.g. "openroad" or "klayout"
    """
    runfiles = os.environ.get("RUNFILES_DIR", "")
    mock_dir = "mock-{}".format(module_name)
    py_file = "{}.py".format(module_name)
    candidates = [
        os.path.join(runfiles, mock_dir + "+", "src", "bin", py_file),
        os.path.join(runfiles, mock_dir, "src", "bin", py_file),
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "mock",
            module_name,
            "src",
            "bin",
            py_file,
        ),
    ]
    for path in candidates:
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location(module_name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("Cannot find {} in {}".format(py_file, candidates))
