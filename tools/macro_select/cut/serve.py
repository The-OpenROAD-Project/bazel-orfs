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
import time

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


class Browser(object):
    """A connected page: where from, since when, last heard from, and what
    is waiting to go to it. Its own writer thread sends, so a page that
    stopped reading blocks nobody else; of the state pushes only the
    latest waits, the others are stale."""

    def __init__(self, peer, now):
        self.peer = peer
        self.since = now
        self.seen = now
        self.cond = threading.Condition()
        self.out = []
        self.latest = None
        self.closed = False

    def send(self, data, push=False):
        with self.cond:
            if push:
                self.latest = data
            else:
                self.out.append(data)
            self.cond.notify()

    def next(self):
        """The next message to send, None once closed."""
        with self.cond:
            while not self.out and self.latest is None and not self.closed:
                self.cond.wait()
            if self.closed:
                return None
            if self.out:
                return self.out.pop(0)
            data, self.latest = self.latest, None
            return data

    def close(self):
        with self.cond:
            self.closed = True
            self.cond.notify()


class Server(object):
    """Serves page_html and pushes state() to every WebSocket client.

    The browser may be on another machine, behind a VPN that drops, on a
    laptop whose lid closes: a page that goes away may never send a close
    frame or even a TCP FIN. So the server pings every browser every
    PING_EVERY seconds, counts any frame back (a pong among them) as
    alive, and drops one silent for DEAD_AFTER seconds. idle_for() says
    how long no browser has been connected, once one has been."""

    PING_EVERY = 10.0
    DEAD_AFTER = 30.0

    def __init__(
        self, bind, port, token, page_html, state, log=None, clock=time.monotonic
    ):
        self.token = token
        self.page = page_html
        self.state = state
        self.log = log or (lambda msg: None)
        self.clock = clock
        self.browsers = {}  # socket -> Browser
        self.ever = False
        self.left_at = None
        self.lock = threading.RLock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind, port))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]

    def start(self, heartbeat=True):
        t = threading.Thread(target=self._accept)
        t.daemon = True
        t.start()
        if heartbeat:
            t = threading.Thread(target=self._heartbeat)
            t.daemon = True
            t.start()

    def _accept(self):
        while True:
            conn, addr = self.sock.accept()
            t = threading.Thread(target=self._serve, args=(conn, addr[0]))
            t.daemon = True
            t.start()

    def _heartbeat(self):
        while True:
            time.sleep(self.PING_EVERY)
            self.sweep(self.clock())

    def sweep(self, now):
        """Drop every browser silent for DEAD_AFTER, ping the rest."""
        with self.lock:
            browsers = list(self.browsers.items())
        for conn, b in browsers:
            if now - b.seen > self.DEAD_AFTER:
                self._drop(conn, "no reply for %.0f s" % (now - b.seen))
            else:
                b.send(ws_encode(b"", 0x9))

    def viewers(self):
        with self.lock:
            return len(self.browsers)

    def idle_for(self, now):
        """Seconds since the last browser left; None before the first one
        came, or while one is connected."""
        with self.lock:
            if not self.ever or self.browsers:
                return None
            return now - self.left_at

    def _drop(self, conn, why):
        with self.lock:
            b = self.browsers.pop(conn, None)
            if b is None:
                return
            if not self.browsers:
                self.left_at = self.clock()
        b.close()
        self.log(
            "browser %s left after %.0f s (%s); %d still connected"
            % (b.peer, self.clock() - b.since, why, self.viewers())
        )
        try:
            # wakes the reader blocked on this socket
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _serve(self, conn, peer):
        why = "connection lost"
        try:
            # a client sends nothing past the head before the 101
            head = gui_proxy.read_head(conn)
            what, reply = gui_proxy.decide(head, self.token, self.port)
            if what != "forward":
                conn.sendall(reply)
                return
            _, target, headers = gui_proxy.parse_head(head)
            if headers.get("upgrade", "").lower() == "websocket":
                why = self._websocket(conn, peer, headers)
                return
            if target.split("?")[0] != "/":
                conn.sendall(gui_proxy.response(404, "Not Found", "not found\n"))
                return
            conn.sendall(page_response(self.page))
        except (OSError, EOFError, ValueError):
            pass
        finally:
            self._drop(conn, why)
            conn.close()

    def _websocket(self, conn, peer, headers):
        conn.sendall(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Accept: %s\r\n\r\n"
                % ws_accept(headers["sec-websocket-key"])
            ).encode("latin-1")
        )
        conn.settimeout(None)
        b = Browser(peer, self.clock())
        with self.lock:
            self.browsers[conn] = b
            self.ever = True
        t = threading.Thread(target=self._writer, args=(conn, b))
        t.daemon = True
        t.start()
        self.log("browser %s connected; %d connected" % (peer, self.viewers()))
        while True:
            opcode, data = ws_read(conn)
            b.seen = self.clock()
            if opcode == 0x8:
                return "closed the page"
            if opcode == 0x9:
                b.send(ws_encode(data, 0xA))
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
            b.send(ws_encode(out))

    def _state_json(self):
        s = dict(self.state())
        s["type"] = "state"
        return json.dumps(s).encode("utf-8")

    def _writer(self, conn, b):
        while True:
            data = b.next()
            if data is None:
                return
            try:
                conn.sendall(data)
            except OSError:
                self._drop(conn, "send failed")
                return

    def push(self):
        """The state to every client, id 0. Never blocks on a client."""
        data = ws_encode(frame(0, T_JSON, self._state_json()))
        with self.lock:
            browsers = list(self.browsers.values())
        for b in browsers:
            b.send(data, push=True)
