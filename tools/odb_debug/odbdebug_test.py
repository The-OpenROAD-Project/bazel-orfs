"""Client and MCP server against a fake daemon speaking the wire protocol.

The real daemon is an OpenROAD process on a design; here a thread answers
the same base64-Tcl-in, JSON-out protocol with canned replies, so the
client's framing, quoting and error handling and the server's JSON-RPC
dispatch are tested without a design.
"""

import base64
import io
import json
import os
import socket
import tempfile
import threading
import unittest

import mcp_server
import odbdebug


class FakeDaemon(object):
    """Answers od_status and echoes anything else as its result."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.requests = []
        self.dir = tempfile.mkdtemp(prefix="odb_debug_test.")
        with open(os.path.join(self.dir, "daemon.json"), "w") as f:
            json.dump(
                {"port": self.port, "pid": 1, "design": "fake", "timing": False}, f
            )
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                line = b""
                while not line.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    line += chunk
                code = base64.b64decode(line.strip()).decode("utf-8")
                self.requests.append(code)
                conn.sendall((json.dumps(self.reply(code)) + "\n").encode("utf-8"))

    def reply(self, code):
        if code == "od_status":
            return {
                "ok": True,
                "result": json.dumps({"design": "fake", "insts": 3}),
                "stdout": "",
                "ms": 1,
            }
        if code.startswith("od_cell "):
            return {"ok": False, "error": "no instance named x", "stdout": "", "ms": 1}
        if code.startswith("od_capture "):
            return {"ok": True, "result": "", "stdout": "report text\n", "ms": 1}
        return {"ok": True, "result": code, "stdout": "hello\n", "ms": 1}

    def close(self):
        self.sock.close()


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

    def test_error_reply_raises(self):
        d = odbdebug.Daemon(self.fake.dir)
        with self.assertRaises(odbdebug.DaemonError):
            d.cell_info("x")

    def test_report_returns_stdout(self):
        d = odbdebug.Daemon(self.fake.dir)
        self.assertEqual(d.report("report_design_area"), "report text\n")

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
            {"status", "macros", "cell_info", "check_placement", "tcl", "report"}
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

    def test_call_tcl(self):
        r = self.rpc("tools/call", {"name": "tcl", "arguments": {"code": "puts hi"}})
        body = json.loads(r["result"]["content"][0]["text"])
        self.assertEqual(body, {"result": "puts hi", "stdout": "hello\n"})

    def test_daemon_error_is_tool_error_not_rpc_error(self):
        r = self.rpc("tools/call", {"name": "cell_info", "arguments": {"name": "x"}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("no instance", r["result"]["content"][0]["text"])

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


if __name__ == "__main__":
    unittest.main()
