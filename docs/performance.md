# Build speed, monitoring and CI timing

## Speed up your builds

## Disable expensive operations for CI and development

For CI or iterative development where timing closure isn't needed, you can
disable expensive operations. The `FAST_SETTINGS` dict in [examples/BUILD](../examples/BUILD)
shows the recommended settings:

| Setting | Stage | What it disables | Speed impact |
|---------|-------|------------------|-------------|
| `REMOVE_ABC_BUFFERS` = `"1"` | floorplan | Removes synthesis buffers instead of running `repair_timing_helper` (gate sizing, VT swapping). Without this, floorplan timing repair can run for hours. | Very high |
| `GPL_TIMING_DRIVEN` = `"0"` | place | Timing-driven global placement. Skips timing path analysis and buffer removal during placement iterations. | High |
| `GPL_ROUTABILITY_DRIVEN` = `"0"` | place | Routability-driven global placement. Skips routing congestion estimation during placement. | Moderate |
| `SKIP_CTS_REPAIR_TIMING` = `"1"` | cts | Timing repair after clock tree synthesis. Skips iterative buffer insertion, gate sizing, gate cloning, and VT swapping. Can reduce CTS from hours to minutes. | Very high |
| `SKIP_INCREMENTAL_REPAIR` = `"1"` | grt | Incremental repair during global routing. Skips two rounds of `repair_design` + `repair_timing` with incremental re-routing. | Very high |
| `SKIP_REPORT_METRICS` = `"1"` | all | Metrics reporting (`report_checks`, `report_wns`, `report_tns`, `report_power`, `report_clock_skew`) at every stage. | Moderate |
| `FILL_CELLS` = `""` | route | Fill cell insertion (`filler_placement`). Required for manufacturing but not for design exploration. | Low |
| `TAPCELL_TCL` = `""` | floorplan | Custom tap/endcap cell placement script. Falls back to simple `cut_rows`. | Low |
| `PWR_NETS_VOLTAGES` = `""` | final | IR drop analysis for power nets (`analyze_power_grid`). | Low |
| `GND_NETS_VOLTAGES` = `""` | final | IR drop analysis for ground nets (`analyze_power_grid`). | Low |

Apply these settings in your `orfs_flow()` target:

```starlark
FAST_SETTINGS = {
    "FILL_CELLS": "",
    "GND_NETS_VOLTAGES": "",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_TIMING_DRIVEN": "0",
    "PWR_NETS_VOLTAGES": "",
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_INCREMENTAL_REPAIR": "1",
    "SKIP_REPORT_METRICS": "1",
    "TAPCELL_TCL": "",
}

orfs_flow(
    name = "my_design",
    arguments = FAST_SETTINGS | {
        "CORE_UTILIZATION": "40",
        # ...
    },
    verilog_files = ["my_design.sv"],
)
```

## Set abstract_stage as early as possible

The `abstract_stage` parameter controls how far the flow runs. Setting it earlier
skips all subsequent stages:

| `abstract_stage` | Stages built | Stages skipped |
|------------------|--------------|----------------|
| `"place"` | synth, floorplan, place | cts, grt, route, final |
| `"cts"` | synth → cts | grt, route, final |
| `"grt"` | synth → grt | route, final |
| `"route"` | synth → route | final |
| `"final"` (default) | All stages | None |

Abstract generation requires at least the `place` stage because pins are placed
during placement. For macro size estimation, `"place"` is usually sufficient.
For timing analysis, `"cts"` provides clock tree data without expensive routing.

## Squashed flows

By default, `orfs_flow()` creates one Bazel target per stage (the default
`squash = False`), each storing its own ODB checkpoint. This is useful for
debugging — you can inspect any intermediate stage, re-run from a checkpoint,
and iterate on individual substeps.

`squash = True` combines all stages after synthesis into a single Bazel action.
Only the final stage's ODB is stored as an artifact. This is for mature, stable
designs like RAM macros where nobody needs to inspect intermediate stages:

```starlark
# Stable RAM macro — no need to inspect intermediate stages
orfs_flow(
    name = "sram_64x128",
    abstract_stage = "cts",
    squash = True,
    ...
)
```

The reduction in artifact count is significant: instead of 7 ODB checkpoints
(synth through final), you get 2 (synth + final). For CI with multiple PDKs
and variants, this saves considerable storage.

Which ODB files to checkpoint as artifacts is flow-specific — the default
per-stage boundaries are just one common case that `orfs_flow()` encodes.
`squash = True` is the other extreme. Advanced users can use `orfs_squashed`
directly for custom groupings (e.g., squashing only floorplan through place
while keeping later stages separate).

Wrapper macros (like those for SRAMs or register files) that call
`orfs_flow()` internally are good candidates for `squash = True`, since
sub-macros are typically stable once working and don't need per-stage
inspection.

You can still use `//:deps` to deploy and debug individual substeps of a
squashed flow if something goes wrong:

```bash
bazel run //:deps -- //sram:sram_64x128_place do-3_4_place_resized
```

## Query timing interactively

Open an interactive OpenROAD shell or GUI to investigate a completed stage:

