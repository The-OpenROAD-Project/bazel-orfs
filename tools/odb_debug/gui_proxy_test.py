"""gui_proxy.py: only a request carrying the token reaches the viewer, the
link's token turns into a cookie, and what passes counts as activity."""

import http.client
import http.server
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import gui_proxy

TOKEN = "0123456789abcdef0123456789abcdef"
PORT = 8123


def head(target, cookie=None):
    lines = ["GET %s HTTP/1.1" % target, "Host: x"]
    if cookie:
        lines.append("Cookie: " + cookie)
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


class Decide(unittest.TestCase):
    def test_no_token_is_denied(self):
        action, reply = gui_proxy.decide(head("/"), TOKEN, PORT)
        self.assertEqual(action, "deny")
        self.assertTrue(reply.startswith(b"HTTP/1.1 403"))

    def test_a_wrong_token_is_denied(self):
        self.assertEqual(
            gui_proxy.decide(head("/?token=" + "f" * 32), TOKEN, PORT)[0], "deny"
        )
        self.assertEqual(
            gui_proxy.decide(head("/", "odbdebug8123=" + "f" * 32), TOKEN, PORT)[0],
            "deny",
        )

    def test_the_links_token_becomes_a_cookie_and_leaves_the_url(self):
        action, reply = gui_proxy.decide(
            head("/index.html?token=%s&x=1" % TOKEN), TOKEN, PORT
        )
        self.assertEqual(action, "redirect")
        text = reply.decode("latin-1")
        self.assertIn("HTTP/1.1 302", text)
        self.assertIn("\r\nLocation: /index.html?x=1\r\n", text)
        self.assertIn("Set-Cookie: odbdebug8123=%s; HttpOnly" % TOKEN, text)

    def test_the_cookie_is_forwarded(self):
        cookie = "other=1; odbdebug8123=%s" % TOKEN
        self.assertEqual(
            gui_proxy.decide(head("/ws", cookie), TOKEN, PORT), ("forward", None)
        )

    def test_another_daemons_cookie_is_not_this_ones(self):
        cookie = "odbdebug9999=%s" % TOKEN
        self.assertEqual(gui_proxy.decide(head("/", cookie), TOKEN, PORT)[0], "deny")

    def test_garbage_is_a_bad_request(self):
        action, reply = gui_proxy.decide(b"hello\r\n\r\n", TOKEN, PORT)
        self.assertEqual(action, "deny")
        self.assertTrue(reply.startswith(b"HTTP/1.1 400"))


class Viewer(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"viewer " + self.path.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Proxy(unittest.TestCase):
    """The proxy as daemon.tcl starts it, in front of a stand-in viewer."""

    @classmethod
    def setUpClass(cls):
        cls.viewer = http.server.HTTPServer(("127.0.0.1", 0), Viewer)
        threading.Thread(target=cls.viewer.serve_forever, daemon=True).start()
        cls.tmp = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        cls.activity = os.path.join(cls.tmp, "activity")
        cls.port = free_port()
        cls.proc = subprocess.Popen(
            [
                sys.executable,
                gui_proxy.__file__,
                "--listen",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--target-port",
                str(cls.viewer.server_address[1]),
                "--activity",
                cls.activity,
                "--pid",
                str(os.getpid()),
            ],
            env=dict(os.environ, ODB_DEBUG_TOKEN=TOKEN),
        )
        deadline = time.time() + 30
        while True:
            try:
                socket.create_connection(("127.0.0.1", cls.port)).close()
                break
            except OSError:
                if time.time() > deadline or cls.proc.poll() is not None:
                    raise
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait()
        cls.viewer.shutdown()

    def get(self, path, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read()

    def test_without_the_token_nothing_reaches_the_viewer(self):
        status, _, body = self.get("/")
        self.assertEqual(status, 403)
        self.assertNotIn(b"viewer", body)

    def test_the_link_then_the_cookie_reach_the_viewer_and_count(self):
        status, headers, _ = self.get("/?token=" + TOKEN)
        self.assertEqual(status, 302)
        cookie = headers["Set-Cookie"].split(";")[0]
        status, _, body = self.get(headers["Location"], cookie)
        self.assertEqual((status, body), (200, b"viewer /"))
        with open(self.activity) as f:
            word, when = f.read().split()
        self.assertEqual(word, "activity")
        self.assertLessEqual(abs(int(when) - time.time()), 60)


if __name__ == "__main__":
    unittest.main()
