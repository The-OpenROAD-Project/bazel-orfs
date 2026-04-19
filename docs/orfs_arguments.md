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

`.json` sources are merged before the stage's `.mk` is written, with later
sources overriding earlier ones:

1. **Inherited** `.json` files from `OrfsInfo.arguments` (weakest)
2. **Stage's own arguments** from the `arguments` attr
3. **`extra_arguments`** `.json` files attached at this stage (strongest)

The merged dict is emitted as `export VAR?=value` into `stage.args.mk`, which
is included at the top of `stage.mk` — so `stage.args.mk` wins over any
later `?=` defaults in the stage config or included makefiles.
`extra_configs` files are included *after* the stage's own exports and can
still force-override with `export VAR=value` (unconditional assignment).

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
- `$::env(OUTPUT)` — output path (Bazel-declared `.json` file)
- All entries from the `arguments` attr as environment variables

The script must write a JSON dictionary to `$::env(OUTPUT)`:

```tcl
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb 1_synth.sdc

# ... compute values from the design ...

set f [open $::env(OUTPUT) w]
puts $f "\{\"CORE_UTILIZATION\": \"40\", \"PLACE_DENSITY\": \"0.65\"\}"
close $f
```

### Output

The rule outputs `OrfsInfo` identical to the input, except:

- `OrfsInfo.arguments` has the computed `.json` appended to the depset

All other fields (`odb`, `gds`, `config`, etc.) pass through unchanged.

## `extra_arguments` in `orfs_flow`

Inject `.json` argument files at specific stages. `extra_arguments` wins
over the stage's own `arguments` attr (see precedence above), so this is
the knob for overriding baseline values with runtime-computed ones:

```python
orfs_flow(
    name = "my_design",
    arguments = {"CORE_UTILIZATION": "30"},  # default
    extra_arguments = {
        "floorplan": [":auto_utilization"],  # overrides CORE_UTILIZATION
    },
    # ...
)
```

## Example: Auto-Utilization Flow

```
orfs_synth ──> orfs_arguments(auto_util.tcl) ─┐
                                              ├─> orfs_flow(..., extra_arguments=...)
                                              │   (floorplan merges the .json)
                                              └───
```

```python
orfs_arguments(
    name = "my_design_auto_util",
    src = ":my_design_synth",
    script = ":auto_utilization.tcl",
)

orfs_flow(
    name = "my_design",
    arguments = {"CORE_UTILIZATION": "30"},
    extra_arguments = {
        "floorplan": [":my_design_auto_util"],
    },
    verilog_files = ["rtl/my_design.sv"],
    # ...
)
```

The floorplan stage merges `CORE_UTILIZATION` and `PLACE_DENSITY` from the
`.json` computed by `auto_utilization.tcl`, overriding the defaults in the
`arguments` dict.
