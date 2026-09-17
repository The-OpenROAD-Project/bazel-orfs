#!/usr/bin/env python3
"""Client for an odb-debug daemon: a persistent OpenROAD session on a
stage ODB, answering Tcl over a localhost socket (see daemon.tcl).

Protocol, one request per line: the line is base64 of UTF-8 Tcl code,
evaluated at the daemon's global scope. The reply is one line of JSON:

    {"ok": true,  "result": "<string>", "stdout": "<string>", "ms": <int>}
    {"ok": false, "error":  "<message>", "stdout": "<string>", "ms": <int>}

`stdout` is whatever the code wrote with `puts`; `result` is the code's
own return value. The daemon's own procs (od_*) return JSON strings, so
`call()` decodes them.

Standard library only, Python 3.6 syntax: the MCP server imports this and
runs under whatever `python3` the host has.

Command line, for a quick look without the MCP server:

    python3 tools/odb_debug/odbdebug.py <ODB_DEBUG_DIR> 'od_status'
    python3 tools/odb_debug/odbdebug.py <ODB_DEBUG_DIR> --tcl 'puts [llength [[ord::get_db_block] getInsts]]'
"""

import base64
import json
import os
import socket
import sys

DEFAULT_TIMEOUT = float(os.environ.get("ODB_DEBUG_TIMEOUT", "600"))


class DaemonError(RuntimeError):
    """The daemon answered ok=false, or is not reachable."""


def info_path(odb_debug_dir=None):
    """daemon.json of the daemon serving `odb_debug_dir` (default: the
    ODB_DEBUG_DIR environment variable, then ./tmp/odb-debug)."""
    d = odb_debug_dir or os.environ.get("ODB_DEBUG_DIR", "tmp/odb-debug")
    return os.path.join(d, "daemon.json")


class Daemon(object):
    """One daemon, found through its daemon.json."""

    def __init__(self, odb_debug_dir=None):
        self.path = info_path(odb_debug_dir)
        self._info = None

    @property
    def info(self):
        """Contents of daemon.json: port, pid, dir, design, odb, workspace,
        commit, timing. Raises DaemonError when there is no daemon."""
        if self._info is None:
            try:
                with open(self.path) as f:
                    self._info = json.load(f)
            except (OSError, ValueError) as e:
                raise DaemonError(
                    "no daemon info at %s (%s); launch the daemon first, see "
                    "tools/odb_debug/README.md" % (self.path, e)
                )
        return self._info

    def request(self, code, timeout=DEFAULT_TIMEOUT):
        """Send Tcl `code`, return the decoded reply dict."""
        port = int(self.info["port"])
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        except OSError as e:
            self._info = None
            raise DaemonError(
                "daemon at 127.0.0.1:%d not reachable (%s); it may have exited "
                "on its idle timeout -- relaunch it" % (port, e)
            )
        try:
            s.sendall(base64.b64encode(code.encode("utf-8")) + b"\n")
            chunks = []
            while True:
                chunk = s.recv(1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
                if chunk.endswith(b"\n"):
                    break
        finally:
            s.close()
        raw = b"".join(chunks).decode("utf-8", "replace").strip()
        if not raw:
            raise DaemonError("empty reply from daemon")
        try:
            return json.loads(raw)
        except ValueError:
            raise DaemonError("malformed reply from daemon: %r" % raw[:200])

    def tcl(self, code, timeout=DEFAULT_TIMEOUT):
        """Evaluate Tcl; return its result string (stdout discarded)."""
        reply = self.request(code, timeout)
        if not reply.get("ok"):
            raise DaemonError(reply.get("error", "unknown daemon error"))
        return reply.get("result", "")

    def tcl_verbose(self, code, timeout=DEFAULT_TIMEOUT):
        """Evaluate Tcl; return (result, stdout)."""
        reply = self.request(code, timeout)
        if not reply.get("ok"):
            raise DaemonError(reply.get("error", "unknown daemon error"))
        return reply.get("result", ""), reply.get("stdout", "")

    def call(self, proc, *args, **kwargs):
        """Call a daemon proc that returns JSON; decode it."""
        timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
        code = " ".join([proc] + [tcl_quote(a) for a in args])
        text = self.tcl(code, timeout)
        try:
            return json.loads(text)
        except ValueError:
            raise DaemonError("%s returned non-JSON: %r" % (proc, text[:200]))

    # Typed conveniences over the daemon's procs.
    def status(self):
        return self.call("od_status")

    def macros(self):
        return self.call("od_macros")

    def cell_info(self, name):
        return self.call("od_cell", name)

    def net_info(self, name):
        return self.call("od_net", name)

    def check_placement(self):
        return self.call("od_check_placement", timeout=3600)

    def dump_geometry(self, out_dir, insts=True):
        return self.call(
            "od_dump", os.path.abspath(out_dir), 1 if insts else 0, timeout=3600
        )

    def wns(self):
        return self.call("od_wns", timeout=3600)

    def worst_paths(self, count=10):
        return self.call("od_worst_paths", int(count), timeout=3600)

    def report(self, command, timeout=3600):
        result, out = self.tcl_verbose("od_capture {%s}" % command, timeout)
        return out or result


def tcl_quote(value):
    """A Python value as one Tcl word."""
    s = str(value)
    return "{" + s + "}" if any(c in s for c in ' \t\n[]$\\"{}') else s


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    d = Daemon(argv[1])
    if argv[2] == "--tcl":
        result, out = d.tcl_verbose(" ".join(argv[3:]))
        if out:
            sys.stdout.write(out)
        print(result)
    else:
        print(json.dumps(d.call(*argv[2:]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
