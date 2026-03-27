# Per-Stage OpenROAD Binaries

## Problem

The monolithic `openroad` binary links all ~37 modules (~197+ source files
for `drt` alone). When iterating on a single ORFS stage — say detailed
routing — rebuilding after a C++ change relinks everything, even modules
irrelevant to that stage. This makes the edit-compile-test cycle
unnecessarily slow.

Each ORFS stage invokes a narrow set of OpenROAD Tcl commands. The modules
behind those commands are already separate `cc_library` targets in Bazel.
But today there is only one `cc_binary` that links them all.

## Idea

Build one stripped-down OpenROAD binary per ORFS stage, linking only the
modules that stage actually needs. bazel-orfs would select the appropriate
binary for each stage target.

### Stage-to-module mapping (derived from ORFS Tcl scripts)

| Stage | Key commands | Required modules (beyond core) |
|-------|-------------|-------------------------------|
| 1 synth | `read_verilog`, `link_design`, `read_liberty` | dbSta, (Yosys external) |
| 2.1 floorplan | `initialize_floorplan`, `make_tracks`, `remove_buffers` | ifp, rsz |
| 2.2 macro_place | `rtl_macro_placer` | mpl |
| 2.3 tapcell | `cut_rows` | tap |
| 2.4 pdn | `pdngen` | pdn |
| 3.1-3.3 global_place | `global_placement`, `place_pins`, `estimate_parasitics` | gpl, ppl, rsz, grt (congestion) |
| 3.4 resize | `repair_design`, `estimate_parasitics` | rsz, grt |
| 3.5 detail_place | `detailed_placement`, `improve_placement`, `optimize_mirroring` | dpl |
| 4 cts | `clock_tree_synthesis`, `repair_timing`, `detailed_placement` | cts, rsz, dpl |
| 5.1 global_route | `global_route`, `pin_access`, `estimate_parasitics` | grt, drt (pin access) |
| 5.2 detail_route | `detailed_route` | drt |
| 5.3 fillcell | `filler_placement` | fin |
| 6 final | `extract_parasitics`, `write_spef`, report commands | rcx, ant, psm |

### Shared core (every binary needs these)

- `odb` — database foundation
- `sta` / `dbSta` — timing infrastructure
- `utl` — utilities
- `gui` — can be stubbed out for headless builds

### Implementation approach

1. **Audit**: for each ORFS substep Tcl script, grep for OpenROAD commands
   and trace them to `src/*/` module `Cmd` registrations to confirm the
   mapping above.
2. **Define `cc_binary` targets**: one per stage group in
   `OpenROAD/BUILD.bazel`, e.g. `openroad_route` linking only
   `core + grt + drt`.
3. **Stub unused module inits**: the `openroad` main registers all modules
   via `InitOpenRoad()`. Per-stage binaries would register only their
   modules. This likely requires a small refactor of `src/Main.cc` /
   `src/OpenRoad.cc` to make module registration configurable.
4. **Wire into bazel-orfs**: extend `orfs_step` rule to accept a
   per-stage `openroad` binary attribute, defaulting to the full binary
   for backwards compatibility.
5. **Validate**: run the full flow with per-stage binaries and diff the
   final `.odb` / metrics against the monolithic binary.

### Cross-cutting concerns

- **`estimate_parasitics`** appears in placement, CTS, and routing stages
  with different flags (`-placement` vs `-global_routing`). Need to verify
  which modules it pulls in for each mode.
- **`gpl` depends on `grt`** for congestion-driven placement — this is an
  unavoidable cross-stage dependency.
- **`repair_timing` / `rsz`** is used in placement, CTS, and post-route
  stages — it will appear in multiple stage binaries.

## Impact

- **Who benefits**: anyone iterating on OpenROAD C++ code for a specific
  stage (PII engineers, contributors, Ascenium).
- **How much**: linking the full binary takes ~30-60s; a stage binary with
  5-8 modules instead of 37 should link in under 10s. Over a day of
  edit-compile-test cycles this saves significant wall-clock time.
- **Side benefit**: makes the dependency structure explicit — documents
  which modules each stage actually needs, surfacing unnecessary
  coupling.

## Effort

Medium — the `cc_library` targets already exist. Main work is:
- Auditing the exact command-to-module mapping (~1 day)
- Refactoring module registration to be configurable (~1-2 days)
- Defining and testing per-stage `cc_binary` targets (~1 day)
- Wiring into bazel-orfs (~0.5 day)
