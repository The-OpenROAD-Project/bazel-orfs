"""The cut page's server: the viewer's framing, the token, the WebSocket."""

import base64
import json
import os
import socket
import struct
import threading
import unittest

import serve


def http(port, head):
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(head.encode("latin-1"))
    data = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()
    return data


def client_frame(payload):
    """A masked binary frame, as a browser sends."""
    mask = os.urandom(4)
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    n = len(payload)
    head = bytes([0x82]) + (
        bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n)
    )
    return head + mask + body


class FrameTest(unittest.TestCase):
    def test_round_trip(self):
        f = serve.frame(7, serve.T_JSON, b"{}")
        self.assertEqual(f[:8], b"\0\0\0\x07\0\0\0\0")
        self.assertEqual(serve.unframe(f), (7, serve.T_JSON, b"{}"))

    def test_a_short_frame_is_refused(self):
        with self.assertRaises(ValueError):
            serve.unframe(b"\0\0\0")

    def test_the_accept_key_of_rfc6455(self):
        self.assertEqual(
            serve.ws_accept("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        )


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.srv = serve.Server(
            "127.0.0.1", 0, "sesame", "<html>page</html>", lambda: {"phase": "x"}
        )
        self.srv.start()
        self.cookie = "odbdebug%d=sesame" % self.srv.port

    def test_no_token_is_forbidden(self):
        r = http(self.srv.port, "GET / HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertTrue(r.startswith(b"HTTP/1.1 403"), r[:40])

    def test_a_wrong_token_is_forbidden(self):
        r = http(self.srv.port, "GET /?token=nope HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertTrue(r.startswith(b"HTTP/1.1 403"), r[:40])

    def test_the_token_is_traded_for_a_cookie(self):
        r = http(self.srv.port, "GET /?token=sesame HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertTrue(r.startswith(b"HTTP/1.1 302"), r[:40])
        self.assertIn(self.cookie.encode(), r)

    def test_the_cookie_gets_the_page(self):
        r = http(
            self.srv.port,
            "GET / HTTP/1.1\r\nHost: x\r\nCookie: %s\r\n\r\n" % self.cookie,
        )
        self.assertTrue(r.startswith(b"HTTP/1.1 200"), r[:40])
        self.assertTrue(r.endswith(b"<html>page</html>"))

    def test_a_state_request_and_a_push(self):
        s = socket.create_connection(("127.0.0.1", self.srv.port))
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall(
            (
                "GET / HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nCookie: %s\r\n\r\n"
                % (key, self.cookie)
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            head += s.recv(1)
        self.assertTrue(head.startswith(b"HTTP/1.1 101"), head)
        self.assertIn(serve.ws_accept(key).encode(), head)
        s.sendall(client_frame(serve.frame(5, serve.T_JSON, b'{"type": "state"}')))
        _, data = serve.ws_read(s)
        rid, kind, payload = serve.unframe(data)
        self.assertEqual((rid, kind), (5, serve.T_JSON))
        self.assertEqual(json.loads(payload.decode()), {"phase": "x", "type": "state"})
        self.srv.push()
        _, data = serve.ws_read(s)
        self.assertEqual(serve.unframe(data)[0], 0)
        s.sendall(client_frame(serve.frame(6, serve.T_JSON, b'{"type": "nope"}')))
        _, data = serve.ws_read(s)
        self.assertEqual(serve.unframe(data)[:2], (6, serve.T_ERROR))
        s.close()


class FakeClock(object):
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def handshake(port, cookie):
    s = socket.create_connection(("127.0.0.1", port))
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(
        (
            "GET / HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nCookie: %s\r\n\r\n"
            % (key, cookie)
        ).encode()
    )
    head = b""
    while b"\r\n\r\n" not in head:
        head += s.recv(1)
    return s


def wait_for(what, cond):
    """Waits for a thread of the server to act; asserts nothing about time."""
    for _ in range(500):
        if cond():
            return
        threading.Event().wait(0.01)
    raise AssertionError("never happened: " + what)


class HeartbeatTest(unittest.TestCase):
    """The browser may be on another machine: a page that went away is
    found by the heartbeat, not by a close frame."""

    def setUp(self):
        self.clock = FakeClock()
        self.logged = []
        self.srv = serve.Server(
            "127.0.0.1",
            0,
            "sesame",
            "",
            lambda: {},
            log=self.logged.append,
            clock=self.clock,
        )
        self.srv.start(heartbeat=False)
        self.cookie = "odbdebug%d=sesame" % self.srv.port

    def test_no_idle_time_before_the_first_browser(self):
        self.assertIsNone(self.srv.idle_for(self.clock()))

    def test_a_closed_page_starts_the_idle_time(self):
        s = handshake(self.srv.port, self.cookie)
        wait_for("the browser counted", lambda: self.srv.viewers() == 1)
        self.assertIsNone(self.srv.idle_for(self.clock()))
        mask = os.urandom(4)
        s.sendall(bytes([0x88, 0x80]) + mask)
        wait_for("the browser dropped", lambda: self.srv.viewers() == 0)
        self.clock.t += 42
        self.assertEqual(self.srv.idle_for(self.clock()), 42)
        self.assertIn("closed the page", self.logged[-1])
        s.close()

    def test_a_silent_browser_is_dropped(self):
        s = handshake(self.srv.port, self.cookie)
        wait_for("the browser counted", lambda: self.srv.viewers() == 1)
        self.clock.t += serve.Server.DEAD_AFTER - 1
        self.srv.sweep(self.clock())
        self.assertEqual(self.srv.viewers(), 1)
        self.clock.t += 2
        self.srv.sweep(self.clock())
        self.assertEqual(self.srv.viewers(), 0)
        self.assertIn("no reply", self.logged[-1])
        s.close()

    def test_a_browser_that_answers_pings_stays(self):
        s = handshake(self.srv.port, self.cookie)
        wait_for("the browser counted", lambda: self.srv.viewers() == 1)
        self.clock.t += serve.Server.DEAD_AFTER - 1
        self.srv.sweep(self.clock())
        opcode, _ = serve.ws_read(s)
        self.assertEqual(opcode, 0x9)
        mask = os.urandom(4)
        s.sendall(bytes([0x8A, 0x80]) + mask)
        b = list(self.srv.browsers.values())[0]
        wait_for("the pong seen", lambda: b.seen == self.clock.t)
        self.clock.t += serve.Server.DEAD_AFTER - 1
        self.srv.sweep(self.clock())
        self.assertEqual(self.srv.viewers(), 1)
        s.close()


class BrowserTest(unittest.TestCase):
    def test_only_the_latest_push_waits(self):
        b = serve.Browser("x", 0)
        b.send(b"old", push=True)
        b.send(b"reply")
        b.send(b"new", push=True)
        self.assertEqual(b.next(), b"reply")
        self.assertEqual(b.next(), b"new")
        b.close()
        self.assertIsNone(b.next())


if __name__ == "__main__":
    unittest.main()
