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
import re
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webclient  # noqa: E402

DEFAULT_TIMEOUT = float(os.environ.get("ODB_DEBUG_TIMEOUT", "600"))

# What detailed_route_debug -pa_markers logs for each candidate it rejects
# (FlexPA_graphics.cpp): a planar candidate's markers, and a via
# candidate's markers each followed by its constraint's own report line.
PLANAR_MARKER = re.compile(
    r"DRT-0292\] Marker (\S+) at \((-?\d+), (-?\d+)\) \((-?\d+), (-?\d+)\)"
)
VIA_HEADER = re.compile(r"^Via (\S+) markers (\d+)")
# OpenROAD's logger prints each message id at most 1000 times per process
# (utl::Logger::max_message_print) and says so once; after that the
# markers of that id are gone for the rest of the daemon's life.
MESSAGE_LIMIT = re.compile(r"(\w+-\d{4})\] message limit")
VIA_MARKER = re.compile(
    r"DRT-0119\] Marker \((-?\d+), (-?\d+)\) \((-?\d+), (-?\d+)\) on (\S+):"
)


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

    @property
    def web(self):
        """True when the daemon serves through OpenROAD's web viewer."""
        return self.info.get("backend") == "web"

    def web_eval(self, code, timeout=DEFAULT_TIMEOUT):
        """Evaluate Tcl through a web daemon's viewer, continuing every
        debug pause. Returns webclient.Viewer.tcl()'s dict."""
        if not self.web:
            raise DaemonError(
                "this needs a web daemon (ODB_DEBUG_BACKEND=web); %s serves "
                "the socket backend" % self.path
            )
        try:
            viewer = webclient.Viewer(self.info["port"], timeout=timeout)
        except webclient.WebError as e:
            self._info = None
            raise DaemonError(str(e))
        try:
            return viewer.tcl(code)
        except (webclient.WebError, OSError) as e:
            raise DaemonError(str(e))
        finally:
            viewer.close()

    def request(self, code, timeout=DEFAULT_TIMEOUT):
        """Send Tcl `code`, return the decoded reply dict."""
        if self.web:
            b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
            out = self.web_eval("od_web_request " + b64, timeout)
            if out["is_error"]:
                raise DaemonError(out["result"])
            try:
                return json.loads(out["result"])
            except ValueError:
                raise DaemonError("malformed reply: %r" % out["result"][:200])
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

    def check_setup(self, examples=10, depth=3, top=20, out=""):
        return self.call(
            "od_check_setup",
            int(examples),
            int(depth),
            int(top),
            os.path.abspath(out) if out else "",
            timeout=3600,
        )

    def report(self, command, timeout=3600):
        result, out = self.tcl_verbose("od_capture {%s}" % command, timeout)
        return out or result

    def pin_access(self, pin, timeout=3600):
        """Run pin_access under detailed_route_debug -pa -pa_markers for
        one pin ("inst:term", or "PIN:port" for a top-level port) and
        return why each access candidate of that pin was rejected.
        pin_access runs over the whole design: on a large one, ask a
        whittled copy. Web backend only."""
        code = (
            "detailed_route_debug -pa -pa_markers -pin %s\n"
            "set od_rc [catch {pin_access -verbose 1} od_msg]\n"
            "detailed_route_debug\n"
            "list $od_rc $od_msg"
        ) % tcl_quote(pin)
        out = self.web_eval(code, timeout)
        summary = parse_pa_log(out["log"])
        summary.update(
            pin=pin,
            pauses=out["pauses"],
            error=out["result"] if out["result"].startswith("1 ") else "",
            dbu_per_micron=int(
                self.tcl("[ord::get_db_tech] getDbUnitsPerMicron", timeout)
            ),
        )
        return summary

    def image(self, path, area=None, width=1024, options=None, timeout=600):
        """Render the design headless (save_image -web, either backend:
        it needs no running viewer) to a PNG at `path`. area: [x0, y0, x1, y1] in um; options: {control: bool}
        display overrides, e.g. {"tracks_pref": True}."""
        path = os.path.abspath(path)
        words = ["save_image", "-web", "-width", str(int(width))]
        if area:
            words += ["-area", "{%s}" % " ".join(str(float(v)) for v in area)]
        for k, v in sorted((options or {}).items()):
            words += ["-display_option", "{%s %s}" % (k, "true" if v else "false")]
        self.tcl(" ".join(words + [tcl_quote(path)]), timeout)
        return {"path": path, "bytes": os.path.getsize(path)}


def parse_pa_log(text):
    """Group what detailed_route_debug -pa_markers logged: distinct
    planar markers by constraint, via candidates and their markers by
    constraint report, and the message ids that hit the logger's limit
    (their markers are incomplete)."""
    planar, via, limited = {}, {}, []
    via_candidates = 0
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = MESSAGE_LIMIT.search(line)
        if m:
            limited.append(m.group(1))
            continue
        m = PLANAR_MARKER.search(line)
        if m:
            box = [int(v) for v in m.groups()[1:]]
            planar.setdefault(m.group(1), [])
            if box not in planar[m.group(1)]:
                planar[m.group(1)].append(box)
            continue
        m = VIA_HEADER.search(line)
        if m:
            via_candidates += int(m.group(2)) > 0
            continue
        m = VIA_MARKER.search(line)
        if m:
            what = lines[i + 1].strip() if i + 1 < len(lines) else ""
            # The constraint's own report: short ones whole ("RECTONLY
            # exceptNonCorePins false", "Spacing table PRL"), long ones by
            # their first word.
            what = what if len(what) <= 40 else what.split(" ")[0]
            key = "%s on %s" % (what or "?", m.group(5))
            box = [int(v) for v in m.groups()[:4]]
            via.setdefault(key, [])
            if box not in via[key]:
                via[key].append(box)
    # The limit notice prints once, on the run that crosses it; a later
    # run shows rejected via candidates with none of their markers.
    if via_candidates and not via and "DRT-0119" not in limited:
        limited.append("DRT-0119")
    return {
        "planar_markers": {
            k: {"count": len(v), "boxes": v[:4]} for k, v in planar.items()
        },
        "via_candidates_rejected": via_candidates,
        "via_markers": {k: {"count": len(v), "boxes": v[:4]} for k, v in via.items()},
        "no_access_point": "DRT-0073" in text,
        "message_limit_hit": limited,
    }


def tcl_quote(value):
    """A Python value as one Tcl word."""
    s = str(value)
    if not s:
        return "{}"
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
