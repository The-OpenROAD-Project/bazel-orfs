"""The cut search's web page: HTTP for the page, a WebSocket for the state.

Shaped like OpenROAD's web viewer (src/web/docs/server-api.md): one port,
the page at /, the WebSocket upgrade at /, every message a binary frame
of a big-endian uint32 request id, a type byte (0 JSON, 2 error), three
reserved bytes and the payload. Requests: {"type": "state"}. Pushes, id
0: {"type": "state", ...} whenever the search's state changes.

The page shows a search that runs commands on this machine's files, so
it is gated as the odb-debug GUI link is (gui_proxy.decide): the link's
token is traded for a cookie, and anything without it gets a 403.
Standard library only.
"""

import base64
import hashlib
import json
import socket
import struct
import threading

import gui_proxy

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

T_JSON = 0
T_ERROR = 2


def frame(req_id, kind, payload):
    """The viewer's message: id, type, three reserved bytes, payload."""
    return struct.pack(">IB3x", req_id, kind) + payload


def unframe(data):
    """(id, type, payload) of a viewer message."""
    if len(data) < 8:
        raise ValueError("a frame is at least 8 bytes, got %d" % len(data))
    req_id, kind = struct.unpack(">IB3x", data[:8])
    return req_id, kind, data[8:]


def ws_accept(key):
    digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def ws_encode(payload, opcode=0x2):
    """A server-to-client WebSocket frame (unmasked)."""
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([n])
    elif n < 1 << 16:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise EOFError
        buf += chunk
    return buf


def ws_read(conn):
    """(opcode, payload) of one client frame (masked, as clients must)."""
    b0, b1 = recv_exact(conn, 2)
    opcode = b0 & 0x0F
    n = b1 & 0x7F
    if n == 126:
        (n,) = struct.unpack(">H", recv_exact(conn, 2))
    elif n == 127:
        (n,) = struct.unpack(">Q", recv_exact(conn, 8))
    mask = recv_exact(conn, 4) if b1 & 0x80 else b"\0\0\0\0"
    data = bytearray(recv_exact(conn, n))
    for i in range(n):
        data[i] ^= mask[i % 4]
    return opcode, bytes(data)


def page_response(body):
    data = body.encode("utf-8")
    head = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Cache-Control: no-store\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n\r\n" % len(data)
    )
    return head.encode("latin-1") + data


class Server(object):
    """Serves page_html and pushes state() to every WebSocket client."""

    def __init__(self, bind, port, token, page_html, state):
        self.token = token
        self.page = page_html
        self.state = state
        self.clients = []
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind, port))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]

    def start(self):
        t = threading.Thread(target=self._accept)
        t.daemon = True
        t.start()

    def _accept(self):
        while True:
            conn, _ = self.sock.accept()
            t = threading.Thread(target=self._serve, args=(conn,))
            t.daemon = True
            t.start()

    def _serve(self, conn):
        try:
            # a client sends nothing past the head before the 101
            head = gui_proxy.read_head(conn)
            what, reply = gui_proxy.decide(head, self.token, self.port)
            if what != "forward":
                conn.sendall(reply)
                return
            _, target, headers = gui_proxy.parse_head(head)
            if headers.get("upgrade", "").lower() == "websocket":
                self._websocket(conn, headers)
                return
            if target.split("?")[0] != "/":
                conn.sendall(gui_proxy.response(404, "Not Found", "not found\n"))
                return
            conn.sendall(page_response(self.page))
        except (OSError, EOFError, ValueError):
            pass
        finally:
            with self.lock:
                if conn in self.clients:
                    self.clients.remove(conn)
            conn.close()

    def _websocket(self, conn, headers):
        conn.sendall(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Accept: %s\r\n\r\n"
                % ws_accept(headers["sec-websocket-key"])
            ).encode("latin-1")
        )
        conn.settimeout(None)
        with self.lock:
            self.clients.append(conn)
        while True:
            opcode, data = ws_read(conn)
            if opcode == 0x8:
                return
            if opcode == 0x9:
                self._send(conn, ws_encode(data, 0xA))
                continue
            if opcode != 0x2:
                continue
            req_id, _, payload = unframe(data)
            try:
                req = json.loads(payload.decode("utf-8"))
                if req.get("type") != "state":
                    raise ValueError("unknown request %r" % req.get("type"))
                out = frame(req_id, T_JSON, self._state_json())
            except ValueError as e:
                out = frame(req_id, T_ERROR, str(e).encode("utf-8"))
            self._send(conn, ws_encode(out))

    def _state_json(self):
        s = dict(self.state())
        s["type"] = "state"
        return json.dumps(s).encode("utf-8")

    def _send(self, conn, data):
        with self.lock:
            try:
                conn.sendall(data)
            except OSError:
                if conn in self.clients:
                    self.clients.remove(conn)

    def push(self):
        """The state to every client, id 0."""
        data = ws_encode(frame(0, T_JSON, self._state_json()))
        with self.lock:
            clients = list(self.clients)
        for c in clients:
            self._send(c, data)
