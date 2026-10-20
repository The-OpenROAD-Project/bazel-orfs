#!/usr/bin/env python3
"""MCP server over an odb-debug daemon (OpenROAD's web viewer on a
loaded design, see daemon.tcl).

Model Context Protocol, JSON-RPC 2.0 over stdio, one message per line.
Each tool is a thin wrapper over a daemon proc (daemon.tcl) through the
client in odbdebug.py, so an agent can ask a placed or routed design
questions -- which macros are where, is this instance inside a macro, what
does check_placement say, what is the worst path -- against a design that
stays loaded between questions.

Standard library only, Python 3.6 syntax: the agent host launches it with
whatever `python3` it has. Register it once (`.mcp.json` in the workspace
root does this for Claude Code):

    {"mcpServers": {"odb-debug": {
        "command": "python3",
        "args": ["tools/odb_debug/mcp_server.py"],
        "env": {"ODB_DEBUG_DIR": "tmp/odb-debug"}}}}

The server holds no state: every call reads daemon.json under
ODB_DEBUG_DIR and connects, so the daemon can be restarted on another ODB
without restarting the agent.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odbdebug  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"

# A reply is read into the agent's context. One report_checks or a tcl
# loop over a million instances would flood it, so a reply longer than
# this keeps its head and tail and says what was dropped.
MAX_TEXT = 16000

# name -> (description, {property: (type, description)}, required, handler)
TOOLS = []


def tool(name, description, params=None, required=()):
    def wrap(fn):
        TOOLS.append((name, description, params or {}, tuple(required), fn))
        return fn

    return wrap


GUI_HOW = (
    "Open gui_url in a browser on your own machine. It works over the VPN"
    " when the machine is reachable at that address; if the browser cannot"
    " connect, check that the VPN is up and nothing blocks the port, or"
    " tunnel it: ssh -L <port>:<address>:<port> <this machine>, then open"
    " the link with localhost:<port>. The token in the link is the only"
    " key to the session; do not paste it anywhere public."
)


@tool(
    "open",
    "Start the daemon on a flow stage in the background and return at once: `bazelisk run <target>` of an odb_debug() target, in a session of its own that outlives this one. The design loads while the human is away; it waits, without an idle exit, for the first question or browser visit. Poll `gui` for the link.",
    {
        "target": (
            "string",
            "Bazel label of an odb_debug() target, e.g. //my:cpu_final_odb_debug",
        ),
        "arguments": (
            "array",
            'Make variables for the daemon, e.g. ["GUI_TIMING=0"]; default none',
        ),
    },
    ["target"],
)
def _open(d, a):
    return odbdebug.launch(
        a["target"], os.path.dirname(d.path), a.get("arguments") or ()
    )


@tool(
    "gui",
    "Whether the daemon is loading, ready or stopped; when ready, the GUI link (gui_url, with its token) and how to open it; while loading or after a failed launch, the end of the launch log.",
)
def _gui(d, a):
    state = odbdebug.gui_state(os.path.dirname(d.path))
    if state["state"] == "ready":
        state["how"] = GUI_HOW
    return state


@tool(
    "status",
    "Design, ODB, workspace commit, whether timing is loaded, instance/net/row counts, die and core boxes in um.",
)
def _status(d, a):
    return d.status()


@tool(
    "macros",
    "Every macro instance: name, master, box [x0,y0,x1,y1] in um, orientation, placement status.",
)
def _macros(d, a):
    return d.macros()


@tool(
    "cell_info",
    "One instance: master, box in um, orientation, placement status, and the macro whose footprint its centre lies in, if any.",
    {"name": ("string", "Instance name (hierarchical, as in the netlist)")},
    ["name"],
)
def _cell(d, a):
    return d.cell_info(a["name"])


@tool(
    "net_info",
    "One net: driver pin, pin count, the box its pins span in um, and up to 64 pin names.",
    {"name": ("string", "Net name")},
    ["name"],
)
def _net(d, a):
    return d.net_info(a["name"])


@tool(
    "check_placement",
    "Placement legality: unplaced count, instances whose centre lies inside a macro, and the check_placement -verbose report.",
)
def _check(d, a):
    return d.check_placement()


@tool(
    "dump_geometry",
    "Write summary/rows/macros/blockages(/insts).txt to a directory for offline analysis with tools/odb_debug/geometry.py.",
    {
        "dir": (
            "string",
            "Output directory (created); relative paths resolve against the server's cwd",
        ),
        "insts": (
            "boolean",
            "Also write every non-macro instance (insts.txt); default true",
        ),
    },
    ["dir"],
)
def _dump(d, a):
    return d.dump_geometry(a["dir"], a.get("insts", True))


@tool(
    "wns",
    "Worst setup slack and its start/end points. Needs timing loaded (GUI_TIMING=1).",
)
def _wns(d, a):
    return d.wns()


@tool(
    "worst_paths",
    "The N worst setup paths: slack, startpoint, endpoint. Needs timing loaded.",
    {"count": ("integer", "How many paths; default 10")},
)
def _worst(d, a):
    return d.worst_paths(a.get("count", 10))


@tool(
    "check_setup",
    "check_setup -verbose, summarized: each warning (unclocked register pins, multiple clocks, unconstrained endpoints, loops, missing input/output delays, unconnected generated clocks) with its count, example pins and the instance prefixes they cluster in. Needs timing loaded.",
    {
        "examples": ("integer", "Example pins per warning; default 10"),
        "depth": ("integer", "Hierarchy levels in a prefix; default 3"),
        "top": ("integer", "Prefixes per warning, most common first; default 20"),
        "out": (
            "string",
            "File for every line of the verbose report, as the daemon sees paths; default none",
        ),
    },
)
def _check_setup(d, a):
    return d.check_setup(
        a.get("examples", 10), a.get("depth", 3), a.get("top", 20), a.get("out", "")
    )


ENDS = (
    "integer",
    "Scope: the cones of this many worst reg2reg endpoints; default 0, every endpoint. Limit it only when a very large design does not answer otherwise: skew needs the flops around the violations free to move",
)


@tool(
    "period",
    "The stage's reg2reg period (clock period minus the worst reg2reg slack over every endpoint), its violating reg2reg endpoints and their TNS. The measure the headroom tools compare against. Needs timing loaded.",
)
def _period(d, a):
    return d.period()


@tool(
    "floor_wire",
    "Zero-wire floor: the reg2reg period with every wire's R and C near zero (clock wires too), then the stage's RC put back. What any placement, buffering or reseating could at most win. Needs timing loaded.",
)
def _floor_wire(d, a):
    return d.floor_wire()


@tool(
    "floor_cycles",
    "One-flop-loop floor: the worst path from a flop back to itself among the flops of the worst paths. Neither useful skew nor retiming can go below it. Needs timing loaded.",
    {"ends": ENDS},
)
def _floor_cycles(d, a):
    return d.floor_cycles(a.get("ends", 0))


@tool(
    "skew_headroom",
    "Useful skew in timing only: the reg2reg period if each flop of the worst paths got the clock arrival that balances its paths in and out, hold kept, then removed. Not a clock tree anyone built. Needs timing loaded.",
    {"ends": ENDS, "hold": ("boolean", "Keep hold slack >= 0; default true")},
)
def _skew_headroom(d, a):
    return d.skew_headroom(a.get("ends", 0), a.get("hold", True))


@tool(
    "vt_headroom",
    "Threshold-voltage headroom: the reg2reg period with every data cell of the worst cones at the fastest VT the stage loaded, then put back. Reports which VTs the cones use; one VT loaded means nothing to swap to. Leakage is not measured. Needs timing loaded.",
    {"ends": ENDS},
)
def _vt_headroom(d, a):
    return d.vt_headroom(a.get("ends", 0))


@tool(
    "headroom",
    "All repair-headroom measurements on the loaded stage in one table: the period, the zero-wire and one-flop-loop floors, useful skew and VT, each with its gain in percent, and how each flow stage ended (setup WNS, TNS, violations from its metrics): a stage that met timing measures nothing. The stage alone: a block is its abstract; across blocks, use the stitched view (.claude/skills/repair-headroom). Minutes to hours on a large design. Needs timing loaded.",
    {"ends": ENDS},
)
def _headroom(d, a):
    return d.headroom(a.get("ends", 0))


@tool(
    "report",
    "Run an OpenROAD command and return what it printed: report_checks -path_delay max, report_design_area, report_wire_length ...",
    {"command": ("string", "The Tcl command line to run")},
    ["command"],
)
def _report(d, a):
    return d.report(a["command"])


@tool(
    "tcl",
    "Evaluate arbitrary Tcl in the OpenROAD session (odb API, sta, gpl/dpl/grt commands). Returns the result and captured stdout. The session has the trust model of an interactive openroad shell.",
    {"code": ("string", "Tcl code, evaluated at global scope")},
    ["code"],
)
def _tcl(d, a):
    result, out = d.tcl_verbose(a["code"])
    return {"result": result, "stdout": out}


@tool(
    "pin_access",
    "Why a pin has (or has no) access points: runs pin_access under detailed_route_debug -pa -pa_markers for that pin and returns the markers DRT logged for every rejected candidate, grouped by constraint (planar: frcLef58RectOnlyConstraint, frcLef58EolKeepOutConstraint ...; via: Short on M4, RECTONLY on M3 ...), boxes in DBU, and whether DRT-0073 was raised. pin_access runs over the whole design, so on a large one ask a whittled copy; the logger prints a message id at most 1000 times per process, see message_limit_hit.",
    {
        "pin": (
            "string",
            "inst:term, e.g. u_blk:din[0]; PIN:<port> for a top-level port",
        )
    },
    ["pin"],
)
def _pin_access(d, a):
    return d.pin_access(a["pin"])


@tool(
    "image",
    "Render the design headless to a PNG (save_image -web): an area in um, a width in pixels, display overrides (stdcells, macros, routing, special_nets, pins, blockages, tracks_pref, rudy ...). Returns the file's path; read it to look.",
    {
        "path": (
            "string",
            "Output PNG; relative paths resolve against the server's cwd",
        ),
        "area": ("array", "[x0, y0, x1, y1] in um; default the whole design"),
        "width": ("integer", "Image width in pixels; default 1024"),
        "options": ("object", 'Display overrides, e.g. {"tracks_pref": true}'),
    },
    ["path"],
)
def _image(d, a):
    return d.image(a["path"], a.get("area"), a.get("width", 1024), a.get("options"))


def tool_list():
    items = []
    for name, desc, params, required, _ in TOOLS:
        props = {}
        for p, (typ, pdesc) in params.items():
            props[p] = {"type": typ, "description": pdesc}
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = list(required)
        items.append({"name": name, "description": desc, "inputSchema": schema})
    return items


def call_tool(name, arguments, odb_debug_dir=None):
    """Run one tool; returns an MCP tools/call result dict."""
    for tname, _, _, required, fn in TOOLS:
        if tname != name:
            continue
        missing = [r for r in required if r not in arguments]
        if missing:
            return _error_result("missing argument(s): %s" % ", ".join(missing))
        try:
            value = fn(odbdebug.Daemon(odb_debug_dir), arguments)
        except odbdebug.DaemonError as e:
            return _error_result(str(e))
        except Exception as e:  # noqa: BLE001
            # Anything else a tool raises is a tool error too: escaping
            # serve() would end the server, and every tool with it, for
            # the rest of the agent's session.
            return _error_result("%s: %s" % (type(e).__name__, e))
        text = value if isinstance(value, str) else json.dumps(value, indent=1)
        return {"content": [{"type": "text", "text": cap(text)}], "isError": False}
    return _error_result("unknown tool %r" % name)


def cap(text, limit=MAX_TEXT):
    """text, or its head and tail on line boundaries with a note between."""
    if len(text) <= limit:
        return text
    half = limit // 2
    head = text[:half]
    head = head[: head.rfind("\n") + 1] or head
    tail = text[-half:]
    tail = tail[tail.find("\n") + 1 :] or tail
    dropped = text[len(head) : len(text) - len(tail)]
    return (
        "%s\n[odb-debug: %d of %d characters (%d lines) dropped; narrow the"
        " query, or redirect it to a file (report_checks ... > file) and read"
        " the part you need]\n\n%s"
        % (head, len(dropped), len(text), dropped.count("\n"), tail)
    )


def _error_result(message):
    return {"content": [{"type": "text", "text": message}], "isError": True}


def handle(message, odb_debug_dir=None):
    """One JSON-RPC request -> response dict, or None for a notification."""
    method = message.get("method", "")
    msg_id = message.get("id")
    params = message.get("params") or {}
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "odb-debug", "version": "1"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        result = call_tool(
            params.get("name", ""), params.get("arguments") or {}, odb_debug_dir
        )
    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": "method not found: %s" % method},
        }
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def serve(stdin, stdout, odb_debug_dir=None):
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            response = handle(message, odb_debug_dir)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def main(argv):
    odb_debug_dir = argv[1] if len(argv) > 1 else None
    serve(sys.stdin, sys.stdout, odb_debug_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
