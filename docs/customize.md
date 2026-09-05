# Configure, customize and iterate

How to pass variables and constraints to a flow, generate macro abstracts,
iterate on floorplan and placement settings, and sweep parameters.
Snippets refer to `//test:...` targets from a clone of this repository;
[examples/](../examples/) has the clean starting point.

## Configure and customize

### Override configuration variables

You can override configuration variables on the command line by passing them as arguments:

```bash
$ bazel run //test:tag_array_64x184_floorplan print-CORE_UTILIZATION
[deleted]
CORE_UTILIZATION: 20
```

```bash
$ bazel run //test:tag_array_64x184_floorplan CORE_UTILIZATION=5 print-CORE_UTILIZATION
[deleted]
CORE_UTILIZATION: 5
```

### Variable validation against `variables.yaml`

bazel-orfs validates all variable names in `arguments` and `sources` against
ORFS `flow/scripts/variables.yaml` at build time. Misspelled or unknown
variables cause an immediate build failure with a clear error message, catching
typos before they silently propagate to runtime.

If a variable is not in `variables.yaml` but is needed for your design:

1. **Create a patch against ORFS** for your project that adds the variable to
   `variables.yaml`. This is the recommended approach — patches make the
   implementation very straightforward and the only cost is occasionally
   updating `variables.yaml` with a variable you need from bazel-orfs.

2. Alternatively, we sometimes add the variable in bazel-orfs first and then
   **file a PR against ORFS** with an updated `variables.yaml`.

See [`patches/`](../patches/) for examples of ORFS patches used by bazel-orfs.

### Pass constraints to stages

Pass constraint files to `orfs_flow()` through `sources`:

```starlark
orfs_flow(
    name = "tag_array_64x184",
    sources = {
        "SDC_FILE": [":constraints-sram"],  # constraint file label
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)
```

If your constraints file includes additional TCL scripts, define them in a filegroup with the `data` attribute:

```starlark
filegroup(
    name = "constraints-sram",
    srcs = [
        ":constraints-sram.sdc",
    ],
    data = [
        ":util.tcl",  # additional TCL script
    ],
    visibility = [":__subpackages__"],
)
```

### Force a rebuild

Sometimes it is desirable, such as when hacking ORFS, to redo a build stage even
if none of the dependencies for that stage changed. You can achieve this by adding
a `PHONY` variable to that stage and bumping it:

```diff
diff --git a/test/BUILD b/test/BUILD
--- a/test/BUILD
+++ b/test/BUILD
 orfs_flow(
     name = "L1MetadataArray",
     abstract_stage = "route",
     arguments = {
+        "PHONY": "1",
         "SYNTH_HIERARCHICAL": "1",
         ...
     },
```

### Hierarchical synthesis: discovered or pinned kept modules

`SYNTH_HIERARCHICAL=1` synthesizes the kept modules in parallel, one
yosys process per partition. Which modules are kept is decided one of two
ways:

- **Discovered** (no `SYNTH_KEEP_MODULES`): `synth_keep.tcl` runs ORFS's
  keep decision, `keep_hierarchy -min_cost $SYNTH_MINIMUM_KEEP_SIZE`, at
  build time, and a static 32 partitions divide the result. This is what
  most hierarchical ORFS designs do, and it needs nothing from you.
- **Pinned** (`SYNTH_KEEP_MODULES = a b c`): one partition and one
  re-canonicalized RTLIL slice per named module. An RTL edit then re-runs
  only the partitions whose module changed; in discovery mode every
  partition re-runs, because none can key on a per-module slice.

So pinning is a caching optimisation for a design you iterate on, not a
requirement. To capture the list ORFS would discover:

```sh
make DESIGN_CONFIG=<config.mk> SYNTH_KEEP_MODULES= clean_synth synth
cat results/<platform>/<design>/base/kept_modules.json
```

and paste the names into `SYNTH_KEEP_MODULES` in the design's config.mk
or `arguments`. `asap7/swerv_wrapper` in ORFS is the worked example. The
list drifts with the RTL: a renamed or removed module fails synthesis
with a clear message rather than silently flattening.

## Work with macros and abstracts

### Generate abstracts

Abstracts (`.lef` and `.lib` files) are generated at the `<target>_generate_abstract` stage, which follows the stage defined via the `abstract_stage` attribute:

```starlark
orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "place",  # generate abstracts after this stage
    arguments = SRAM_ARGUMENTS | {
        "CORE_ASPECT_RATIO": "2",
        "CORE_UTILIZATION": "40",
        "PLACE_DENSITY": "0.65",
    },
    sources = {
        "IO_CONSTRAINTS": [":io-sram"],
        "SDC_FILE": [":constraints-sram"],
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)
```

By default, `abstract_stage` is set to `final` (the latest ORFS stage).

> **NOTE:** Abstracts can be generated starting from the `place` stage, because pin placement happens during the place stage. The legal values for `abstract_stage` are: `place`, `cts`, `grt`, `route`, `final`.

Abstracts are useful for estimating sizes of macros with long build times and checking if they fit in upper-level modules without running the full place and route flow.

> **NOTE:** Stages that follow the one passed to `abstract_stage` are not created by `orfs_flow()`.

### Mock area targets

Mock area targets override `_generate_abstract` to produce mocked abstracts with the same pinout as the original macro but with a scaled size. This is useful in early design stages.

The flow contains:
* `<target>_synth_mock_area` — synthesis with internal logic removed
* `<target>_mock_area` — reads `DIE_AREA` and `CORE_AREA` from the default floorplan and scales them by `mock_area`
* `<target>_floorplan_mock_area` — floorplan with overridden `DIE_AREA` and `CORE_AREA`
* `<target>_generate_abstract` — abstracts generated from mocked synthesis and floorplan