```bash
# GUI with timing loaded
bazel run <target>_<stage> gui_<stage>

# Interactive TCL shell (no GUI)
bazel run <target>_<stage> open_<stage>
```

Useful TCL commands once inside OpenROAD:

| Command | What it shows |
|---------|---------------|
| `report_checks -path_delay max -group_count 5` | Top 5 worst setup timing paths |
| `report_checks -path_delay max -through [get_pins *name*]` | Worst path through a specific pin |
| `report_wns` | Worst negative slack |
| `report_tns` | Total negative slack |
| `get_cells -hier *name*` | Find instances by name pattern |

## Monitor long-running builds

ORFS stages can take minutes to hours. To monitor progress, find the active
OpenROAD processes and tail their log files.

**Step 1: Find what's running with `ps`**

```bash
# Find active openroad processes — the command line shows the script and log path
ps -Af | grep openroad | grep -v grep
```

Example output:

```
user 2175870 ... openroad -exit ... flow/scripts/global_place.tcl -metrics .../3_3_place_gp.json
```

From the process command line you can read:
- Which script is running (`global_place.tcl` = placement stage)
- The sandbox path and log file name (replace `.json` with `.tmp.log` for the active log)

**Step 2: Tail the active log**

During execution, the active log has a `.tmp.log` suffix inside the Bazel sandbox.
When the action completes, the sandbox is destroyed — so `.tmp.log` files vanish.
The final `.log` is written to `bazel-out/` only on completion.

To capture live output, use `tee` to save a copy before the sandbox disappears:

```bash
# Find active .tmp.log files and tee them to /tmp for later inspection
find ~/.cache/bazel -name "*.tmp.log" -size +0c 2>/dev/null | \
  while read f; do
    name=$(basename "$f" .tmp.log)
    tail -f "$f" | tee "/tmp/${name}.log" &
  done
```

**Step 3: Monitor via the local flow** (easier, recommended for debugging):

```bash
# Start the build in the local flow
bazel run //:deps -- //test:L1MetadataArray_cts
tmp/test/L1MetadataArray_cts_deps/make do-cts &

# In another terminal, watch the log
tail -f tmp/test/L1MetadataArray_cts_deps/logs/4_1_cts.log
```

**What to look for in logs:**

| Log pattern | What it means | Action to speed up |
|-------------|---------------|-------------------|
| `Iteration \| Overflow` decreasing slowly | Global placement convergence. Overflow should drop toward 0. | Set `GPL_TIMING_DRIVEN=0` and `GPL_ROUTABILITY_DRIVEN=0` to skip timing/congestion analysis per iteration. |
| `repair_timing` running for many iterations | Timing repair loop — can run for hours. | Set `SKIP_CTS_REPAIR_TIMING=1` (CTS) or `SKIP_INCREMENTAL_REPAIR=1` (GRT). Or set `SETUP_SLACK_MARGIN`/`HOLD_SLACK_MARGIN` to terminate early. |
| `[WARNING STA-1554]` "not a valid start point" (thousands) | SDC constraints reference pins that don't exist. Harmless but floods the log and slows STA. | Fix SDC constraints or filter with `suppress_message`. |
| `remove_buffers` / `repair_timing_helper` in floorplan | Buffer optimization after synthesis. | Set `REMOVE_ABC_BUFFERS=1` to skip this entirely. |
| `report_checks` / `report_wns` / `report_clock_skew` | Metrics reporting at stage end. | Set `SKIP_REPORT_METRICS=1` to skip. |
| `estimate_parasitics` | Parasitic estimation — usually fast. Indicates transition between sub-steps. | Normal, no action needed. |
| `filler_placement` | Fill cell insertion. | Set `FILL_CELLS=""` to skip (not needed for CI/DSE). |
| `analyze_power_grid` | IR drop analysis. | Set `PWR_NETS_VOLTAGES=""` and `GND_NETS_VOLTAGES=""` to skip. |

**Log file naming convention:**

Each ORFS stage produces numbered log files under `logs/`. During execution,
the active file has a `.tmp.log` suffix:

| Stage | Log files |
|-------|-----------|
| synth | `1_1_yosys_canonicalize.log`, `1_2_yosys.log` |
| floorplan | `2_1_floorplan.log` through `2_4_floorplan_pdn.log` |
| place | `3_1_place_gp_skip_io.log` through `3_5_place_dp.log` |
| cts | `4_1_cts.log` |
| grt | `5_1_grt.log` |
| route | `5_2_route.log`, `5_3_fillcell.log` |
| final | `6_1_merge.log`, `6_report.log` |

## Where CI time goes

The CI pipeline (`.github/workflows/ci.yml`) runs 6 jobs. The `test-make-target` job
is a matrix of 9 targets that run in parallel on separate runners. Use `--profile` and
`analyze-profile` to profile your own builds:

```bash
bazel build <target> --profile=/tmp/profile.gz
bazel analyze-profile /tmp/profile.gz
```

### Smoketests (`bazel test ...`)

The smoketests job builds *everything* including sram and sky130 targets.
Critical path runs through the `sram/` hierarchical build (sdq_17x64 → top):

