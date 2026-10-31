# odb-debug: a persistent OpenROAD session you can ask questions

A stage of the flow ends in an ODB. Everything about where the flow left
the design is in that file: where the macros are, which cells the placer
left inside a macro footprint, how the free standard-cell sites are
distributed, what the worst path is. Reading it back costs a load of the
ODB and, for timing, the liberty set: seconds to minutes on a large
design, every time a script opens it to print one number.

odb-debug loads the design once, in the flow's own OpenROAD with the flow's
environment, and serves it through OpenROAD's web viewer on localhost. A
person asks through a small Python client or looks in a browser, an agent
asks through an MCP server that exposes the daemon's procs as tools. Every
question after the load is milliseconds, and the viewer brings what a
plain session lacks: debug renderers that can be stepped from a script and
headless pictures.

```
     bazelisk run @bazel-orfs//:odb_debug -- //my:cpu_place  (or ./make run in a //:dirty tree)
                                     |
   agent --MCP stdio--> mcp_server.py --websocket--> daemon.tcl in openroad (web_server)
   shell -------------> odbdebug.py  --websocket-->     |
   browser ------------------------- http://127.0.0.1:<port> --^
                                                     v
                        geometry.py <-- od_dump text files (offline forensics, pictures)
```

These files do the work, and none needs anything beyond a stock `python3`:

| file | role |
|---|---|
| `daemon.tcl` | Runs inside openroad. Opens the stage through ORFS's `open.tcl`, defines the `od_*` procs, serves them through `web_server`, writes `daemon.json`, exits when idle. |
| `webclient.py` | The web viewer's websocket protocol, from a script: `tcl_eval`, log pushes, and a Continue for every debug pause. |
| `odbdebug.py` | Client. `Daemon(dir).status()`, `.tcl(code)`, `.call(proc, ...)`, `.pin_access(pin)`, `.image(path, ...)`; a CLI for one-off questions. |
| `mcp_server.py` | MCP server over the client: JSON-RPC 2.0 on stdio, one tool per proc plus `tcl` and `report`, and `open`/`gui` to start a daemon and hand over its GUI. |
| `gui_proxy.py` | The GUI link: lets a browser on another machine reach the viewer, only with the daemon's token, and records its activity for the idle exit. |
| `geometry.py` | Placement forensics on an `od_dump` directory: free sites, cells inside macros, where the failed cells are. Optional `--png`. |

## Launch

### From a stage target

```sh
bazelisk run @bazel-orfs//:odb_debug -- //my:cpu_place GUI_TIMING=0
```

starts the daemon on any flow stage target (`<module>_<stage>`, through
the stage's `gui_<stage>`, below) in a session of its own, waits until it
is ready and prints the GUI link. Nothing is added to a BUILD file. The
daemon directory is `$ODB_DEBUG_DIR`, by default the workspace's
`tmp/odb-debug`, where the MCP server looks; the MCP `open` tool does the
same without waiting.

An `odb_debug()` target is the same daemon with its make variables fixed
in a BUILD file, for a stage opened often with the same ones:

```starlark
load("@bazel-orfs//:openroad.bzl", "odb_debug")

odb_debug(
    name = "cpu_place_odb_debug",
    src = ":cpu_place",           # any stage with an ODB
)
```

```sh
bazelisk run //my:cpu_place_odb_debug -- ODB_DEBUG_DIR=tmp/odb-debug GUI_TIMING=0
```

`bazelisk run` builds the stage first if it is out of date, then opens its
ODB with the stage's SDC, liberty set, RC and derates. Variables after `--`
are make overrides, so anything the flow reads can be set; the ones that
matter here:

| variable | meaning |
|---|---|
| `ODB_DEBUG_DIR` | Required. Where `daemon.json` goes. Absolute, so the client finds it from any directory. |
| `GUI_TIMING=0` | Skip the liberty files. Geometry queries work, timing queries report that no timing is loaded. A 1.35 M-instance ODB loads in seconds instead of minutes. |
| `ODB_DEBUG_IDLE_SECS` | Idle time before the daemon exits, counted from the first interaction (a loaded daemon waits for that without a limit); default twice its load time and at least 120 s; `0` disables. |
| `ODB_DEBUG_PORT` | Fixed port instead of an ephemeral one. |
| `ODB_DEBUG_GUI_BIND` | Address the GUI link listens on; default the one the ssh session came in on (`SSH_CONNECTION`), else 127.0.0.1. Read from the environment too: on a machine reached over a VPN from sessions that are not ssh, export it once in the shell profile. |
| `ODB_DEBUG_GUI_PORT` | Fixed GUI port instead of an ephemeral one. |
| `LOG_DIR` | Where make writes `run.log`; defaults inside the runfiles tree, pass an absolute path to keep it pristine. |

### As the GUI: `gui_<stage>`

ORFS's `gui_<stage>` make target is the web viewer (carried patch 0139;
`qt_<stage>`, the Qt GUI, bazel-orfs refuses), and bazel-orfs runs it as this daemon,
through `gui.sh`, with no `odb_debug()` target:

