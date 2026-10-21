"""The cut page's server: the viewer's framing, the token, the WebSocket."""

import base64
import json
import os
import socket
import struct
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


if __name__ == "__main__":
    unittest.main()