```
Critical path (553 s):
  Action                                          Time      %
  sram/sdq_17x64  1_1_yosys_canonicalize          5.5s    1%
  sram/sdq_17x64  1_2_yosys.v (synthesis)        31.2s    6%
  sram/sdq_17x64  2_floorplan.odb                28.0s    5%
  sram/sdq_17x64  3_place.odb                   298.1s   54%   ← placement dominates
  sram/sdq_17x64  generate_abstract               9.3s    2%
  sram/top         1_1_yosys_canonicalize          4.7s    1%
  sram/top         1_2_yosys.v (synthesis)         9.0s    2%
  sram/top         2_floorplan.odb                25.2s    5%
  sram/top         3_place.odb                   129.0s   23%   ← placement again
  sram/top         4_cts.odb                       9.0s    2%
  sram/top         generate_abstract               4.6s    1%
```

Placement (global_place + global_place_skip_io) accounts for ~77% of the critical path.

### test-make-target matrix

Each target runs on a separate CI runner. The critical path target is
`tag_array_64x184_generate_abstract` (CTS abstract with hierarchical L1MetadataArray):

```
Critical path (465 s):
  Action                                          Time      %
  tag_array_64x184 synth                         20.9s    4%
  tag_array_64x184 floorplan                     21.8s    5%
  tag_array_64x184 place                        224.8s   48%   ← placement dominates
  tag_array_64x184 cts                           12.4s    3%
  tag_array_64x184 generate_abstract              4.5s    1%
  L1MetadataArray  synth                         16.4s    4%
  L1MetadataArray  floorplan                     18.9s    4%
  L1MetadataArray  place                        134.7s   29%   ← placement again
  L1MetadataArray  cts                            7.5s    2%
  L1MetadataArray  generate_abstract              3.3s    1%
```

Other matrix targets are faster since they build subsets of the same dependency chain.
The `subpackage/` targets duplicate `test/` builds in a separate Bazel package (203s
critical path for tag_array_64x184 alone).

### Per-design timing (single-design, synth through CTS with FAST_SETTINGS)

| Design | Synth | Floorplan | Place | CTS | Abstract | Total |
|--------|-------|-----------|-------|-----|----------|-------|
| lb_32x128 (small) | 5s | 7s | 15s | 3s | - | 25s |
| tag_array_64x184 | 21s | 22s | 225s | 12s | 5s | 280s |
| sdq_17x64 (megaboom) | 37s | 28s | 298s | - | 9s | 362s |
| L1MetadataArray (hierarchical) | 16s | 19s | 135s | 8s | 3s | 181s |

Each OpenROAD sub-step has a minimum startup overhead of ~1.3s (loading the database,
reading libraries). For small designs, this overhead dominates. For large designs,
`global_place` dominates instead — it accounts for 50-85% of the placement stage.

## Force a cache miss for testing

Bazel caches based on content hashes. To force a specific stage to rebuild without
`bazel clean` (which is slow and rebuilds everything), change a variable that
belongs to that stage:

```starlark
# Force floorplan rebuild by changing a floorplan variable
"CORE_UTILIZATION": "21",  # was "20"

# Force placement rebuild by changing a placement variable
"PLACE_DENSITY": "0.21",   # was "0.20"
```

Each ORFS variable is assigned to a specific stage via `variables.yaml`. Changing a
variable only invalidates its stage and all subsequent stages — synthesis is preserved.
See `ORFS flow/scripts/variables.yaml` for which variables belong to which stage.

## Debug cache misses

Use `--explain` to understand why Bazel is rebuilding a target:

```bash
bazel build <target> --explain=/tmp/explain.txt --verbose_explanations
```

Avoid `bazel clean --expunge` — it forces a full rebuild. If you need to force-rebuild
one target, use the [`PHONY` variable trick](customize.md#force-a-rebuild) instead.

## CI optimization opportunities

Potential improvements to the bazel-orfs CI pipeline:

- **Placement dominates**: 50-85% of build time is `global_place`. ORFS upstream
  improvements to placement speed would have the largest impact.
- **Duplicate builds across packages**: `subpackage/` targets rebuild the same
  designs as `test/`, but in a separate Bazel package. The `test-make-target` matrix
  runs them on separate runners without shared caches.
- **Consolidate FAST_SETTINGS**: Copies exist in `examples/BUILD`, `test/BUILD`, `sram/BUILD`,
  and `subpackage/BUILD`. A shared `.bzl` file would prevent drift.
- **STA-1554 warning flood**: tag_array_64x184 emits ~1000 `STA-1554` warnings
  ("not a valid start point") per placement stage. These are harmless but slow
  down log processing. Fixing the SDC constraints would eliminate them.
- **OpenROAD startup overhead**: Each sub-step takes ~1.3s minimum for database/library
  loading. For small designs, this overhead is significant. ORFS sub-step consolidation
  would help.
- **`SKIP_REPORT_METRICS=1` for all CI targets**: Already applied via FAST_SETTINGS.
  Metrics reporting adds minutes per stage on large designs.
