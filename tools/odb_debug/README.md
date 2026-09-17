# odb-debug: a persistent OpenROAD session you can ask questions

A stage of the flow ends in an ODB. Everything about where the flow left
the design is in that file: where the macros are, which cells the placer
left inside a macro footprint, how the free standard-cell sites are
distributed, what the worst path is. Reading it back costs a load of the
ODB and, for timing, the liberty set: seconds to minutes on a large
design, every time a script opens it to print one number.

odb-debug loads the design once, in the flow's own OpenROAD with the flow's
environment, and keeps it open behind a localhost socket. A person asks
through a small Python client, an agent through an MCP server that exposes
the daemon's procs as tools. Every question after the load is milliseconds.

```
                 bazelisk run //my:cpu_place_odb_debug  (or ./make run in a _deps tree)
                                     |
   agent --MCP stdio--> mcp_server.py --socket--> daemon.tcl in openroad, design loaded
   shell -------------> odbdebug.py  --socket-->     |
                                                     v
                        geometry.py <-- od_dump text files (offline forensics, pictures)
```

Three files do the work, and none needs anything beyond a stock `python3`:

| file | role |
|---|---|
| `daemon.tcl` | Runs inside openroad. Opens the stage through ORFS's `open.tcl`, defines the `od_*` procs, serves Tcl over a socket, writes `daemon.json`, exits when idle. |
| `odbdebug.py` | Client. `Daemon(dir).status()`, `.tcl(code)`, `.call(proc, ...)`; a CLI for one-off questions. |
| `mcp_server.py` | MCP server over the client: JSON-RPC 2.0 on stdio, one tool per proc plus `tcl` and `report`. |
| `geometry.py` | Placement forensics on an `od_dump` directory: free sites, cells inside macros, where the failed cells are. Optional `--png`. |

## Launch

### From a target

```starlark
load("@bazel-orfs//:openroad.bzl", "odb_debug")

odb_debug(
    name = "cpu_place_odb_debug",
    src = ":cpu_place",           # any stage with an ODB
)
```

```sh
bazelisk run //my:cpu_place_odb_debug -- ODB_DEBUG_DIR=$PWD/tmp/odb-debug GUI_TIMING=0
```

`bazelisk run` builds the stage first if it is out of date, then opens its
ODB with the stage's SDC, liberty set, RC and derates. Variables after `--`
are make overrides, so anything the flow reads can be set; the ones that
matter here:

| variable | meaning |
|---|---|
| `ODB_DEBUG_DIR` | Required. Where `daemon.json` goes. Absolute, so the client finds it from any directory. |
| `GUI_TIMING=0` | Skip the liberty files. Geometry queries work, timing queries report that no timing is loaded. A 1.35 M-instance ODB loads in seconds instead of minutes. |
| `ODB_DEBUG_IDLE_SECS` | Idle time before the daemon exits; default twice its load time and at least 120 s; `0` disables. |
| `ODB_DEBUG_PORT` | Fixed port instead of an ephemeral one. |
| `LOG_DIR` | Where make writes `run.log`; defaults inside the runfiles tree, pass an absolute path to keep it pristine. |

### From a deployed `_deps` tree

A stage that failed or was stopped has no finished ODB, but ORFS writes a
checkpoint per substep (`3_2_place_iop.odb`, `3_3_place_gp.odb`,
`3_4_place_resized.odb`, ...). Build the stage's `_deps` target, deploy it
(see `docs/orfs_run.md`), copy the checkpoint into its `results/`, and run
the daemon on it:

```sh
./make run RUN_SCRIPT=$PWD/tools/odb_debug/daemon.tcl \
    ODB_FILE=$PWD/results/3_4_place_resized.odb \
    ODB_DEBUG_DIR=$PWD/tmp/odb-debug GUI_TIMING=0
```

### From an open GUI

`source tools/odb_debug/daemon.tcl` in a GUI session attaches to the design
already loaded there; `ODB_DEBUG_DIR` must be set in the environment.

### `daemon.json`

Written when the socket is ready, removed when the daemon exits on its own:

```json
{"port":41123,"pid":12345,"dir":"...","design":"cpu","odb":".../3_place.odb",
 "workspace":"...","commit":"8dd2fb5...","timing":false}
```

Check `commit` against the tree you are studying. A daemon left over from
an earlier session serves a stale ODB without complaint.

## Ask

### Shell

```sh
python3 tools/odb_debug/odbdebug.py tmp/odb-debug od_status
python3 tools/odb_debug/odbdebug.py tmp/odb-debug od_macros
python3 tools/odb_debug/odbdebug.py tmp/odb-debug od_cell core/rob/u_buf_1234
python3 tools/odb_debug/odbdebug.py tmp/odb-debug od_dump $PWD/tmp/odb-debug/geom 1
python3 tools/odb_debug/odbdebug.py tmp/odb-debug --tcl 'report_checks -path_delay max -group_path_count 3'
```

