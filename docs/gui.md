# ORFS GUI

A local GUI for monitoring and interacting with bazel-orfs builds.
Think **modern gitk for ORFS**: fast, lightweight, file-system driven.

The UI matches GitHub's design language (fonts, spacing, dark theme) so
it feels natural to use alongside GitHub in a browser. A common workflow
is GitHub in one tab, ORFS GUI in another.

## What You Can Do

- **See the build graph** — all ORFS targets as an interactive DAG,
  color-coded by stage and build status
- **Monitor builds in real-time** — launch the GUI on a running
  `bazel build` (started by you, a colleague, or a screen session) and
  see progress as files appear in bazel-bin
- **Read logs** — per-stage and per-substep, with error/warning
  highlighting and search
- **View metrics** — all ORFS JSON metrics (power, area, timing,
  instances, utilization, wirelength, congestion, DRC counts)
- **Read reports** — timing, congestion, DRC, power reports
- **Check cache setup** — warns if `--disk_cache` is not configured
- **Start builds** — trigger `bazel build` from the graph (planned)
- **Edit parameters** — modify `design.yaml` from the GUI (planned)
- **Generate issue reproducers** — package bazel artifacts for bug
  reports (planned)
- **Run whittle** — minimize ODBs for debugging with live progress
  (planned)
- **Track history** — PPA trends over time in yaml files (planned)
- **Sweep parameters** — visualize `orfs_sweep()` variants, drive
  optimization with Optuna, view Pareto fronts (planned)

## Quick Start

```bash
# From any project using bazel-orfs:
bazelisk run @bazel-orfs//:gui

# Or from the bazel-orfs repo itself:
bazelisk run //:gui

# The server persists after closing the browser.
# Press Ctrl-C in the terminal to stop it.
# Re-running from another terminal just opens a new browser window.
```

## Architecture

- **Backend**: Flask (Python) reads files from `bazel-bin/`
- **Frontend**: HTML/JS SPA with Cytoscape.js (DAG) and Chart.js (charts)
- **Window**: system browser (default), pywebview native window with `--gui=webview`
- **Communication**: Files only — no IPC between ORFS builds and the GUI
- **Live reload**: static files served from workspace source, no caching —
  edit `gui_src/static/` and refresh the browser to see changes

The GUI is a pure filesystem observer. It works regardless of how builds
were started (GUI button, another terminal, screen session, CI).

## User Personas

1. **Students** — learning the flow, visual feedback, parameter tweaking
2. **Megaboom builders** — hierarchical designs, build graph overview, variant comparison
3. **OpenROAD developers** — reproduce problems, generate issue reproducers, whittle ODBs

## Status Colors