```sh
bazelisk run //my:cpu_final gui_final          # any stage target
tmp/my/cpu/make gui_final                      # a //:dirty tree
```

It prints the GUI link and holds the terminal; Ctrl-C ends it. Its
`ODB_DEBUG_DIR` is the workspace's `tmp/odb-debug`, where the MCP server
looks, so the agent asks the session the human is looking at.

### From a tree deployed by `//:dirty`

A stage that failed or was stopped has no finished ODB, but ORFS writes a
checkpoint per substep (`3_2_place_iop.odb`, `3_3_place_gp.odb`,
`3_4_place_resized.odb`, ...). Deploy the stage with
`bazelisk run //:dirty -- start <flow> <stage>` (see `docs/dirty-lane.md`), copy the checkpoint into its `results/`, and run
the daemon on it:

```sh
./make run RUN_SCRIPT=$PWD/tools/odb_debug/daemon.tcl \
    ODB_FILE=$PWD/results/3_4_place_resized.odb \
    ODB_DEBUG_DIR=$PWD/tmp/odb-debug GUI_TIMING=0
```

### Look at it

The daemon is a web viewer: open `gui_url` from `daemon.json` (or the MCP
`gui` tool) in a browser for the GUI, on the same loaded design the client
asks. It works from another machine, over a VPN for one:

- The link goes through `gui_proxy.py`, which listens on
  `ODB_DEBUG_GUI_BIND`. That is by default the address the ssh session
  that started the daemon came in on, the one the human's machine
  reaches; without ssh it is 127.0.0.1.
- The viewer evaluates any Tcl it is sent and has no authentication, so
  the proxy forwards only what carries the link's token. The link's
  token turns into a cookie for the rest of the visit. `daemon.json` is
  readable by its owner only.
- Every byte the browser sends through it counts as interaction for the
  idle exit. The viewer's own `url`, on 127.0.0.1, works on the machine
  itself, but there the browser does not count, so browse through
  `gui_url` or with `ODB_DEBUG_IDLE_SECS=0`.

A loaded daemon waits for its first question or browser visit with no
idle exit, so a design started after a build is still there when the
human comes to look; the `warm-gui` skill does that. The MCP `open` tool
starts a daemon detached, in a session of its own that outlives the
agent's, and `gui` says when it is ready.

A script that has already loaded a design can `source
tools/odb_debug/daemon.tcl` to serve it instead of opening a stage;
`ODB_DEBUG_DIR` must be set in the environment (`//test/odb_debug:block_test`
does this with a hand-made LEF and DEF).

### `daemon.json`

Written once the viewer takes requests, removed when the daemon exits on
its own:

