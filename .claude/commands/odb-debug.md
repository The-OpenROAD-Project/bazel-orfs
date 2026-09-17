> **Repo**: Run from your ORFS workspace root (the one with `MODULE.bazel` and the `bazel-orfs` dep). Examples use the neutral `//<project>:<module>_<stage>` naming — substitute your own targets.

Ask a placed or routed design questions through a persistent OpenROAD session, instead of reading logs or re-running a stage to print one number.

ARGUMENTS: $ARGUMENTS

The tool is `tools/odb_debug/` in bazel-orfs (`README.md` there is the
manual): a daemon Tcl that opens a stage's ODB in the flow's own OpenROAD
and answers Tcl over a localhost socket, a stdlib Python client, and an MCP
server exposing the daemon's procs as tools. Loading a large design once
and asking it many questions is the point: a 1 M-instance ODB loads in
seconds without liberty and in minutes with it, and every question after
that is milliseconds.

## 1. Decide what you are asking, and pick the ODB

- **Where did the flow leave things?** The stage's own ODB: `_floorplan`
  (macro placement, rows, PDN), `_place`, `_cts`, `_grt`, `_route`.
- **Why did a stage fail or stall?** The last checkpoint *inside* the
  stage. ORFS writes one per substep (`3_2_place_iop.odb`,
  `3_3_place_gp.odb`, `3_4_place_resized.odb`, `3_5_place_dp.odb` ...);
  the one before the failing substep is what to open. These live in the
  stage's `_deps` tree after `bazelisk build //<project>:<module>_place_deps`
  and a deploy, or wherever the stalled run put them.
- **Geometry or timing?** Geometry (macros, rows, instance positions,
  legality) needs no liberty: pass `GUI_TIMING=0` and the load is seconds.
  Timing (slack, paths, reports) needs the design's liberty set: leave the
  default, pay the load once.

## 2. Launch the daemon

From a target, on the stage's finished ODB:

```starlark
load("@bazel-orfs//:openroad.bzl", "odb_debug")

odb_debug(
    name = "cpu_place_odb_debug",
    src = ":cpu_place",
)
```

```bash
bazelisk run //<project>:cpu_place_odb_debug -- ODB_DEBUG_DIR=$PWD/tmp/odb-debug GUI_TIMING=0 &
```

From a deployed `_deps` tree, on any checkpoint:

```bash
./make run RUN_SCRIPT=$PWD/tools/odb_debug/daemon.tcl \
    ODB_FILE=$PWD/tmp/lab/results/3_4_place_resized.odb \
    ODB_DEBUG_DIR=$PWD/tmp/odb-debug GUI_TIMING=0 &
```

Wait for `tmp/odb-debug/daemon.json`. It carries the port, the ODB path,
the workspace and its git commit: **check the commit against the tree you
are studying** before trusting a number — a daemon from an earlier session
happily serves a stale ODB. The daemon exits on its own after an idle
period (default twice its load time, at least two minutes;
`ODB_DEBUG_IDLE_SECS` overrides, `0` disables).

## 3. Ask

With the MCP server registered (`.mcp.json` in this repo does it for Claude
Code; the daemon directory is `tmp/odb-debug` relative to the workspace),
the tools are `status`, `macros`, `cell_info`, `net_info`,
`check_placement`, `dump_geometry`, `wns`, `worst_paths`, `report` and
`tcl`. Without it, the same from a shell:

```bash
python3 tools/odb_debug/odbdebug.py tmp/odb-debug od_status
python3 tools/odb_debug/odbdebug.py tmp/odb-debug od_cell rob/u_buf_1234
python3 tools/odb_debug/odbdebug.py tmp/odb-debug --tcl 'report_checks -path_delay max -group_path_count 3'
```

Start with `status`: design, instance and macro counts, timing on or off,
die and core. Then the question you came with. `tcl` runs anything the
openroad shell would (odb API, `sta::`, `gpl::`, `dpl::`, `grt::`); it
returns the result and captured `puts` output separately. Prefer the
typed tools where one fits — their answers are JSON in microns.

## 4. Placement forensics, the common case

A legaliser that fails (`DPL-0035`/`DPL-0036`) or never finishes is a
floorplan question, not a legaliser bug, until proven otherwise:

1. `dump_geometry` to a directory, then
   `python3 tools/odb_debug/geometry.py free <dir>`: how much site area
   there is and how much of it sits in row fragments too narrow to hold
   anything (slivers between abutting macros). A floorplan with mm² of
   free area and tens of thousands of 5–20 µm fragments has no room where
   the placer wants it.
2. `geometry.py inside <dir>`: which logic cells global placement left
   inside a macro footprint, per macro. Every one is a cell the legaliser
   must carry out of the macro; thousands of them is a density or
   channel-width problem.
3. Take the instance names from the failure log into a file and
   `geometry.py failed <dir> <names.txt>`: where the failed cells are,
   whether they are stacked on one coordinate, how crowded their
   neighbourhood is, which 100 µm squares they cluster in. Wire buffers in
   slivers point at channel width (`ANNEAL_BLOCK_GAP_UM`, macro halos);
   cells in the open in a crowded square point at density.
4. `--png` on any of the three draws the free-site grid, macro outlines and
   the cells in question; look at the picture before changing a knob.

Fix the floorplan (channel width, utilisation, halos, macro placement),
then let the flow re-run from floorplan. Widening the legaliser's search
window (`-max_displacement`, microns) is a mitigation, not a fix.

## 5. Rules

- Never read a large ODB, log or geometry dump into context; ask the
  daemon or run `geometry.py` and read their summaries.
- `tcl` has the trust model of an interactive openroad shell on the same
  machine, and the daemon listens on `127.0.0.1` only. Do not write the
  ODB from the daemon; a study wants the flow's files read-only.
- One daemon per `ODB_DEBUG_DIR`. Relaunching overwrites `daemon.json`;
  stop the old one first, or use another directory.