To create mock area targets, add `mock_area` to your `orfs_flow` definition:

```starlark
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    mock_area = 0.5,
    sources = LB_SOURCES,
    verilog_files = LB_VERILOG_FILES,
)
```

### Fast floorplanning with mock abstracts

To skip cts and route and create a mock abstract where you can check that macros fit at the top level, set `abstract_stage` to `place`:

> **WARNING:** Although mock abstracts can speed up turnaround times, skipping place, cts, or route can lead to errors that don't exist when these stages are run.

```diff
diff --git a/test/BUILD b/test/BUILD
--- a/test/BUILD
+++ b/test/BUILD
 orfs_flow(
     name = "L1MetadataArray",
-    abstract_stage = "route",
+    abstract_stage = "place",
     arguments = {
         ...
     },
```

You can verify the generated targets with `bazel query`:

```bash
bazel query '...:*' | grep 'L1MetadataArray'

//test:L1MetadataArray_synth
//test:L1MetadataArray_floorplan
//test:L1MetadataArray_generate_abstract
```

The abstract target always follows the `<target>_generate_abstract` naming pattern:

```bash
bazel build //test:L1MetadataArray_generate_abstract
```

The output `LEF` file can be found under `bazel-bin/results/<module>/<target>/base/<target.lef>`.

## Tweak and iterate on designs

### Adjust floorplan parameters

The `CORE_ASPECT_RATIO` parameter is a floorplan variable, so
changing it only rebuilds from the floorplan stage:

```diff
diff --git a/test/BUILD b/test/BUILD
--- a/test/BUILD
+++ b/test/BUILD
 orfs_flow(
     name = "tag_array_64x184",
     arguments = SRAM_ARGUMENTS | {
-        "CORE_ASPECT_RATIO": "10",
+        "CORE_ASPECT_RATIO": "4",
         "CORE_UTILIZATION": "20",
     },
```

Bazel detects this change specifically as a change to the floorplan, re-uses the synthesis result, and rebuilds from the floorplan stage.
Similarly, if `PLACE_DENSITY` is modified, only stages from placement onward are rebuilt.

To apply and view the changes:

```bash
# Build and view in GUI
bazel run //test:tag_array_64x184_floorplan gui_floorplan
```

## Design space exploration

bazel-orfs supports design space exploration (DSE) by fanning out
`orfs_flow()` variants in the BUILD file — see the `orfs_sweep` macro in
`sweep.bzl` — with Bazel handling parallelism and caching.

**Use-case:** Find parameter combinations (utilization, density, clock period,
macro placement, etc.) that optimize area, timing, or power for a given design.

Parameters only propagate to relevant stages — changing `PLACE_DENSITY` does not
invalidate the synthesis cache.

**External optimizers:** Use the `orfs_run_executable` rule to compile a
standalone Make wrapper — a binary that invokes the underlying tool (e.g.
OpenROAD) directly with `KEY=VALUE` variable overrides. Bazel builds the
wrapper and its inputs once; the optimizer (Optuna, Vizier, hyperopt, etc.)
then drives the wrapper in its inner loop. Do not script `bazel build`
invocations from the optimizer instead: Bazel and a trial loop are a poor
impedance match — per-trial server and analysis overhead, and every variable
override invalidates the cache for all stages that read it.

See the `orfs_run_executable` rule docstring in `private/rules.bzl` for important execution constraints regarding logging, output directories, and parallel invocations.

When trials share a common flow prefix (a decision *tree* rather than a flat
list), a run script can walk the whole tree in one OpenROAD process with the
`fork` snapshot idiom, paying each shared stage once and writing one result
file per leaf into an output folder (`orfs_run(out_dir = ...)` /
`$RUN_OUTPUT_DIR`). See [fork.md](fork.md).

```python
# In your bazel-run Python script or objective function:
import os
import subprocess
import tempfile

# Drive the compiled wrapper directly with KEY=VALUE overrides.
# Absolute paths: the executable runs inside its own runfiles directory.
# A per-invocation LOG_DIR keeps runfiles pristine and keeps parallel
# trials from overwriting each other's run.log.
trial_dir = tempfile.mkdtemp()
result = subprocess.run(
    [
        "path/to/my_run_executable",
        "PLACE_DENSITY=0.6",
        f"LOG_DIR={trial_dir}",
        f"METRICS_OUT={trial_dir}/metrics.json",
    ],
    capture_output=True, text=True, check=True
)
```

**Computed arguments — a precursor to DSE.** Before sweeping a parameter, it is
often cheaper to *compute* a defensible value from the synthesised netlist or
prior-stage ODB. bazel-orfs ships two ready-to-use Tcl scripts at the repository
root for this — `compute_floorplan_shape.tcl` (emits `CORE_UTILIZATION` /
`CORE_MARGIN`) and `compute_slack_margin.tcl` (emits
`SETUP_/HOLD_SLACK_MARGIN`) — both invoked through the existing `orfs_arguments`
rule. Computed arguments and AutoTuner compose: compute the seed, then let an
external optimizer explore the local neighbourhood. See
[orfs_arguments.md](orfs_arguments.md#a-way-out-of-parameter-guess-pray-stare-at-logs-hell)
for the longer write-up.

### Examples

[test/estimation_ladder](../test/estimation_ladder/) is a worked example: an
out-of-Bazel Optuna study drives a fast estimator built with
`orfs_run_executable`, trading estimator runtime against clock-period
estimation accuracy, with an `orfs_flow` global-route flow as ground truth.
