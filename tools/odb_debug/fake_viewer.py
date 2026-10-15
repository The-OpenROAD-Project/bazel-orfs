"""A stand-in for OpenROAD's web viewer, for tests: the websocket
handshake, the binary reply frames, log and debug_paused pushes, and
debug_continue, with tcl_eval answered by a Python function.

handler(cmd) returns a dict: "result" (string), optionally "is_error",
"log" (lines pushed before the reply), "pauses" (debug pauses to push,
each waiting for the client's debug_continue) and "error" (answer with an
error frame instead of a reply).
"""

import base64
import hashlib
import json
import socket
import struct
import threading

KIND_JSON, KIND_ERROR = 0, 2


def server_frame(payload, opcode=0x2):
    n = len(payload)
    head = bytearray([0x80 | opcode])
    if n < 126:
        head.append(n)
    elif n < 1 << 16:
        head.append(126)
        head += struct.pack(">H", n)
    else:
        head.append(127)
        head += struct.pack(">Q", n)
    return bytes(head) + payload


def reply_frame(rid, kind, payload):
    return server_frame(struct.pack(">IB3x", rid, kind) + payload)


def push_frame(msg):
    return reply_frame(0, KIND_JSON, json.dumps(msg).encode("utf-8"))


class FakeViewer(object):
    def __init__(self, handler):
        self.handler = handler
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.port = self.listener.getsockname()[1]
        self.received = []
        t = threading.Thread(target=self.accept_loop)
        t.daemon = True
        t.start()

    def close(self):
        self.listener.close()

    def accept_loop(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            t = threading.Thread(target=self.serve, args=(conn,))
            t.daemon = True
            t.start()

    @staticmethod
    def recv_frame(conn):
        def n(k):
            b = b""
            while len(b) < k:
                c = conn.recv(k - len(b))
                if not c:
                    raise EOFError
                b += c
            return b

        b0, b1 = bytearray(n(2))
        size = b1 & 0x7F
        if size == 126:
            size = struct.unpack(">H", n(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", n(8))[0]
        assert b1 & 0x80, "client frames must be masked"
        mask = n(4)
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(bytearray(n(size))))
        return b0 & 0x0F, data

    def next_message(self, conn):
        while True:
            op, data = self.recv_frame(conn)
            if op == 0x8:
                raise EOFError
            if op == 0x1:
                msg = json.loads(data.decode("utf-8"))
                self.received.append(msg)
                return msg

    def serve(self, conn):
        head = b""
        while b"\r\n\r\n" not in head:
            c = conn.recv(1)
            if not c:
                return
            head += c
        key = [
            line.split(b": ")[1]
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"sec-websocket-key")
        ][0]
        accept = base64.b64encode(
            hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
        )
        conn.sendall(
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n"
        )
        # A ping first: the client must answer it and carry on.
        conn.sendall(server_frame(b"hi", opcode=0x9))
        try:
            while True:
                msg = self.next_message(conn)
                if msg["type"] != "tcl_eval":
                    continue
                out = self.handler(msg["cmd"])
                if "error" in out:
                    conn.sendall(
                        reply_frame(msg["id"], KIND_ERROR, out["error"].encode())
                    )
                    continue
                for line in out.get("log", []):
                    conn.sendall(push_frame({"type": "log", "text": line + "\n"}))
                for _ in range(out.get("pauses", 0)):
                    conn.sendall(push_frame({"type": "debug_paused"}))
                    while self.next_message(conn)["type"] != "debug_continue":
                        pass
                body = {
                    "result": out.get("result", ""),
                    "is_error": bool(out.get("is_error")),
                }
                conn.sendall(
                    reply_frame(msg["id"], KIND_JSON, json.dumps(body).encode())
                )
        except EOFError:
            pass
        finally:
            conn.close()
