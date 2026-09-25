"""Launch an odb_debug daemon on a placed design and ask it questions."""

import json
import os
import signal
import subprocess
import sys
import time
import unittest

import mcp_server
import odbdebug


class SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = os.path.join(os.environ["TEST_TMPDIR"], "odb-debug")
        cls.proc = subprocess.Popen(
            [
                sys.argv[1],
                "ODB_DEBUG_DIR=" + cls.dir,
                "LOG_DIR=" + os.path.join(os.environ["TEST_TMPDIR"], "log"),
                "ODB_DEBUG_IDLE_SECS=0",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        info = os.path.join(cls.dir, "daemon.json")
        deadline = time.time() + 600
        while not os.path.exists(info):
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "daemon exited early:\n"
                    + cls.proc.stdout.read().decode(errors="replace")
                )
            if time.time() > deadline:
                raise AssertionError("daemon did not write daemon.json")
            time.sleep(0.5)
        cls.d = odbdebug.Daemon(cls.dir)

    @classmethod
    def tearDownClass(cls):
        os.killpg(cls.proc.pid, signal.SIGTERM)
        cls.proc.wait(timeout=60)

    def test_status(self):
        s = self.d.status()
        self.assertEqual(s["design"], "multiplier")
        self.assertGreater(s["insts"], 0)
        self.assertGreater(s["rows"], 0)
        self.assertTrue(self.d.info["odb"].endswith("3_place.odb"))
        self.assertEqual(len(s["core"]), 4)

    def test_geometry_queries(self):
        self.assertEqual(self.d.macros(), [])
        insts = self.d.tcl(
            "lrange [lmap i [[ord::get_db_block] getInsts] {$i getName}] 0 0"
        )
        cell = self.d.cell_info(insts)
        self.assertEqual(cell["name"], insts)
        self.assertFalse(cell["is_macro"])
        cp = self.d.check_placement()
        self.assertEqual(cp["unplaced"], 0)
        self.assertEqual(cp["inside_macro"], 0)
        dump = self.d.dump_geometry(os.path.join(os.environ["TEST_TMPDIR"], "geom"))
        for f in (
            "summary.txt",
            "rows.txt",
            "macros.txt",
            "blockages.txt",
            "insts.txt",
        ):
            self.assertTrue(os.path.exists(os.path.join(dump["dir"], f)), f)
        self.assertEqual(dump["insts"], self.d.status()["insts"])

    def test_timing_queries(self):
        s = self.d.status()
        if not s["timing"]:
            with self.assertRaises(odbdebug.DaemonError):
                self.d.wns()
            return
        wns = self.d.wns()
        self.assertIn("wns", wns)
        self.assertEqual(len(self.d.worst_paths(3)), 3)
        self.assertIn("Design area", self.d.report("report_design_area"))

    def test_errors_and_stdout(self):
        with self.assertRaises(odbdebug.DaemonError):
            self.d.cell_info("no/such/instance")
        result, out = self.d.tcl_verbose("puts hello; expr 6 * 7")
        self.assertEqual((result, out), ("42", "hello\n"))

    def test_mcp_end_to_end(self):
        r = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "status", "arguments": {}},
            },
            self.dir,
        )
        self.assertFalse(r["result"]["isError"])
        self.assertEqual(
            json.loads(r["result"]["content"][0]["text"])["design"], "multiplier"
        )


class RelativeDirTest(unittest.TestCase):
    def test_a_relative_dir_is_relative_to_where_bazel_run_was_invoked(self):
        # bazel run starts the daemon from its runfiles tree and says where
        # the user was in BUILD_WORKING_DIRECTORY.
        cwd = os.path.join(os.environ["TEST_TMPDIR"], "user_cwd")
        os.makedirs(cwd)
        proc = subprocess.Popen(
            [
                sys.argv[1],
                "ODB_DEBUG_DIR=tmp/odb-debug",
                "LOG_DIR=" + os.path.join(os.environ["TEST_TMPDIR"], "log_rel"),
                "ODB_DEBUG_IDLE_SECS=0",
                "GUI_TIMING=0",
            ],
            env=dict(os.environ, BUILD_WORKING_DIRECTORY=cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            info = os.path.join(cwd, "tmp/odb-debug/daemon.json")
            deadline = time.time() + 120
            while not os.path.exists(info):
                if proc.poll() is not None:
                    raise AssertionError(
                        "daemon exited early:\n"
                        + proc.stdout.read().decode(errors="replace")
                    )
                if time.time() > deadline:
                    raise AssertionError("daemon did not write " + info)
                time.sleep(0.5)
            d = odbdebug.Daemon(os.path.join(cwd, "tmp/odb-debug"))
            self.assertEqual(d.status()["design"], "multiplier")
        finally:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=60)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
