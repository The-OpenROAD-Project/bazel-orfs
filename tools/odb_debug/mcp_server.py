#!/usr/bin/env python3
"""MCP server over an odb-debug daemon.

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

# name -> (description, {property: (type, description)}, required, handler)
TOOLS = []


def tool(name, description, params=None, required=()):
    def wrap(fn):
        TOOLS.append((name, description, params or {}, tuple(required), fn))
        return fn

    return wrap


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
        text = value if isinstance(value, str) else json.dumps(value, indent=1)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    return _error_result("unknown tool %r" % name)


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
