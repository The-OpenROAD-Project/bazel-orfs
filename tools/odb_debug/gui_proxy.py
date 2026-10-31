#!/usr/bin/env python3
"""The GUI link of an odb-debug daemon: a proxy that lets a browser on
another machine (over a VPN, say) reach the daemon's web viewer, which
listens on 127.0.0.1 only.

The viewer evaluates any Tcl it is sent and has no authentication, so
the proxy forwards a connection only when it carries the daemon's token:
in the link's query (`/?token=...`), answered with a cookie and a
redirect to the same page without it, or in that cookie on every later
request, the viewer's websocket included. Anything else gets a 403.

Every byte a browser sends counts as interaction: the proxy writes the
time to the activity file, which the daemon's watchdog reads for an idle exit.

daemon.tcl starts it beside the viewer; it exits when the daemon does.

    ODB_DEBUG_TOKEN=<token> gui_proxy.py --listen ADDR --port P \
        --target-port T --activity FILE --pid PID

The token comes through the environment, not argv, which every user on
the machine can read. Standard library only, Python 3.6 syntax.
"""

import argparse
import hmac
import os
import socket
import sys
import threading
import time

try:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
except ImportError:  # pragma: no cover - Python 2 is not supported
    raise

MAX_HEAD = 65536
HEAD_TIMEOUT = 30
# Seconds between writes of the activity file while bytes flow.
ACTIVITY_EVERY = 1.0


def cookie_name(port):
    """Cookies are per host, not per port: two daemons on one machine need
    a cookie each."""
    return "odbdebug%d" % port


def parse_head(head):
    """(method, target, {lower-case header: value}) of an HTTP request head."""
    lines = head.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3:
        raise ValueError("not an HTTP request line: %r" % lines[0][:80])
    headers = {}
    for line in lines[1:]:
        if not line:
            break
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return parts[0], parts[1], headers


def cookies(header):
    jar = {}
    for item in header.split(";"):
        name, sep, value = item.strip().partition("=")
        if sep:
            jar[name] = value
    return jar


def same(a, b):
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def decide(head, token, port):
    """What to do with a request: ("forward", None), ("redirect",
    response bytes) or ("deny", response bytes)."""
    try:
        _, target, headers = parse_head(head)
    except ValueError:
        return "deny", response(400, "Bad Request", "odb-debug: not HTTP\n")
    url = urlsplit(target)
    query = parse_qsl(url.query, keep_blank_values=True)
    given = [v for k, v in query if k == "token"]
    if given:
        if not same(given[-1], token):
            return "deny", forbidden()
        rest = urlencode([(k, v) for k, v in query if k != "token"])
        location = urlunsplit(("", "", url.path or "/", rest, ""))
        return "redirect", response(
            302,
            "Found",
            "",
            [
                ("Location", location),
                (
                    "Set-Cookie",
                    "%s=%s; HttpOnly; SameSite=Strict; Path=/"
                    % (cookie_name(port), token),
                ),
            ],
        )
    jar = cookies(headers.get("cookie", ""))
    if same(jar.get(cookie_name(port), ""), token):
        return "forward", None
    return "deny", forbidden()


def forbidden():
    return response(
        403,
        "Forbidden",
        "odb-debug: open the GUI through the link with its token, from the"
        " MCP server's gui tool or daemon.json's gui_url.\n",
    )


def response(code, reason, body, headers=()):
    data = body.encode("utf-8")
    lines = ["HTTP/1.1 %d %s" % (code, reason)]
    lines += ["%s: %s" % h for h in headers]
    lines += [
        "Content-Type: text/plain; charset=utf-8",
        "Content-Length: %d" % len(data),
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(lines).encode("latin-1") + data


class Activity(object):
    """The activity file, written at most once a second: `activity <epoch>`,
    replaced atomically so the watchdog never reads half a line."""

    def __init__(self, path):
        self.path = path
        self.last = 0.0
        self.lock = threading.Lock()

    def touch(self):
        now = time.time()
        with self.lock:
            if now - self.last < ACTIVITY_EVERY:
                return
            self.last = now
        tmp = "%s.%d.tmp" % (self.path, threading.get_ident())
        with open(tmp, "w") as f:
            f.write("activity %d\n" % int(now))
        os.rename(tmp, self.path)


def read_head(conn):
    data = b""
    conn.settimeout(HEAD_TIMEOUT)
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            raise ValueError("closed before the request head ended")
        data += chunk
        if len(data) > MAX_HEAD:
            raise ValueError("request head over %d bytes" % MAX_HEAD)
    conn.settimeout(None)
    return data


def pump(src, dst, on_data=None):
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                break
            if on_data:
                on_data()
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve_one(conn, args, token, activity):
    try:
        data = read_head(conn)
    except (ValueError, OSError):
        conn.close()
        return
    head = data[: data.index(b"\r\n\r\n") + 4]
    action, reply = decide(head, token, args.port)
    if action != "forward":
        try:
            conn.sendall(reply)
        except OSError:
            pass
        conn.close()
        return
    activity.touch()
    try:
        upstream = socket.create_connection(("127.0.0.1", args.target_port))
    except OSError:
        try:
            conn.sendall(
                response(502, "Bad Gateway", "odb-debug: the daemon is gone\n")
            )
        except OSError:
            pass
        conn.close()
        return
    upstream.sendall(data)
    t = threading.Thread(target=pump, args=(upstream, conn))
    t.daemon = True
    t.start()
    pump(conn, upstream, activity.touch)
    t.join()
    conn.close()
    upstream.close()


def alive(pid):
    """False once the daemon has exited, zombie included."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            # The state follows the parenthesised command name.
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--listen", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--activity", required=True)
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args(argv[1:])
    token = os.environ.get("ODB_DEBUG_TOKEN", "")
    if len(token) < 16:
        sys.stderr.write("gui_proxy: ODB_DEBUG_TOKEN missing or short\n")
        return 2

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((args.listen, args.port))
    listener.listen(64)
    activity = Activity(args.activity)

    def watch():
        while alive(args.pid):
            time.sleep(2)
        os._exit(0)

    w = threading.Thread(target=watch)
    w.daemon = True
    w.start()
    while True:
        conn, _ = listener.accept()
        t = threading.Thread(target=serve_one, args=(conn, args, token, activity))
        t.daemon = True
        t.start()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
