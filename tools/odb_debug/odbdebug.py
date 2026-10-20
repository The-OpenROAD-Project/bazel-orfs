#!/usr/bin/env python3
"""Client for an odb-debug daemon: a persistent OpenROAD session on a
stage ODB, served by OpenROAD's web viewer on localhost (see daemon.tcl).

A request is base64 of UTF-8 Tcl code, sent as `od_web_request <base64>`
through the viewer's tcl_eval and evaluated at the daemon's global scope.
The reply is one JSON object:

    {"ok": true,  "result": "<string>", "stdout": "<string>", "ms": <int>}
    {"ok": false, "error":  "<message>", "stdout": "<string>", "ms": <int>}

`stdout` is whatever the code wrote with `puts`; `result` is the code's
own return value. The daemon's own procs (od_*) return JSON strings, so
`call()` decodes them. Every debug pause the code meets is continued
(webclient.py), and what the logger printed meanwhile is kept.

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
import subprocess
import sys
import time

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

    def exchange(self, code, timeout=DEFAULT_TIMEOUT):
        """Send Tcl `code`; return (reply dict, logger output, debug
        pauses continued)."""
        try:
            viewer = webclient.Viewer(self.info["port"], timeout=timeout)
        except webclient.WebError as e:
            self._info = None
            raise DaemonError(
                "%s (an idle daemon exits on its own, see ODB_DEBUG_IDLE_SECS)" % e
            )
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        try:
            out = viewer.tcl("od_web_request " + b64)
        except (webclient.WebError, OSError) as e:
            raise DaemonError(str(e))
        finally:
            viewer.close()
        if out["is_error"]:
            raise DaemonError(out["result"])
        try:
            reply = json.loads(out["result"])
        except ValueError:
            raise DaemonError("malformed reply: %r" % out["result"][:200])
        return reply, out["log"], out["pauses"]

    def request(self, code, timeout=DEFAULT_TIMEOUT):
        """Send Tcl `code`, return the decoded reply dict."""
        return self.exchange(code, timeout)[0]

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

    # Repair headroom (headroom.tcl): each measures a what-if and undoes
    # it; "restored" is the period measured again afterwards.
    def period(self, target=0):
        if target:
            return self.call("od_period", float(target), timeout=3600)
        return self.call("od_period", timeout=3600)

    def floor_wire(self):
        return self.call("od_floor_wire", timeout=7200)

    def floor_cycles(self, ends=0):
        return self.call("od_floor_cycles", int(ends), timeout=7200)

    def skew_headroom(self, ends=0, hold=True):
        return self.call("od_skew_headroom", int(ends), 1 if hold else 0, timeout=14400)

    def floor_retime(self, ends=0):
        return self.call("od_floor_retime", int(ends), timeout=14400)

    def vt_headroom(self, ends=0):
        return self.call("od_vt_headroom", int(ends), timeout=7200)

    def headroom(self, ends=0, target=0):
        if target:
            return self.call("od_headroom", int(ends), float(target), timeout=28800)
        return self.call("od_headroom", int(ends), timeout=28800)

    def report(self, command, timeout=3600):
        result, out = self.tcl_verbose("od_capture {%s}" % command, timeout)
        return out or result

    def pin_access(self, pin, timeout=3600):
        """Run pin_access under detailed_route_debug -pa -pa_markers for
        one pin ("inst:term", or "PIN:port" for a top-level port) and
        return why each access candidate of that pin was rejected.
        pin_access runs over the whole design: on a large one, ask a
        whittled copy."""
        code = (
            "detailed_route_debug -pa -pa_markers -pin %s\n"
            "set od_rc [catch {pin_access -verbose 1} od_msg]\n"
            "detailed_route_debug\n"
            "list $od_rc $od_msg"
        ) % tcl_quote(pin)
        reply, log, pauses = self.exchange(code, timeout)
        if not reply.get("ok"):
            raise DaemonError(reply.get("error", "unknown daemon error"))
        result = reply.get("result", "")
        summary = parse_pa_log(log)
        summary.update(
            pin=pin,
            pauses=pauses,
            error=result[2:] if result.startswith("1 ") else "",
            dbu_per_micron=int(
                self.tcl("[ord::get_db_tech] getDbUnitsPerMicron", timeout)
            ),
        )
        return summary

    def image(self, path, area=None, width=1024, options=None, timeout=600):
        """Render the design headless (save_image -web) to a PNG at
        `path`. area: [x0, y0, x1, y1] in um; options: {control: bool}
        display overrides, e.g. {"tracks_pref": True}."""
        path = os.path.abspath(path)
        # save_image -web logs WEB-0024 "Saved" and writes nothing when
        # the directory is missing, so make it, and check the file after.
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        words = ["save_image", "-web", "-width", str(int(width))]
        if area:
            words += ["-area", "{%s}" % " ".join(str(float(v)) for v in area)]
        for k, v in sorted((options or {}).items()):
            words += ["-display_option", "{%s %s}" % (k, "true" if v else "false")]
        self.tcl(" ".join(words + [tcl_quote(path)]), timeout)
        if not os.path.isfile(path):
            raise DaemonError("save_image -web wrote no file at %s" % path)
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


# The daemon a launch() started: written when bazelisk is spawned, read by
# gui_state() while the design loads and daemon.json does not exist yet.
LAUNCH_FILE = "launch.json"
LAUNCH_LOG = "launch.log"


def pid_alive(pid):
    """False once `pid` has exited; a zombie counts as exited."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError, ValueError):
        return False