```json
{"port":41123,"pid":12345,"dir":"...","url":"http://127.0.0.1:41123",
 "gui_url":"http://10.8.0.5:41150/?token=...","design":"cpu","odb":".../3_place.odb","workspace":"...","commit":"8dd2fb5...",
 "timing":false}
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
| `check_setup` | each `check_setup` warning with its count, example pins and the instance prefixes they cluster in (`.claude/skills/check-setup/SKILL.md`) |
| `report cmd` | what any `report_*` command prints |
| `tcl code` | anything else: result and captured stdout |
| `image path` | a PNG of an area (`save_image -web`, headless) |
| `pin_access pin` | why a pin has no access point: DRT's markers for each rejected candidate, by constraint |
| `period` | the reg2reg period, violating reg2reg endpoints, their TNS |
| `floor_wire`, `floor_wire_skew` | the reg2reg period at zero wire, at today's clock arrivals and with useful skew |
| `floor_cycles`, `floor_cycles_nowire` | the one-flop-loop floor, with wires as built and at zero wire |
| `skew_headroom`, `vt_headroom` | the period with useful skew (timing only, hold kept) or the cones at the fastest VT loaded, with the leakage it costs; undone after |
| `headroom` | all of the above in one table, and how each stage ended (`.claude/skills/repair-headroom/SKILL.md`) |
| `open target` | start the daemon on a flow stage target (`gui_<stage>`) or an `odb_debug()` target, detached; returns at once |
| `gui` | `loading` (end of the launch log), `ready` (the GUI link and how to open it) or `stopped` |

A reply longer than 16000 characters (`MAX_TEXT` in `mcp_server.py`)
keeps its head and tail and says how much was dropped, so one
`report_checks` cannot flood the agent's context. The shell client is not
capped.

## Debug renderers and the viewer's rough edges

`detailed_route_debug`, `global_placement_debug` and the like stop at every
step for a Continue. The client continues each stop and collects what was
logged on the way, so a command that pauses hundreds of times runs to the
end in seconds, through `tcl` or a typed tool. `pin_access` is built on
this: why DRT rejects a candidate exists only in `-pa_markers`'s output.

The rough edges are OpenROAD's; the daemon works around them or says so:

- With one thread, a debug pause inside `tcl_eval` holds the only thread
  that could deliver the Continue; the daemon raises the count to two.
- `web_server` would open a browser wherever it runs; on a desktop
  `xdg-open` ignores `$BROWSER`. The daemon passes `-no_browser`
  (OpenROAD#11658), so nothing opens.
- `web_server` listens, runs the browser launcher (skipped here), and
  only then lets requests in; a request in between crashes OpenROAD
  (signal 11). `daemon.json` therefore
  appears two seconds after the viewer starts (`daemon.json.pending`
  until then).
- `web_server` blocks, and Tcl's event loop does not run under it, so the
  idle exit is a shell beside the daemon that watches `heartbeat`: busy
  while a request runs, idle from when it ended, so a long request is
  neither cut short nor followed by an exit the moment it returns. It
  stops the daemon as a browser's `exit` does, through the viewer with
  `odbdebug.py` (which `odb_debug()` ships beside `daemon.tcl`), so
  `web_server` returns and the run ends with status 0; a kill, the
  fallback when that fails, ends it with SIGTERM, which make reports as a
  failed run.
- The logger prints a message id at most 1000 times per process
  (`utl::Logger::max_message_print`). Repeated `pin_access` calls on one
  daemon run out of DRT-0119 (via markers); the reply's
  `message_limit_hit` says so. Relaunch for the full set.

The websocket protocol is the viewer's own and unversioned;
`//test/odb_debug:block_test` is what notices when a bump changes it.

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
| `od_check_setup ?examples? ?depth? ?top? ?out?` | needs timing; as `check_setup`, every line to `out` if given |
| `od_period`, `od_floor_wire`, `od_floor_cycles ?ends?`, `od_floor_wire_skew ?ends?`, `od_floor_cycles_nowire ?ends?`, `od_skew_headroom ?ends? ?hold?`, `od_vt_headroom ?ends?`, `od_headroom ?ends?` | need timing; as the tools of the same names. The measurements are `hr_*` procs in `headroom.tcl` beside `daemon.tcl`, shared with `orfs_headroom`'s stitched view of a parent and its blocks |
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

A request is `od_web_request <base64 of UTF-8 Tcl>`, sent as the viewer's
`tcl_eval` over its websocket (`ws://127.0.0.1:<port>/ws`) and evaluated at
global scope. Its result is one JSON reply:

```
{"ok":true,"result":"<string>","stdout":"<string>","ms":<int>}
{"ok":false,"error":"<message>","stdout":"<string>","ms":<int>}
```

Base64 keeps newlines and braces out of the framing, so multi-line Tcl is
one request. The websocket framing is the viewer's: JSON requests, binary
replies `[4-byte id][1-byte kind][3 reserved][payload]`, id 0 for pushes
(`log`, `debug_paused`); `webclient.py` has the details. The daemon listens
on `127.0.0.1` only and has the trust model of an interactive openroad
shell on the same machine.

## Tests

`//tools/odb_debug:odbdebug_test` runs the client and the MCP server
against a fake viewer (`fake_viewer.py`) answering `od_web_request`, and
`open` against a stand-in bazelisk; `:gui_proxy_test` checks that only the
token gets through, in front of a stand-in viewer;
`:webclient_test` runs the websocket client against the same fake and the
pin-access parser on DRT's real output; `:geometry_test` runs the
forensics on a hand-made dump. `//test/odb_debug:smoke_test` launches the
real daemon on a placed multiplier and asks it everything once;
`//test/odb_debug:block_test` launches it on a 10 µm block whose 36 nm M3
pin has no access point, asks `pin_access` and `image`, and checks the
idle exit and the GUI link (a loaded daemon waits for its first visitor,
the token gates the viewer, the visit starts the idle clock), in seconds.
