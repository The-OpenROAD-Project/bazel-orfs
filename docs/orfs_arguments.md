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

## A way out of parameter guess, pray, stare at logs hell

The rest of this document is the API reference. This section is the
*why-it-matters* — written as a use-case write-up by a downstream user
who has been in the hole the title describes. It is opinionated; treat
it as one report from the field, not the canonical position of the
project.

### The frame: ORFS variable types

Upstream ORFS already classifies flow variables by *automation
potential* (see `OpenROAD-flow-scripts/docs/user/FlowVariables.md`,
"Types of variables"):

- **Trivial** — automatically determined by the tool with near-optimal
  results. Can be hidden from the user.
- **Easy** — requires input but easy to tune from reports or visuals.
  `PLACE_DENSITY` is the canonical example.
- **Complex** — small changes have large effects. `CTS_DISTANCE_BUF`
  is the canonical example.

The upstream documentation states:

> *It is an ongoing effort to move variables upwards in the categories
> below.*

`orfs_arguments` is one mechanism for that upward move. Instead of
"a human reads reports and updates a number", a Tcl script reads the
ODB and emits the number — turning an *Easy* variable into something
approaching *Trivial* for that flow, and giving *Complex* variables a
defensible computed seed instead of a static guess.

### The pain that motivates this

ORFS knobs like `CORE_UTILIZATION`, `CORE_MARGIN`, `SETUP_SLACK_MARGIN`,
and `HOLD_SLACK_MARGIN` are commonly set as static numbers in user
`BUILD.bazel` files. Two failure modes recur in real flows:

**Per-configuration drift.** A number that works for one configuration
does not work for another; every shape change re-opens tuning. In a
project with multiple variants of the same RTL family, this becomes a
per-variant table of magic numbers — `CORE_UTILIZATION` 15 / 20% per
variant, `CORE_MARGIN` flat 2 µm, `SETUP_SLACK_MARGIN` ranging from
−12000 to −30000 ps, and so on. The numbers drift out of date silently
as the RTL evolves. Every regression that touches floorplan or timing
becomes an exercise in re-tuning constants by hand.

**`SLACK_MARGIN=0` futile-loop.** If a stage emerges with positive
worst-slack but the next stage introduces violations, setting margin
to 0 makes `repair_timing` chase "≥ 0," which has been observed in
practice as hundreds of repair passes and an ODB-1200 crash on a
modest-sized CTS configuration. The fix is to compute
`min(slack, 0) − Δ` so a defined budget exists for the next stage to
work within.

### Two shipped scripts that move CORE_UTILIZATION, CORE_MARGIN, and SLACK_MARGINs upward

bazel-orfs ships two ready-to-use Tcl scripts at the repository root
that invoke through `orfs_arguments`:

#### `compute_floorplan_shape.tcl`

Emits `CORE_UTILIZATION` and `CORE_MARGIN` from the synth-stage ODB.

The utilization formula:

```
util = (std + macro) × target_density / (std × growth + macro)
```

`std` and `macro` are the standard-cell and macro/fixed-area sums in
the synthesised netlist. `growth` (default 1.40) accounts for the
std-cell expansion `repair_design` will perform. `target_density`
(default 0.225) is the post-repair placement density we want to land
at. The result is clamped to a documented range (default 5–50%).

Macros do not inflate during repair, so they appear as a fixed budget
in both the numerator and denominator — designs that are mostly
macros end up at the ceiling, designs that are mostly std cells end
up at the floor or near `target_density / growth`.

`CORE_MARGIN` is a die-size-aware floor: the historical 2 µm value
stays for small designs and scales mildly (default 0.5% of die linear
dimension) so big designs get more PDN-ring headroom.

#### `compute_slack_margin.tcl`

Emits `SETUP_SLACK_MARGIN` and `HOLD_SLACK_MARGIN` from the previous
stage's worst slack. The formula is `min(slack, 0) − Δ`, with
Δ = 1000 ps default for both setup and hold.

The script is identical regardless of which downstream stage will
consume the JSON — the destination is encoded only in the
`orfs_arguments` target name. Each invocation auto-discovers the
freshest ODB in the previous-stage `RESULTS_DIR`, so the same script
chains synth→floorplan, place→cts, cts→grt, etc.

The Δ default is data-validated: real flows have landed hold repair
within a fraction of a picosecond of the −1000 margin, indicating
Δ = 1000 ps is tight enough to be useful but loose enough to
converge.

### Parameterisation

Both scripts read all calibration constants from environment variables
with the values above as defaults. Override per-design via the
`arguments` attr on `orfs_arguments(...)`:

| Script | Env var | Default |
|---|---|---|
| floorplan_shape | `REPAIR_GROWTH_FACTOR` | `1.40` |
| floorplan_shape | `TARGET_POST_REPAIR_DENSITY` | `0.225` |
| floorplan_shape | `CORE_UTILIZATION_FLOOR_PCT` | `5.0` |
| floorplan_shape | `CORE_UTILIZATION_CEILING_PCT` | `50.0` |
| floorplan_shape | `CORE_MARGIN_FLOOR_UM` | `2.0` |
| floorplan_shape | `CORE_MARGIN_DIE_FRACTION` | `0.005` |
| slack_margin | `DELTA_SETUP_PS` | `1000` |
| slack_margin | `DELTA_HOLD_PS` | `1000` |