def gui_bind(environ=None):
    """The address a browser on the human's machine reaches: the one
    their ssh session came in on, else None (the daemon's default)."""
    environ = os.environ if environ is None else environ
    if environ.get("ODB_DEBUG_GUI_BIND"):
        return environ["ODB_DEBUG_GUI_BIND"]
    fields = environ.get("SSH_CONNECTION", "").split()
    return fields[2] if len(fields) == 4 else None


def launch(target, odb_debug_dir, arguments=(), workspace=None, bazelisk="bazelisk"):
    """Start `bazelisk run <target>`, an odb_debug() daemon target, detached
    in a session of its own, so it outlives the agent session that asked
    for it; return at once. The design loads in the background:
    gui_state() says when the GUI is ready."""
    directory = os.path.abspath(odb_debug_dir)
    running = gui_state(directory)
    if running["state"] in ("loading", "ready"):
        raise DaemonError(
            "a daemon is already %s in %s (%s); stop it first with the tcl"
            " tool's `exit`, or use another ODB_DEBUG_DIR"
            % (
                running["state"],
                directory,
                running.get("target") or running.get("design"),
            )
        )
    if not os.path.isdir(directory):
        os.makedirs(directory)
    for stale in ("daemon.json", "daemon.json.pending"):
        try:
            os.remove(os.path.join(directory, stale))
        except OSError:
            pass
    make_args = ["ODB_DEBUG_DIR=" + directory]
    bind = gui_bind()
    if bind:
        make_args.append("ODB_DEBUG_GUI_BIND=" + bind)
    make_args += list(arguments)
    log_path = os.path.join(directory, LAUNCH_LOG)
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(
            [bazelisk, "run", target, "--"] + make_args,
            cwd=workspace or os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    record = {
        "pid": proc.pid,
        "target": target,
        "log": log_path,
        "started": int(time.time()),
    }
    with open(os.path.join(directory, LAUNCH_FILE), "w") as f:
        json.dump(record, f)
    return {"state": "loading", "target": target, "log": log_path}


def log_tail(path, lines=20):
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def gui_state(odb_debug_dir=None):
    """Where the daemon in `odb_debug_dir` is: "ready" with the GUI link,
    "loading" with the end of the launch log, or "stopped"."""
    directory = os.path.dirname(info_path(odb_debug_dir))
    try:
        with open(os.path.join(directory, "daemon.json")) as f:
            info = json.load(f)
    except (OSError, ValueError):
        info = None
    if info and pid_alive(info.get("pid", 0)):
        return {
            "state": "ready",
            "gui_url": info.get("gui_url", ""),
            "design": info.get("design", ""),
            "odb": info.get("odb", ""),
            "timing": info.get("timing"),
        }
    try:
        with open(os.path.join(directory, LAUNCH_FILE)) as f:
            record = json.load(f)
    except (OSError, ValueError):
        return {"state": "stopped"}
    state = "loading" if pid_alive(record.get("pid", 0)) else "stopped"
    return {
        "state": state,
        "target": record.get("target", ""),
        "log": record.get("log", ""),
        "log_tail": log_tail(record.get("log", "")),
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
