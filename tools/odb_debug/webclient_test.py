"""webclient against a fake web viewer, and the pin-access log parser."""

import base64
import hashlib
import json
import socket
import struct
import threading
import unittest

import odbdebug
import webclient


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


def reply(rid, kind, payload):
    return server_frame(struct.pack(">IB3x", rid, kind) + payload)


class FakeViewer(object):
    """Answers tcl_eval like OpenROAD's viewer. A command "pause N" pushes
    a log line and a debug_paused N times, each time waiting for the
    client's debug_continue, then replies."""

    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.received = []
        threading.Thread(target=self.serve, daemon=True).start()

    def recv_frame(self, conn):
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

    def serve(self):
        conn, _ = self.listener.accept()
        head = b""
        while b"\r\n\r\n" not in head:
            head += conn.recv(1)
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
                op, data = self.recv_frame(conn)
                if op == 0x8:
                    return
                if op != 0x1:
                    continue
                msg = json.loads(data.decode())
                self.received.append(msg)
                if msg["type"] != "tcl_eval":
                    continue
                cmd = msg["cmd"]
                if cmd.startswith("pause "):
                    for k in range(int(cmd.split()[1])):
                        push = {"type": "log", "text": "step %d\n" % k}
                        conn.sendall(reply(0, 0, json.dumps(push).encode()))
                        conn.sendall(
                            reply(0, 0, json.dumps({"type": "debug_paused"}).encode())
                        )
                        while True:
                            op, data = self.recv_frame(conn)
                            if op != 0x1:
                                continue
                            m = json.loads(data.decode())
                            self.received.append(m)
                            if m["type"] == "debug_continue":
                                break
                    body = {"result": "done", "is_error": False}
                elif cmd == "boom":
                    conn.sendall(reply(msg["id"], 2, b"no such request"))
                    continue
                else:
                    body = {"result": cmd.upper(), "is_error": False}
                # A long reply exercises the 16-bit length form.
                if cmd == "long":
                    body["result"] = "x" * 70000
                conn.sendall(reply(msg["id"], 0, json.dumps(body).encode()))
        except EOFError:
            return


class WebClientTest(unittest.TestCase):
    def test_tcl_round_trip(self):
        fake = FakeViewer()
        v = webclient.Viewer(fake.port, timeout=10)
        try:
            out = v.tcl("expr")
            self.assertEqual(out["result"], "EXPR")
            self.assertFalse(out["is_error"])
            self.assertEqual(out["pauses"], 0)
            self.assertEqual(len(v.tcl("long")["result"]), 70000)
        finally:
            v.close()

    def test_every_pause_is_continued_and_logged(self):
        fake = FakeViewer()
        v = webclient.Viewer(fake.port, timeout=10)
        try:
            out = v.tcl("pause 3")
        finally:
            v.close()
        self.assertEqual(out["result"], "done")
        self.assertEqual(out["pauses"], 3)
        self.assertEqual(out["log"], "step 0\nstep 1\nstep 2")
        kinds = [m["type"] for m in fake.received]
        self.assertEqual(kinds.count("debug_continue"), 3)

    def test_error_reply_raises(self):
        fake = FakeViewer()
        v = webclient.Viewer(fake.port, timeout=10)
        try:
            with self.assertRaises(webclient.WebError):
                v.tcl("boom")
        finally:
            v.close()

    def test_unreachable(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        with self.assertRaises(webclient.WebError):
            webclient.Viewer(port)


# What detailed_route_debug -pa -pa_markers logs, cut down from a real run
# on an asap7 block pin two wire widths wide.
PA_LOG = """[INFO DRT-4000] DEBUGGING inst u_blk term p36
[INFO DRT-0165] Start pin access.
[INFO DRT-0292] Marker frcLef58RectOnlyConstraint at (6480, 12502) (6498, 12538).
[INFO DRT-0292] Marker frcLef58RectOnlyConstraint at (6480, 12502) (6498, 12538).
[INFO DRT-0292] Marker frcLef58EolKeepOutConstraint at (6498, 12880) (6507, 12900).
Via VIA34 markers 2
[INFO DRT-0119] Marker (6411, 12528) (6509, 12552) on M4:
Short
[INFO DRT-0119] Marker (6471, 12520) (6489, 12541) on M3:
RECTONLY exceptNonCorePins false
Via VIA34 markers 0
Via VIA34 markers 1
[INFO DRT-0119] Marker (6480, 12880) (6498, 12884) on M3:
EOLKEEPOUT backwardExt 0 sideExt 13 forwardExt 31 eolWidth 25 cornerOnly true exceptWithin false withinLow 0 withinHigh 0
[ERROR DRT-0073] No access point for u_blk/p36 (BLK)."""


class ParsePaLogTest(unittest.TestCase):
    def test_groups_markers_by_constraint(self):
        s = odbdebug.parse_pa_log(PA_LOG)
        self.assertEqual(
            s["planar_markers"]["frcLef58RectOnlyConstraint"],
            {"count": 1, "boxes": [[6480, 12502, 6498, 12538]]},
        )
        self.assertEqual(
            s["planar_markers"]["frcLef58EolKeepOutConstraint"]["count"], 1
        )
        # The candidate with no markers was accepted, not rejected.
        self.assertEqual(s["via_candidates_rejected"], 2)
        self.assertEqual(
            sorted(s["via_markers"]),
            [
                "EOLKEEPOUT on M3",
                "RECTONLY exceptNonCorePins false on M3",
                "Short on M4",
            ],
        )
        self.assertTrue(s["no_access_point"])
        self.assertEqual(s["message_limit_hit"], [])

    def test_reports_the_logger_limit(self):
        crossing = PA_LOG + "\n[WARNING DRT-0119] message limit (1000) reached."
        self.assertEqual(
            odbdebug.parse_pa_log(crossing)["message_limit_hit"], ["DRT-0119"]
        )
        # After the limit: via candidates rejected with none of their markers.
        later = "Via VIA34 markers 3\nVia VIA34 markers 1"
        s = odbdebug.parse_pa_log(later)
        self.assertEqual(s["via_markers"], {})
        self.assertEqual(s["message_limit_hit"], ["DRT-0119"])


if __name__ == "__main__":
    unittest.main()
