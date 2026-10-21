import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odbdebug  # noqa: E402
import open_gui  # noqa: E402


class OpenGuiTest(unittest.TestCase):
    def run_main(self, argv, environ, states):
        launches = []

        def launch(target, directory, arguments, workspace=None):
            launches.append((target, directory, list(arguments), workspace))
            return {"state": "loading", "target": target, "log": "launch.log"}

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(odbdebug, "launch", launch), mock.patch.object(
            odbdebug, "gui_state", side_effect=states
        ), mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            code = open_gui.main(argv, environ, sleep=lambda s: None)
        return code, launches, out.getvalue(), err.getvalue()

    def test_waits_for_the_link_and_prints_it(self):
        code, launches, out, err = self.run_main(
            ["open_gui", "//x:cpu_cts", "GUI_TIMING=0"],
            {"BUILD_WORKSPACE_DIRECTORY": "/ws"},
            [
                {"state": "loading"},
                {"state": "loading"},
                {"state": "ready", "gui_url": "http://10.8.0.5:1/?token=t"},
            ],
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            launches, [("//x:cpu_cts", "/ws/tmp/odb-debug", ["GUI_TIMING=0"], "/ws")]
        )
        self.assertEqual(out, "http://10.8.0.5:1/?token=t\n")
        self.assertIn("token", err)

    def test_odb_debug_dir_is_relative_to_the_workspace(self):
        _, launches, _, _ = self.run_main(
            ["open_gui", "//x:cpu_final"],
            {"BUILD_WORKSPACE_DIRECTORY": "/ws", "ODB_DEBUG_DIR": "tmp/other"},
            [{"state": "ready", "gui_url": "u"}],
        )
        self.assertEqual(launches[0][1], "/ws/tmp/other")

    def test_a_daemon_that_stops_fails_with_its_log(self):
        code, _, out, err = self.run_main(
            ["open_gui", "//x:cpu_cts"],
            {"BUILD_WORKSPACE_DIRECTORY": "/ws"},
            [{"state": "stopped", "log_tail": "the stage failed"}],
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("the stage failed", err)

    def test_no_target_prints_usage(self):
        code, launches, _, err = self.run_main(["open_gui"], {}, [])
        self.assertEqual(code, 2)
        self.assertEqual(launches, [])
        self.assertIn("@bazel-orfs//:odb_debug", err)


if __name__ == "__main__":
    unittest.main()
