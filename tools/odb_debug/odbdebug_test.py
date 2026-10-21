"""Client and MCP server against a fake daemon.

The real daemon is an OpenROAD web viewer on a design; here a fake viewer
(fake_viewer.py) answers od_web_request with canned replies, so the
client's framing, quoting and error handling and the server's JSON-RPC
dispatch are tested without a design.
"""

import base64
import io
import json
import os
import socket
import tempfile
import time
import unittest

import fake_viewer
import mcp_server
import odbdebug

# What detailed_route_debug -pa_markers logs for a rejected pin, cut down.
PA_LOG = [
    "[INFO DRT-0292] Marker frcLef58RectOnlyConstraint at (6480, 12502) (6498, 12538).",
    "Via VIA34 markers 1",
    "[INFO DRT-0119] Marker (6411, 12528) (6509, 12552) on M4:",
    "Short",
    "[ERROR DRT-0073] No access point for u_blk/p36 (BLK).",
]


class FakeDaemon(object):
    """A fake viewer answering od_web_request like daemon.tcl: od_status,
    errors, reports, a pin_access with debug pauses, and an echo for
    anything else."""

    def __init__(self):
        self.requests = []
        self.viewer = fake_viewer.FakeViewer(self.handle)
        self.port = self.viewer.port
        self.dir = tempfile.mkdtemp(prefix="odb_debug_test.")
        with open(os.path.join(self.dir, "daemon.json"), "w") as f:
            json.dump(
                {"port": self.port, "pid": 1, "design": "fake", "timing": False}, f
            )

    def handle(self, cmd):
        verb, _, b64 = cmd.partition(" ")
        if verb != "od_web_request":
            return {"result": "invalid command name", "is_error": True}
        code = base64.b64decode(b64).decode("utf-8")
        self.requests.append(code)
        reply, extra = self.reply(code)
        return dict(extra, result=json.dumps(reply))

    def reply(self, code):
        if code == "od_status":
            return {
                "ok": True,
                "result": json.dumps({"design": "fake", "insts": 3}),
                "stdout": "",
                "ms": 1,
            }, {}
        if code.startswith("od_cell "):
            return {
                "ok": False,
                "error": "no instance named x",
                "stdout": "",
                "ms": 1,
            }, {}
        if code.split(" ")[0] in (
            "od_period",
            "od_floor_wire",
            "od_floor_cycles",
            "od_skew_headroom",
            "od_floor_retime",
            "od_vt_headroom",
            "od_headroom",
        ):
            return {
                "ok": True,
                "result": json.dumps({"code": code}),
                "stdout": "",
                "ms": 1,
            }, {}
        if code.startswith("od_check_setup "):
            return {"ok": True, "result": "[]", "stdout": "", "ms": 1}, {}
        if code.startswith("od_capture {report_long"):
            text = "".join("line %06d\n" % i for i in range(100000))
            return {"ok": True, "result": "", "stdout": text, "ms": 1}, {}
        if code.startswith("od_capture "):
            return {"ok": True, "result": "", "stdout": "report text\n", "ms": 1}, {}
        if code.startswith("detailed_route_debug -pa -pa_markers -pin "):
            return {"ok": True, "result": "1 DRT-0073", "stdout": "", "ms": 1}, {
                "log": PA_LOG,
                "pauses": 3,
            }
        if code.startswith("[ord::get_db_tech] getDbUnitsPerMicron"):
            return {"ok": True, "result": "1000", "stdout": "", "ms": 1}, {}
        return {"ok": True, "result": code, "stdout": "hello\n", "ms": 1}, {}

    def close(self):
        self.viewer.close()


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeDaemon()

    @classmethod
    def tearDownClass(cls):
        cls.fake.close()

    def test_status_decodes_json(self):
        d = odbdebug.Daemon(self.fake.dir)
        self.assertEqual(d.status(), {"design": "fake", "insts": 3})

    def test_tcl_returns_result_and_stdout(self):
        d = odbdebug.Daemon(self.fake.dir)
        self.assertEqual(d.tcl_verbose("puts hi"), ("puts hi", "hello\n"))

    def test_call_quotes_arguments(self):
        d = odbdebug.Daemon(self.fake.dir)
        self.fake.requests[:] = []
        d.tcl(
            " ".join(["od_dump", odbdebug.tcl_quote("/a b/c"), odbdebug.tcl_quote(1)])
        )
        self.assertEqual(self.fake.requests[-1], "od_dump {/a b/c} 1")

    def test_check_setup_sends_an_absolute_out(self):
        d = odbdebug.Daemon(self.fake.dir)
        self.assertEqual(d.check_setup(), [])
        self.assertEqual(self.fake.requests[-1], "od_check_setup 10 3 20 {}")
        d.check_setup(5, 2, 7, "cs.txt")
        self.assertEqual(
            self.fake.requests[-1],
            "od_check_setup 5 2 7 " + os.path.abspath("cs.txt"),
        )

    def test_empty_argument_is_one_word(self):
        # an empty string is a word of its own, not a missing argument
        self.assertEqual(odbdebug.tcl_quote(""), "{}")

    def test_error_reply_raises(self):
        d = odbdebug.Daemon(self.fake.dir)
        with self.assertRaises(odbdebug.DaemonError):
            d.cell_info("x")

    def test_report_returns_stdout(self):
        d = odbdebug.Daemon(self.fake.dir)
        self.assertEqual(d.report("report_design_area"), "report text\n")

    def test_pin_access_continues_pauses_and_groups_markers(self):
        d = odbdebug.Daemon(self.fake.dir)
        r = d.pin_access("u_blk:p36")
        self.assertTrue(self.fake.requests[-2].startswith("detailed_route_debug"))
        self.assertEqual(r["pauses"], 3)
        self.assertEqual(r["error"], "DRT-0073")
        self.assertTrue(r["no_access_point"])
        self.assertEqual(
            r["planar_markers"],
            {
                "frcLef58RectOnlyConstraint": {
                    "count": 1,
                    "boxes": [[6480, 12502, 6498, 12538]],
                }
            },
        )
        self.assertEqual(list(r["via_markers"]), ["Short on M4"])
        self.assertEqual(r["dbu_per_micron"], 1000)

    def test_image_sends_save_image_web(self):
        d = odbdebug.Daemon(self.fake.dir)
        path = os.path.join(self.fake.dir, "a.png")
        with open(path, "wb") as f:
            f.write(b"png")
        r = d.image(path, [1, 2, 3, 4], 300, {"tracks_pref": True})
        self.assertEqual(
            self.fake.requests[-1],
            "save_image -web -width 300 -area {1.0 2.0 3.0 4.0} "
            "-display_option {tracks_pref true} " + path,
        )
        self.assertEqual(r, {"path": path, "bytes": 3})

    def test_image_makes_its_directory(self):
        d = odbdebug.Daemon(self.fake.dir)
        path = os.path.join(self.fake.dir, "new", "dir", "b.png")
        with self.assertRaises(odbdebug.DaemonError):
            d.image(path)
        self.assertTrue(os.path.isdir(os.path.dirname(path)))

    def test_image_that_wrote_nothing_raises(self):
        # the fake viewer, like save_image -web into a missing directory,
        # reports success and writes nothing
        d = odbdebug.Daemon(self.fake.dir)
        with self.assertRaisesRegex(odbdebug.DaemonError, "wrote no file"):
            d.image(os.path.join(self.fake.dir, "absent.png"))

    def test_missing_daemon(self):
        d = odbdebug.Daemon(os.path.join(self.fake.dir, "nowhere"))
        with self.assertRaises(odbdebug.DaemonError):
            d.status()

    def test_unreachable_daemon(self):
        dead = tempfile.mkdtemp(prefix="odb_debug_dead.")
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        with open(os.path.join(dead, "daemon.json"), "w") as f:
            json.dump({"port": port}, f)
        with self.assertRaises(odbdebug.DaemonError):
            odbdebug.Daemon(dead).status()


class McpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeDaemon()

    @classmethod
    def tearDownClass(cls):
        cls.fake.close()

    def rpc(self, method, params=None, msg_id=1):
        return mcp_server.handle(
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params},
            self.fake.dir,
        )

    def test_initialize(self):
        r = self.rpc("initialize", {"protocolVersion": "2024-11-05"})
        self.assertEqual(r["result"]["serverInfo"]["name"], "odb-debug")
        self.assertIn("tools", r["result"]["capabilities"])

    def test_notification_has_no_reply(self):
        self.assertIsNone(self.rpc("notifications/initialized"))

    def test_tools_list_has_schemas(self):
        tools = self.rpc("tools/list")["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertTrue(
            {
                "status",
                "macros",
                "cell_info",
                "check_placement",
                "check_setup",
                "tcl",
                "report",
                "pin_access",
                "image",
                "period",
                "floor_wire",
                "floor_cycles",
                "skew_headroom",
                "floor_retime",
                "vt_headroom",
                "headroom",
            }
            <= names
        )
        cell = [t for t in tools if t["name"] == "cell_info"][0]
        self.assertEqual(cell["inputSchema"]["required"], ["name"])

    def test_call_status(self):
        r = self.rpc("tools/call", {"name": "status", "arguments": {}})
        self.assertFalse(r["result"]["isError"])
        self.assertEqual(
            json.loads(r["result"]["content"][0]["text"])["design"], "fake"
        )

    def test_headroom_tools_call_their_procs_with_scope(self):
        # each headroom tool is its daemon proc, the scope and the hold
        # choice passed through as Tcl words, defaults when not given
        for name, args, code in [
            ("period", {}, "od_period"),
            ("period", {"target": 2000}, "od_period 2000.0"),
            ("floor_retime", {"ends": 9}, "od_floor_retime 9"),
            ("floor_wire", {}, "od_floor_wire"),
            ("floor_cycles", {}, "od_floor_cycles 0"),
            ("skew_headroom", {"ends": 50, "hold": False}, "od_skew_headroom 50 0"),
            ("skew_headroom", {}, "od_skew_headroom 0 1"),
            ("vt_headroom", {"ends": 7}, "od_vt_headroom 7"),
            ("headroom", {}, "od_headroom 0"),
            ("headroom", {"ends": 5, "target": 1500}, "od_headroom 5 1500.0"),
        ]:
            r = self.rpc("tools/call", {"name": name, "arguments": args})
            self.assertFalse(r["result"]["isError"], name)
            body = json.loads(r["result"]["content"][0]["text"])
            self.assertEqual(body, {"code": code}, name)

    def test_call_tcl(self):
        r = self.rpc("tools/call", {"name": "tcl", "arguments": {"code": "puts hi"}})
        body = json.loads(r["result"]["content"][0]["text"])
        self.assertEqual(body, {"result": "puts hi", "stdout": "hello\n"})

    def test_long_reply_is_capped_with_head_and_tail(self):
        r = self.rpc(
            "tools/call", {"name": "report", "arguments": {"command": "report_long"}}
        )
        text = r["result"]["content"][0]["text"]
        self.assertLess(len(text), mcp_server.MAX_TEXT + 500)
        self.assertTrue(text.startswith("line 000000\n"))
        self.assertTrue(text.endswith("line 099999\n"))
        self.assertIn("characters", text)
        self.assertIn("dropped", text)

    def test_cap_keeps_whole_lines_and_short_text(self):
        self.assertEqual(mcp_server.cap("short\n"), "short\n")
        text = "".join("%04d\n" % i for i in range(100))
        capped = mcp_server.cap(text, 100)
        kept = [l for l in capped.splitlines() if l and not l.startswith("[")]
        self.assertTrue(all(len(l) == 4 for l in kept))
        self.assertIn("0000", kept)
        self.assertIn("0099", kept)

    def test_daemon_error_is_tool_error_not_rpc_error(self):
        r = self.rpc("tools/call", {"name": "cell_info", "arguments": {"name": "x"}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("no instance", r["result"]["content"][0]["text"])

    def test_any_tool_exception_is_a_tool_error(self):
        # an exception that is not a DaemonError used to escape serve()
        # and end the server; it is the call's error, and the next call
        # is answered
        def boom(d, a):
            raise OSError("disk on fire")

        saved = mcp_server.TOOLS
        mcp_server.TOOLS = [("boom", "", {}, [], boom)] + list(saved)
        try:
            r = self.rpc("tools/call", {"name": "boom", "arguments": {}})
        finally:
            mcp_server.TOOLS = saved
        self.assertTrue(r["result"]["isError"])
        self.assertIn("OSError: disk on fire", r["result"]["content"][0]["text"])
        r = self.rpc("tools/call", {"name": "status", "arguments": {}})
        self.assertFalse(r["result"]["isError"])

    def test_image_that_wrote_nothing_is_a_tool_error(self):
        r = self.rpc(
            "tools/call",
            {
                "name": "image",
                "arguments": {"path": os.path.join(self.fake.dir, "none.png")},
            },
        )
        self.assertTrue(r["result"]["isError"])
        self.assertIn("wrote no file", r["result"]["content"][0]["text"])

    def test_missing_argument(self):
        r = self.rpc("tools/call", {"name": "cell_info", "arguments": {}})
        self.assertTrue(r["result"]["isError"])

    def test_unknown_tool_and_method(self):
        self.assertTrue(
            self.rpc("tools/call", {"name": "nope", "arguments": {}})["result"][
                "isError"
            ]
        )
        self.assertEqual(self.rpc("bogus")["error"]["code"], -32601)

    def test_serve_round_trip(self):
        stdin = io.StringIO(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            )
            + "\n"
            + "not json\n"
            + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
            + "\n"
        )
        stdout = io.StringIO()
        mcp_server.serve(stdin, stdout, self.fake.dir)
        lines = [json.loads(l) for l in stdout.getvalue().splitlines()]
        self.assertEqual([l.get("id") for l in lines], [1, None, 2])
        self.assertEqual(lines[1]["error"]["code"], -32700)


class LaunchTest(unittest.TestCase):
    """launch() and gui_state() with a bazelisk stand-in that records its
    arguments and holds until the test lets it go."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="odb_debug_launch.")
        self.dir = os.path.join(self.tmp, "odb-debug")
        self.args = os.path.join(self.tmp, "args")
        self.release = os.path.join(self.tmp, "release")
        self.bazelisk = os.path.join(self.tmp, "bazelisk")
        with open(self.bazelisk, "w") as f:
            f.write(
                "#!/bin/sh\n"
                'printf "%%s\\n" "$@" > %s.tmp && mv %s.tmp %s\n'
                "echo building the stage\n"
                "while [ ! -f %s ]; do sleep 0.1; done\n"
                "echo the stage failed\n"
                % (self.args, self.args, self.args, self.release)
            )
        os.chmod(self.bazelisk, 0o755)

    def wait_for(self, what, done):
        deadline = time.time() + 60
        while not done():
            self.assertLess(time.time(), deadline, "timed out waiting for " + what)
            time.sleep(0.05)

    def test_launch_loads_in_the_background_and_reports_its_end(self):
        env = {"SSH_CONNECTION": "10.0.0.2 51000 10.8.0.5 22"}
        saved = dict(os.environ)
        os.environ.update(env)
        try:
            r = odbdebug.launch(
                "//x:final_odb_debug",
                self.dir,
                ["GUI_TIMING=0"],
                workspace=self.tmp,
                bazelisk=self.bazelisk,
            )
        finally:
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(r["state"], "loading")
        self.wait_for("the arguments", lambda: os.path.exists(self.args))
        with open(self.args) as f:
            self.assertEqual(
                f.read().split("\n")[:-1],
                [
                    "run",
                    "//x:final_odb_debug",
                    "--",
                    "ODB_DEBUG_DIR=" + os.path.abspath(self.dir),
                    "ODB_DEBUG_GUI_BIND=10.8.0.5",
                    "GUI_TIMING=0",
                ],
            )
        self.assertEqual(odbdebug.gui_state(self.dir)["state"], "loading")
        # One daemon per directory: a second launch says what is there.
        with self.assertRaises(odbdebug.DaemonError) as e:
            odbdebug.launch("//y:z", self.dir, bazelisk=self.bazelisk)
        self.assertIn("already loading", str(e.exception))
        self.assertIn("//x:final_odb_debug", str(e.exception))
        # A launch that ends without a daemon is stopped, with its log.
        open(self.release, "w").close()
        self.wait_for(
            "the launch to end",
            lambda: odbdebug.gui_state(self.dir)["state"] == "stopped",
        )
        self.assertIn("the stage failed", odbdebug.gui_state(self.dir)["log_tail"])

    def test_a_stage_target_runs_its_gui_make_target(self):
        saved = dict(os.environ)
        os.environ.pop("SSH_CONNECTION", None)
        os.environ.pop("ODB_DEBUG_GUI_BIND", None)
        try:
            odbdebug.launch(
                "//x:cpu_cts",
                self.dir,
                ["GUI_TIMING=0"],
                workspace=self.tmp,
                bazelisk=self.bazelisk,
            )
        finally:
            os.environ.clear()
            os.environ.update(saved)
        self.wait_for("the arguments", lambda: os.path.exists(self.args))
        with open(self.args) as f:
            self.assertEqual(
                f.read().split("\n")[:-1],
                [
                    "run",
                    "//x:cpu_cts",
                    "--",
                    "ODB_DEBUG_DIR=" + os.path.abspath(self.dir),
                    "GUI_TIMING=0",
                    "gui_cts",
                ],
            )
        open(self.release, "w").close()

    def test_gui_make_target(self):
        self.assertEqual(odbdebug.gui_make_target("//x:cpu_final"), "gui_final")
        self.assertEqual(odbdebug.gui_make_target("//x/y:cpu_grt_td_cts"), "gui_cts")
        self.assertEqual(odbdebug.gui_make_target("@w//x:synth"), "gui_synth")
        self.assertIsNone(odbdebug.gui_make_target("//x:cpu_final_odb_debug"))
        self.assertIsNone(odbdebug.gui_make_target("//x:cpu"))

    def test_nothing_launched_is_stopped(self):
        self.assertEqual(odbdebug.gui_state(self.dir), {"state": "stopped"})

    def test_the_gui_binds_where_the_ssh_session_came_in(self):
        self.assertEqual(
            odbdebug.gui_bind({"SSH_CONNECTION": "1.2.3.4 5 10.8.0.5 22"}), "10.8.0.5"
        )
        self.assertEqual(
            odbdebug.gui_bind(
                {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22", "ODB_DEBUG_GUI_BIND": "a"}
            ),
            "a",
        )
        self.assertIsNone(odbdebug.gui_bind({}))


if __name__ == "__main__":
    unittest.main()
