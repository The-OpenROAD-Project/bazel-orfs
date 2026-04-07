# `orfs_arguments` — Computed Flow Arguments

## Overview

`orfs_arguments` is a Bazel rule that runs a Tcl script to compute ORFS
flow arguments (e.g., `CORE_UTILIZATION`, `PLACE_DENSITY`) from stage
outputs. The computed arguments are stored as a `.json` file and flow
through `OrfsInfo.arguments` to subsequent stages.

## OrfsInfo.arguments

`OrfsInfo.arguments` is a depset of `.json` files that accumulates as
stages run. Each `.json` file is a flat dictionary:

```json
{"CORE_UTILIZATION": "40", "PLACE_DENSITY": "0.65"}
```

When a stage generates its `.mk` config, it merges all inherited `.json`
files into a Makefile-style include. The `.mk` format is an implementation
detail — the interface is always `.json`.

### Precedence

Arguments are merged in this order (first set wins with `?=`):

1. **Inherited `.json` files** from `OrfsInfo.arguments` (included first)
2. **Stage's own arguments** from the `arguments` attr (written as `export VAR?=`)
3. **`extra_configs`** included last (can use `export VAR=` to force override)

## `orfs_arguments` Rule

### Usage

```python
load("//:openroad.bzl", "orfs_arguments")

orfs_arguments(
    name = "auto_utilization",
    src = ":my_design_synth",
    script = ":auto_utilization.tcl",
)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `src` | label | Previous stage target providing `OrfsInfo` |
| `script` | label | Tcl script that computes arguments |
| `arguments` | dict | Environment variables passed to the Tcl script |
| `data` | label_list | Additional input files for the Tcl script |

### Tcl Script Contract

The script receives:

- `$::env(SCRIPTS_DIR)` — ORFS scripts directory
- `$::env(RESULTS_DIR)` — results directory with stage outputs
- `$::env(WORK_HOME)` — working directory for outputs
- `$::env(OUTPUT)` — output filename (auto-generated `.json`)
- All entries from the `arguments` attr as environment variables

The script must write a JSON dictionary to `$WORK_HOME/$OUTPUT`:

```tcl
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb 1_synth.sdc

# ... compute values from the design ...

set out [file join $::env(WORK_HOME) $::env(OUTPUT)]
set f [open $out w]
puts $f "\{\"CORE_UTILIZATION\": \"40\", \"PLACE_DENSITY\": \"0.65\"\}"
close $f
```

### Output

The rule outputs `OrfsInfo` identical to the input, except:

- `OrfsInfo.arguments` has the computed `.json` appended to the depset

All other fields (`odb`, `gds`, `config`, etc.) pass through unchanged.

## `extra_arguments` in `orfs_flow`

Inject `.json` argument files at specific stages:

```python
orfs_flow(
    name = "my_design",
    extra_arguments = {
        "floorplan": [":auto_utilization"],
    },
    previous_stage = {"floorplan": ":my_design_synth"},
    # ...
)
```

## Example: Auto-Utilization Flow

```
orfs_synth ──> orfs_arguments(auto_util.tcl) ──> orfs_flow(floorplan+)
                     │                                    │
                     │ reads synth ODB                    │ inherits .json
                     │ computes CORE_UTILIZATION           │ via OrfsInfo.arguments
                     │ writes .json                       │
                     └────────────────────────────────────┘
```

```python
orfs_synth(
    name = "my_design_synth",
    verilog_files = ["rtl/my_design.sv"],
    # ...
)

orfs_arguments(
    name = "my_design_auto_util",
    src = ":my_design_synth",
    script = ":auto_utilization.tcl",
)

orfs_flow(
    name = "my_design",
    arguments = {/* other args */},
    previous_stage = {"floorplan": ":my_design_auto_util"},
    verilog_files = ["rtl/my_design.sv"],
    # ...
)
```

The floorplan stage inherits `CORE_UTILIZATION` and `PLACE_DENSITY` from
the `.json` computed by `auto_utilization.tcl`. These values take
precedence over defaults in the `arguments` dict because inherited `.json`
files are included before the stage's own `export VAR?=` lines.