The first form calls a proc that returns JSON and prints it decoded; the
`--tcl` form evaluates anything and prints its `puts` output, then its
result.

### Python

```python
from odbdebug import Daemon
d = Daemon("tmp/odb-debug")
d.status()["insts"]
d.cell_info("core/rob/u_buf_1234")["inside_macro"]
result, stdout = d.tcl_verbose("puts [llength [[ord::get_db_block] getInsts]]")
```

### MCP

`.mcp.json` at the workspace root registers the server for Claude Code:

```json
{"mcpServers": {"odb-debug": {
    "command": "python3",
    "args": ["tools/odb_debug/mcp_server.py"],
    "env": {"ODB_DEBUG_DIR": "tmp/odb-debug"}}}}
```

Any MCP host takes the same three lines. The server holds no state: each
call reads `daemon.json` and connects, so the daemon can be relaunched on
another ODB without restarting the agent. Tools:

| tool | answers |
|---|---|
| `status` | design, ODB, commit, timing on/off, counts, die and core in µm |
| `macros` | every macro instance with box, orientation, status |
| `cell_info name` | one instance: box, status, the macro whose footprint it is inside, if any |
| `net_info name` | driver, pin count, the box the pins span |
| `check_placement` | unplaced count, cells inside macros, `check_placement -verbose` text |
| `dump_geometry dir` | writes the text files `geometry.py` reads |
| `wns`, `worst_paths n` | worst slack and its endpoints; the n worst paths |
| `report cmd` | what any `report_*` command prints |
| `tcl code` | anything else: result and captured stdout |

## The daemon's procs

Every proc returns a JSON string; lengths are microns.

| proc | |
|---|---|
| `od_status` | as the `status` tool |
| `od_macros` | as `macros` |
| `od_cell name` | as `cell_info` |
| `od_net name` | as `net_info` |
| `od_check_placement` | as `check_placement` |
| `od_dump dir ?insts?` | `summary.txt`, `rows.txt`, `macros.txt`, `blockages.txt`, and with `insts` 1 (default) `insts.txt` |
| `od_wns`, `od_worst_paths ?n?` | need timing |
| `od_capture script` | run `script`, return its stdout as a plain string |

Add your own: `tcl` with a `proc od_mine {} { ... }` defines it for the
rest of the session, and `call("od_mine")` decodes what it returns.

## Placement forensics

A legaliser that fails or never finishes is asking a floorplan question.
`geometry.py` answers it from an `od_dump` directory, with no OpenROAD in
the loop:

```sh
python3 tools/odb_debug/geometry.py free   tmp/odb-debug/geom
python3 tools/odb_debug/geometry.py inside tmp/odb-debug/geom
grep -o 'instance [^ ]*' place.log | cut -d' ' -f2 > tmp/failed.txt
python3 tools/odb_debug/geometry.py failed tmp/odb-debug/geom tmp/failed.txt --png tmp/failed.png
```

- `free`: standard-cell site area, how it is spread over a 50 µm grid, and
  how much of it sits in row fragments under 20 µm wide: the slivers
  between abutting macros, which hold nothing but count as free area in a
  utilisation number.
- `inside`: logic cells whose centre global placement left inside a macro
  footprint, per macro. The legaliser must carry each one out.
- `failed`: given the instance names a legaliser reported, where they are:
  inside a macro, in a sliver, stacked on one coordinate, and how crowded
  their 10 µm neighbourhood is. Wire buffers in slivers say the channels
  are too narrow; cells in the open in a crowded square say the density is
  too high.

`--png` needs matplotlib and draws the free-site grid, the macro outlines
and the cells in question.

## Protocol

One request per line: base64 of UTF-8 Tcl, evaluated at global scope. One
JSON reply per line:

```
{"ok":true,"result":"<string>","stdout":"<string>","ms":<int>}
{"ok":false,"error":"<message>","stdout":"<string>","ms":<int>}
```

Base64 keeps newlines and braces out of the framing, so multi-line Tcl is
one request. The daemon listens on `127.0.0.1` only and has the trust model
of an interactive openroad shell on the same machine.

## Tests

`//tools/odb_debug:odbdebug_test` runs the client and the MCP server
against a fake daemon speaking the protocol; `:geometry_test` runs the
forensics on a hand-made dump; `//test/odb_debug:smoke_test` launches the
real daemon on a placed multiplier and asks it everything once.
