#!/usr/bin/env python3
"""Client for OpenROAD's web viewer (`web_server`, `openroad -web`): the
websocket API the browser uses, driven from a script.

The protocol is the viewer's own (src/web in OpenROAD): requests are
text frames of JSON {"type": ..., "id": n, ...}; replies are binary
frames [4-byte id, big-endian][1-byte kind: 0 JSON, 1 PNG, 2 error]
[3 reserved][payload]. id 0 is a server push: {"type": "log", "text":
...} carries logger and puts output, {"type": "debug_paused"} says a
debug renderer (detailed_route_debug, global_placement_debug, ...) is
waiting for {"type": "debug_continue"}.

`tcl()` continues every pause it meets, so a command that pauses
hundreds of times (detailed_route_debug -pa -pa_markers) runs to the
end and its log carries what each stop printed. The server needs more
than one thread for that: under `-threads 1` a pause inside tcl_eval
holds the only thread that could deliver the continue.

Standard library only, Python 3.6 syntax: the MCP server imports this
and runs under whatever `python3` the host has.
"""

import base64
import json
import os
import socket
import struct

KIND_JSON, KIND_PNG, KIND_ERROR = 0, 1, 2


class WebError(RuntimeError):
    """The viewer is not reachable, closed the connection, or answered
    a request with an error."""


def frame(payload, opcode=0x1, mask=None):
    """A client-to-server websocket frame (always masked)."""
    mask = mask if mask is not None else os.urandom(4)
    n = len(payload)
    head = bytearray([0x80 | opcode])
    if n < 126:
        head.append(0x80 | n)
    elif n < 1 << 16:
        head.append(0x80 | 126)
        head += struct.pack(">H", n)
    else:
        head.append(0x80 | 127)
        head += struct.pack(">Q", n)
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(bytearray(payload)))
    return bytes(head) + mask + body


def parse_reply(data):
    """(id, kind, payload) of a binary reply frame's data."""
    if len(data) < 8:
        raise WebError("short reply frame (%d bytes)" % len(data))
    rid, kind = struct.unpack(">IB", data[:5])
    return rid, kind, data[8:]


class Connection(object):
    """One websocket connection to a viewer on 127.0.0.1."""

    def __init__(self, port, host="127.0.0.1", timeout=None):
        try:
            self.sock = socket.create_connection((host, int(port)), timeout=10)
        except OSError as e:
            raise WebError(
                "web viewer at %s:%s not reachable (%s); it may have exited "
                "-- relaunch it" % (host, port, e)
            )
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                "GET /ws HTTP/1.1\r\nHost: %s:%s\r\nUpgrade: websocket\r\n"
                "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n" % (host, port, key)
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            c = self.sock.recv(1)
            if not c:
                raise WebError("connection closed during the handshake")
            head += c
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise WebError("handshake refused: %r" % head.split(b"\r\n")[0])
        self.sock.settimeout(timeout)
        self.next_id = 1

    def close(self):
        try:
            self.sock.sendall(frame(b"", opcode=0x8))
        except OSError:
            pass
        self.sock.close()

    def _recvn(self, n):
        out = b""
        while len(out) < n:
            c = self.sock.recv(n - len(out))
            if not c:
                raise WebError("web viewer closed the connection")
            out += c
        return out

    def recv_message(self):
        """(opcode, payload) of the next data message, answering pings."""
        data, opcode = b"", None
        while True:
            b0, b1 = bytearray(self._recvn(2))
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recvn(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recvn(8))[0]
            if b1 & 0x80:  # a server must not mask, but tolerate it
                m = self._recvn(4)
                raw = bytearray(self._recvn(n))
                payload = bytes(b ^ m[i % 4] for i, b in enumerate(raw))
            else:
                payload = self._recvn(n)
            if op == 0x9:
                self.sock.sendall(frame(payload, opcode=0xA))
                continue
            if op == 0xA:
                continue
            if op == 0x8:
                raise WebError("web viewer closed the connection")
            if op != 0x0:
                opcode = op
            data += payload
            if b0 & 0x80:
                return opcode, data

    def send(self, obj):
        """Send a request; return its id."""
        obj = dict(obj, id=self.next_id)
        self.next_id += 1
        self.sock.sendall(frame(json.dumps(obj).encode("utf-8")))
        return obj["id"]


class Viewer(object):
    """A web viewer serving a loaded design."""

    def __init__(self, port, timeout=None):
        self.conn = Connection(port, timeout=timeout)

    def close(self):
        self.conn.close()

    def request(self, obj, on_push=None):
        """Send one request and wait for its reply, handing every push
        that arrives meanwhile to on_push. Returns (kind, payload)."""
        rid = self.conn.send(obj)
        while True:
            opcode, data = self.conn.recv_message()
            if opcode != 0x2:
                continue
            i, kind, payload = parse_reply(data)
            if i == rid:
                if kind == KIND_ERROR:
                    raise WebError(payload.decode("utf-8", "replace"))
                return kind, payload
            if i == 0 and kind == KIND_JSON and on_push is not None:
                try:
                    on_push(json.loads(payload.decode("utf-8")))
                except ValueError:
                    pass

    def tcl(self, code):
        """Evaluate Tcl in the viewer's interpreter. Returns a dict:
        result, is_error, log (logger and puts output while it ran) and
        pauses (debug pauses it continued)."""
        log, pauses = [], [0]

        def push(msg):
            if msg.get("type") == "log":
                log.append(msg.get("text", ""))
            elif msg.get("type") == "debug_paused":
                pauses[0] += 1
                self.conn.send({"type": "debug_continue"})

        kind, payload = self.request({"type": "tcl_eval", "cmd": code}, push)
        reply = json.loads(payload.decode("utf-8")) if kind == KIND_JSON else {}
        text = "\n".join(t.rstrip("\n") for t in log if t)
        return {
            "result": reply.get("result", ""),
            "is_error": bool(reply.get("is_error")),
            "log": text,
            "pauses": pauses[0],
        }
