"""The odb-debug daemon on its web backend, on a block whose 36 nm M3 pin
has no access point: the MCP pin_access tool must say why, from the
markers DRT's own pin-access debug logs.

argv: openroad, the asap7 tech LEF, web_block.tcl, daemon.tcl.
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


class WebBackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        openroad, tech_lef, script, daemon = sys.argv[1:5]
        cls.dir = os.path.join(os.environ["TEST_TMPDIR"], "odb-debug")
        # A file, not a pipe: DRT's debug output would fill a pipe nobody
        # reads and stop the daemon mid-write.
        cls.log = os.path.join(os.environ["TEST_TMPDIR"], "daemon.log")
        cls.log_file = open(cls.log, "wb")
        cls.proc = subprocess.Popen(
            # One thread on purpose: the daemon must raise it, or a debug
            # pause inside tcl_eval holds the only thread there is.
            [openroad, "-no_init", "-no_splash", "-threads", "1", script],
            env=dict(
                os.environ,
                TECH_LEF=os.path.abspath(tech_lef),
                ODB_DEBUG_DAEMON=os.path.abspath(daemon),
                ODB_DEBUG_DIR=cls.dir,
                ODB_DEBUG_BACKEND="web",
            ),
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        info = os.path.join(cls.dir, "daemon.json")
        deadline = time.time() + 30
        while not os.path.exists(info):
            if cls.proc.poll() is not None or time.time() > deadline:
                cls.tearDownClass()
                with open(cls.log, "rb") as f:
                    log = f.read().decode(errors="replace")
                raise AssertionError("daemon did not start:\n" + log)
            time.sleep(0.2)
        cls.d = odbdebug.Daemon(cls.dir)

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            os.killpg(cls.proc.pid, signal.SIGTERM)
        cls.proc.wait(timeout=60)
        cls.log_file.close()

    def test_a_the_socket_tools_answer_through_the_viewer(self):
        self.assertEqual(self.d.info["backend"], "web")
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


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