| Color | Meaning | How detected |
|-------|---------|-------------|
| Gray (solid) | Has output | .odb exists in bazel-bin (may be stale — only Bazel knows if it's cached) |
| Blue (pulsing) | Building now | Active `bazel build` subprocess |
| Gray (hollow) | No output | No .odb in bazel-bin |
| Red (solid) | Failed | Build process exited with error |

Note: the GUI cannot know whether Bazel considers an artifact cached or
stale. Only Bazel's action cache knows that. A solid gray dot means "an
.odb file exists from a previous build" — it may or may not be reused on
the next build.

## Dependencies

GUI deps are isolated in `requirements_gui.in` (flask, pywebview).
They are never pulled for non-GUI targets or in CI. The pip hub
`bazel-orfs-gui-pip` is marked `dev_dependency = True` so downstream
consumers are completely unaffected.

---

## Staged Development Plan

### Stage 1: MVP — Graph + Logs + Metrics (CURRENT)

**Status**: In progress

**What's built**:
- `requirements_gui.in` — flask, pywebview
- `MODULE.bazel` — third pip hub `bazel-orfs-gui-pip` (dev_dependency)
- `BUILD` — `gui` py_binary + `requirements_gui` compile + py_test targets
- `gui_src/server.py` — Flask server + pywebview launcher + persistent server lifecycle
  - `BUILD_WORKSPACE_DIRECTORY` for workspace discovery (works from `@bazel-orfs//:gui`)
  - Lockfile in `tmp/.gui_port` for detecting existing server
  - `--gui=webview|browser` flag
- `gui_src/query.py` — bazel query wrapper with 30s cache, DOT→Cytoscape JSON
- `gui_src/metrics.py` — ORFS-aware reader for JSON metrics, logs, reports
  - Mirrors `STAGE_SUBSTEPS`, `STAGE_METADATA` from `private/stages.bzl`
  - PPA extraction from all ORFS JSON metric fields
  - File change detection for SSE live updates
- `gui_src/static/` — Dark-theme SPA with tabs: Graph, Metrics, Logs, Reports
  - Cytoscape.js interactive DAG with stage-colored nodes
  - Status-colored node borders (green/blue/amber/red)
  - Log viewer with error/warning highlighting
  - Metrics table with PPA summary
- `gui_src/query_test.py`, `gui_src/metrics_test.py` — Unit tests with mocked filesystem

**What's missing for Stage 1**:
- Generate `requirements_gui_lock_3_13.txt` lock file
- Verify `bazel build //:gui` compiles
- Run tests
- End-to-end smoke test with a real design

### Stage 2: PPA + Config + History

- **Chart.js PPA dashboard**: power/area/timing per stage, variant comparison
- **`design.yaml` support in `orfs_flow()`**: stage-aware via `ORFS_VARIABLE_TO_STAGES`.
  `orfs_flow()` picks up `design.yaml` in same package, merges into `arguments`
  before `get_stage_args()` routes to correct stages. Changing `GRT_*` does NOT
  redo synthesis. BUILD files are never modified.
- **GUI parameter editor**: reads/writes `design.yaml`
- **Cache setup checker**: verifies `--disk_cache` in `.bazelrc`/`user.bazelrc`
- **Time estimation heuristics**: route ~10x place for >100K instances, refined
  by historical data from completed builds
- **History tracking**: after builds, metrics appended to `tmp/history/<design>.yaml`.
  Trend charts over time. Location configurable via `--history-dir`.

Files to create:
- `gui_src/config.py` — design.yaml reader/writer
- `gui_src/history.py` — PPA history in yaml files
- `gui_src/config_test.py`, `gui_src/history_test.py`

Files to modify:
- `private/flow.bzl` — `orfs_flow()` picks up `design.yaml`
- `gui_src/static/app.js` — add PPA charts, config editor, history tab

### Stage 3: Build Controls + Live Monitoring

The GUI is a pure filesystem observer — it detects in-progress builds by
watching bazel-bin for file changes (mtime polling). You can launch the GUI
on a build started by someone else (or another terminal, screen session)
and immediately see progress.

- **Observe any running build**: automatic via file watching
- **Start builds from GUI**: "Build" button triggers `bazel build` subprocess
  managed by the server. Can be stopped from GUI or by killing the server.
- **Start builds from terminal**: `bazel build` in another terminal — GUI
  picks it up automatically
- Blue pulsing status for in-progress stages
- SSE live log streaming (tails log files as they grow)
- Red status when error patterns detected in logs
- Green transition when stage output .odb appears

Files to create:
- `gui_src/processes.py` — background subprocess manager

### Stage 4: Issue Generation + Whittle

Python-based reproducer generation from bazel artifacts directly (not
brittle `make issue`). Uses Bazel knowledge to find ODB, config, logs
for each target/stage.

- **`gui_src/issue.py`**: reads bazel-bin artifacts, packages reproducer
  - User selects components: ODB/DEF, LEF subset, LIB, config, Tcl script
  - Generates self-contained tar.gz or directory
  - Extensively unit-tested with mocked filesystem
- **Whittle GUI**: dedicated tab for `whittle.py`
  - Form: select stage ODB (auto-populated), error string, persistence
  - Live progress chart: instance count vs iteration (parsed from whittle.log)
  - Stop button, results with reduction ratio

Files to create:
- `gui_src/issue.py` — reproducer generation
- `gui_src/issue_test.py`

### Stage 5: Parameter Sweeps + Optimization

Integrate with `orfs_sweep()` for design space exploration, driven by
external optimizers like Optuna.

- **Sweep tab**: visualize `orfs_sweep()` variants and their PPA results
  side-by-side (bar charts, Pareto fronts)
- **Static variant grid**: `orfs_sweep()` pre-defines a set of Bazel
  targets with different parameter combinations. The GUI shows them as
  a grid with PPA columns, sortable by any metric.
- **Optuna integration**: an optimizer loop (e.g., Optuna) populates
  `design.yaml` files for each sweep variant, triggers builds, reads
  PPA results from bazel-bin, and suggests the next trial. The GUI
  monitors this loop:
  - Live trial history chart (parameter values vs PPA)
  - Pareto front visualization (power vs area vs timing)
  - Hyperparameter importance plot
  - Stop/pause optimization from the GUI
- **Workflow**: user defines sweep parameters in BUILD via `orfs_sweep()`,
  which creates fixed Bazel targets. Optuna selects which variants to
  build and in what order, writing parameters to `design.yaml` files.
  Bazel caches ensure unchanged variants aren't rebuilt. The GUI shows
  all of this in real time.

### Stage 6: Flow Images

Optional PNG generation during ORFS flow. Images rendered as files,
GUI auto-discovers them.

- Add optional image outputs to ORFS stage rules in `private/rules.bzl`
- OpenROAD GUI scripting produces PNG per stage
- Image gallery tab in GUI, click to zoom
- Auto-discovery from `bazel-bin/<pkg>/images/`

Files to modify:
- `private/rules.bzl` — optional image generation
- `gui_src/static/app.js` — Images tab

## File Structure

```
gui_src/
  __init__.py           # empty package marker
  server.py             # Flask app + pywebview launcher
  query.py              # bazel query wrapper + caching
  metrics.py            # ORFS-aware file reader
  query_test.py         # unit tests
  metrics_test.py       # unit tests
  static/
    index.html          # SPA shell
    app.js              # main application logic
    style.css           # dark theme
    lib/
      cytoscape.min.js  # DAG visualization (vendored, MIT)
      chart.min.js      # charts (vendored, MIT)

# Future files (Stages 2-4):
  config.py             # design.yaml reader/writer
  history.py            # PPA history tracking
  issue.py              # reproducer generation
  processes.py          # background process manager
  config_test.py
  history_test.py
  issue_test.py
```

## Key Design Decisions

### Files-Only Communication

The GUI never uses IPC, sockets, or custom protocols to communicate with
running builds. It reads files from `bazel-bin/` — the same files that
ORFS stages produce naturally. This means:
- GUI works with builds started by anyone (another user, screen, CI)
- No coupling between build process and GUI process
- Nothing to break when ORFS internals change

### Separate Dependencies

`requirements_gui.in` keeps GUI deps (flask, pywebview) out of:
- Main `requirements.in` (PyYAML only)
- Feature `requirements_features.in` (matplotlib only)
- CI containers (never pull GUI deps)
- Downstream consumers (pip hub is `dev_dependency = True`)

### Persistent Server, Ephemeral Browser

The server writes `tmp/.gui_port` with PID and port. Second invocations
detect the running server and just open a browser window. Ctrl-C stops
the server and cleans up the lockfile.

### `@bazel-orfs//:gui` from Consumer Projects

`BUILD_WORKSPACE_DIRECTORY` points to the consumer's workspace (e.g.,
the demo repo), while `__file__` resolves to bazel-orfs's runfiles for
static files. This means the GUI shows the consumer's targets and builds
while serving its own frontend assets.

### ORFS Domain Knowledge

The GUI mirrors constants from `private/stages.bzl`:
- `ALL_STAGES` — stage order
- `STAGE_SUBSTEPS` — substeps within each stage
- `STAGE_METADATA` — output files, reports, JSON metrics per stage
- `STAGE_OUTPUTS` — primary output file per stage (.odb)

This allows it to:
- Parse target names into design/variant/stage
- Locate logs, metrics, reports in bazel-bin
- Detect build status by checking output file existence
- Understand PPA metric field names
- Know that `abstract_stage` targets are macros/memories
