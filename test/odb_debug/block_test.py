"""The odb-debug daemon on a 10 um block whose 36 nm M3 pin has no access
point: the MCP pin_access tool must say why, from the markers DRT's own
pin-access debug logs; image must draw it headless; and an idle daemon
must exit while a long request must not be cut short.

argv: openroad, the asap7 tech LEF, block.tcl, daemon.tcl.
"""

import json
import os
import signal
import subprocess
import sys
import time
import unittest

import mcp_server
import odbdebug


def call(name, arguments, directory):
    r = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        directory,
    )
    result = r["result"]
    if result["isError"]:
        raise AssertionError(result["content"][0]["text"])
    return json.loads(result["content"][0]["text"])


class Launched(object):
    """A daemon on the block, its output in a file: DRT's debug output
    would fill a pipe nobody reads and stop the daemon mid-write."""

    def __init__(self, name, idle_secs):
        openroad, tech_lef, script, daemon = sys.argv[1:5]
        tmp = os.environ["TEST_TMPDIR"]
        self.dir = os.path.join(tmp, name)
        self.log = os.path.join(tmp, name + ".log")
        self.log_file = open(self.log, "wb")
        self.proc = subprocess.Popen(
            # One thread on purpose: the daemon must raise it, or a debug
            # pause inside tcl_eval holds the only thread there is.
            [openroad, "-no_init", "-no_splash", "-threads", "1", script],
            env=dict(
                os.environ,
                TECH_LEF=os.path.abspath(tech_lef),
                ODB_DEBUG_DAEMON=os.path.abspath(daemon),
                ODB_DEBUG_DIR=self.dir,
                ODB_DEBUG_IDLE_SECS=str(idle_secs),
            ),
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.info = os.path.join(self.dir, "daemon.json")
        deadline = time.time() + 30
        while not os.path.exists(self.info):
            if self.proc.poll() is not None or time.time() > deadline:
                self.stop()
                raise AssertionError("daemon did not start:\n" + self.output())
            time.sleep(0.2)
        self.d = odbdebug.Daemon(self.dir)

    def output(self):
        with open(self.log, "rb") as f:
            return f.read().decode(errors="replace")

    def stop(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
        self.proc.wait(timeout=60)
        self.log_file.close()


class BlockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.daemon = Launched("block", 0)
        cls.dir, cls.d = cls.daemon.dir, cls.daemon.d

    @classmethod
    def tearDownClass(cls):
        cls.daemon.stop()

    def test_a_the_tools_answer_through_the_viewer(self):
        self.assertEqual(
            self.d.info["url"], "http://127.0.0.1:%d" % self.d.info["port"]
        )
        self.assertEqual(call("status", {}, self.dir)["design"], "top")
        self.assertEqual(
            call("tcl", {"code": "puts hello; expr 6 * 7"}, self.dir),
            {"result": "42", "stdout": "hello\n"},
        )

    # Named to run before p18: the logger prints a message id at most
    # 1000 times per process, and p36's via candidates use most of them.
    def test_b_p36_has_no_access_point_and_says_why(self):
        r = call("pin_access", {"pin": "u_blk:p36"}, self.dir)
        self.assertTrue(r["no_access_point"])
        self.assertEqual(r["error"], "DRT-0073")
        self.assertGreater(r["pauses"], 0)
        # Planar exits from inside the pin step from 36 nm to the 18 nm
        # wire; from its ends they meet the end-of-line keep-out.
        self.assertIn("frcLef58RectOnlyConstraint", r["planar_markers"])
        self.assertIn("frcLef58EolKeepOutConstraint", r["planar_markers"])
        # Vias up land in the block's M4 obstruction.
        self.assertIn("Short on M4", r["via_markers"])
        self.assertGreater(r["via_candidates_rejected"], 0)

    def test_c_p18_is_reached_without_a_marker(self):
        r = call("pin_access", {"pin": "u_blk:p18"}, self.dir)
        self.assertEqual(r["planar_markers"], {})

    def test_image(self):
        out = os.path.join(os.environ["TEST_TMPDIR"], "p36.png")
        r = call(
            "image",
            {
                "path": out,
                "area": [6.40, 12.47, 6.58, 12.93],
                "width": 200,
                "options": {"tracks_pref": True},
            },
            self.dir,
        )
        self.assertEqual(r["path"], out)
        with open(out, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")


class IdleExitTest(unittest.TestCase):
    def test_a_request_longer_than_the_idle_time_survives_then_it_exits(self):
        daemon = Launched("idle", 2)
        try:
            # Busy for twice the idle time: not cut short, and answered.
            self.assertEqual(daemon.d.tcl("after 4000; expr 1 + 1"), "2")
            # Not gone the moment it returned either: idle counts from the end.
            self.assertIsNone(daemon.proc.poll())
            daemon.proc.wait(timeout=30)
            self.assertFalse(os.path.exists(daemon.info))
            self.assertIn("idle for 2 s, exiting", daemon.output())
        finally:
            daemon.stop()


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