### Wiring

```python
load("@bazel-orfs//:openroad.bzl", "orfs_arguments", "orfs_flow")

orfs_arguments(
    name = "my_design_floorplan_shape",
    src = ":my_design_synth",
    script = "@bazel-orfs//:compute_floorplan_shape.tcl",
    arguments = {
        # all optional; shown here as defaults for documentation
        "REPAIR_GROWTH_FACTOR": "1.40",
        "TARGET_POST_REPAIR_DENSITY": "0.225",
    },
)

orfs_arguments(
    name = "my_design_floorplan_slack",
    src = ":my_design_synth",
    script = "@bazel-orfs//:compute_slack_margin.tcl",
)

orfs_arguments(
    name = "my_design_place_slack",
    src = ":my_design_floorplan",
    script = "@bazel-orfs//:compute_slack_margin.tcl",
)

orfs_flow(
    name = "my_design",
    extra_arguments = {
        "floorplan": [
            ":my_design_floorplan_shape",
            ":my_design_floorplan_slack",
        ],
        "place": [":my_design_place_slack"],
        # ... and so on for cts / grt
    },
    # ...
)
```

A worked example lives in `gallery/smoketest/BUILD.bazel`
(`counter` flow) and is exercised by the default-set test
`//smoketest:counter_computed_arguments_test`.

### Why design-specific calibration is the right boundary

Mechanism (read ODB, sum areas, query slack, emit JSON) is
universal — it lives in the upstream Tcl shipped here. Calibration
constants depend on **netlist structure** (macro:std ratio,
hierarchy depth, how aggressively `repair_design` will inflate
buffers in a given design), not technology. A generic "auto-X" rule
for everyone would either re-implement per-design Tcl in Starlark
or ship a heuristic that is wrong for half the customers. The split
this section advocates: ship the mechanism, parameterise the
constants, document calibration so users can recalibrate.

### Honest about the limits

- The shipped default constants are calibrated against one design
  family on one PDK. Portability is unproven. Downstream users
  should expect to recalibrate.
- The flow is one-shot per build. There is no closed loop that
  re-runs after route to check whether density actually landed in
  band. Building one would be a useful follow-on.
- The two scripts cover `CORE_UTILIZATION`, `CORE_MARGIN`, and
  `SETUP/HOLD_SLACK_MARGIN`. `PLACE_DENSITY` — the marquee *Easy*
  variable in the upstream taxonomy — is not (yet) computed; that
  is the natural next script.
- This is not autonomous. A human writes the heuristic, picks the
  defaults, and reads the logs to confirm the result is sensible.
  What the pattern removes is the requirement to re-do that work
  for every shape change of every variant.

### Composition with AutoTuner / DSE

AutoTuner (Ray Tune-driven, OpenROAD upstream) treats variables like
`CORE_UTILIZATION` as opaque hyperparameters and searches over them.
METRICS2.1 + the AutoTuner work shows the search finds good PPA but
is expensive (thousands of cloud runs).

Computed arguments are complementary: they give the search a
**measurement-grounded prior**. A starting point within a few
percent of the final answer instead of inside a 20–50% interval. The
two pair naturally — compute the seed; let AutoTuner explore the
local neighbourhood. The bazel-orfs README's DSE section already
gestures at external optimisers (Optuna, Vizier, hyperopt); none of
those mention seeding the search with a computed prior.

### Analogues in other long-running pipelines

The pattern is *measure → compute → re-stage*, which is structurally
familiar from other long-running engineering pipelines:

- **Seismic processing — iterative velocity analysis.** Velocity
  models are refined across passes: each pass measures residual
  move-out / image quality, computes a corrected velocity field,
  feeds it to the next migration. Modern variants use ML (FWI,
  deep-learning inversion); the classical version is purely
  heuristic/iterative — exactly the regime computed-argument
  scripts are in.
- **HLS DSE.** iDSE / Intelligent argue that *seeded* exploration
  beats blind sweeps; the computed-arguments pattern is the
  physical-design analogue.
- **NWP data assimilation.** Each cycle of a weather forecast
  computes a corrected initial condition from observations and
  hands it to the next forecast. Same shape.

The analogy is structural, not technical — none of these solve the
ORFS problem, and ORFS is not particularly close to any of them in
algorithmic detail. They are cited only to make the shape of the
pattern recognisable to readers from outside EDA.

### References

- `docs/user/FlowVariables.md#types-of-variables` in
  OpenROAD-flow-scripts — the Trivial / Easy / Complex taxonomy.
- AutoTuner: "Instructions for AutoTuner with Ray," OpenROAD-flow-
  scripts documentation; METRICS2.1 / Flow Tuning paper (UCSD).
- Velocity analysis: SEG Wiki article "Velocity analysis" and the
  classical iterative-migration literature (Yilmaz, *Seismic Data
  Analysis*).
- Practical Design Space Exploration, Nardi et al., 2018; iDSE,
  arXiv:2505.22086 (HLS-side seeded DSE).
