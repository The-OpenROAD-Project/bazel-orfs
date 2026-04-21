# bazel-orfs

This repository contains [Bazel](https://bazel.build/) rules for wrapping [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) (ORFS).

## Why Bazel on top of ORFS?

bazel-orfs gives all the expected Bazel advantages to ORFS: artifacts, parallel builds, remote execution, repeatable builds, etc.

Also, ORFS and OpenROAD is work in progress and you should expect for
large designs to get involved with the community or need a
support contract with [Precision Innovations](https://www.linkedin.com/in/tomspyrou/).

Using ORFS directly, instead of modifying it or creating an alternative flow,
makes it easy to get the very latest features and version of OpenROAD and ORFS
as well as having access to all ORFS features, including debugging
features such as `make issue` and `deltaDebug.py`.

Since bazel-orfs uses the unmodified ORFS, it is easy to articulate familiar
and easily actionable github issues for the OpenROAD and ORFS maintainers.

## Use cases

| I want to... | Go to |
|---|---|
| Run my first build | [Get started](#get-started) |
| Define a new design flow | [Define a design flow](#define-a-design-flow) |
| Add bazel-orfs to my project | [Use as an external dependency](#use-bazel-orfs-as-an-external-dependency) |
| View results in the OpenROAD GUI | [View results in the GUI](#view-results-in-the-gui) |
| Build with local ORFS | [Use the local flow](#use-the-local-flow) |
| Create macros with LEF/LIB | [Work with macros and abstracts](#work-with-macros-and-abstracts) |
| Quickly estimate macro sizes | [Mock area targets](#mock-area-targets) |
| Tweak floorplan or placement settings | [Tweak and iterate on designs](#tweak-and-iterate-on-designs) |
| Run a single substep (e.g. resizing) | [Substep targets](#substep-targets) |
| Reduce artifacts for stable designs | [Squashed flows](#squashed-flows) |
| Speed up CI or development builds | [Speed up your builds](#speed-up-your-builds) |
| Understand CI timing breakdown | [Where CI time goes](#where-ci-time-goes) |
| Query timing interactively | [Query timing interactively](#query-timing-interactively) |
| Monitor long-running builds | [Monitor long-running builds](#monitor-long-running-builds) |
| Sweep design parameters | [Design space exploration](#design-space-exploration) |
| Integrate Chisel designs | [chisel/README.md](chisel/README.md) |
| Pin slow-to-build artifacts | [tools/pin/README.md](tools/pin/README.md) |
| Debug or create issue archives | [Create a make issue archive](#create-a-make-issue-archive) |
| Upgrade bazel-orfs or ORFS | [Upgrade bazel-orfs](#upgrade-bazel-orfs) |
| Override configuration variables | [Override configuration variables](#override-configuration-variables) |

## Requirements

* [Bazelisk](https://bazel.build/install/bazelisk) or [Bazel](https://bazel.build/install) - if using Bazel, please refer to [.bazelversion](./.bazelversion) file for the recommended version of the tool.

That's it. Bazel builds OpenROAD, OpenSTA, Yosys, ABC, GNU Make, and Qt from source, and manages all other dependencies (Python, toolchains) hermetically. No Docker, no system packages beyond a standard Linux installation.

* (Optional) Locally built [ORFS](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts). To use it, `env.sh` file from OpenROAD-flow-scripts has to be sourced or `FLOW_HOME` environment variable has to be set to the path of the local `OpenROAD-flow-scripts/flow` installation.

## Get started

### Run your first build

To build the `cts` (Clock Tree Synthesis) stage of the `L1MetadataArray` target, run:

```bash
bazel run @bazel-orfs//test:L1MetadataArray_cts
```

Bazel automatically downloads the pre-built ORFS environment and runs the flow. Results are placed in the `tmp/results` directory under the workspace root.

### View results in the GUI

To open the OpenROAD GUI for a completed stage:

```bash
bazel run <target>_<stage> gui_<stage>
```

For example, to view the route stage of `L1MetadataArray`:

```bash
bazel run @bazel-orfs//test:L1MetadataArray_route gui_route
```

You can also run the build and view results in two steps:

```bash
bazel run @bazel-orfs//test:L1MetadataArray_route
# Start the GUI
tmp/test/L1MetadataArray_route/make gui_route

# Or open the CLI instead
tmp/test/L1MetadataArray_route/make open_route
gui::show
```

GUI and CLI are available for these stages: `floorplan`, `place`, `cts`, `grt`, `route`, `final`.

### Use the local flow

The local flow lets you build with a locally compiled [ORFS](https://openroad-flow-scripts.readthedocs.io/en/latest/user/UserGuide.html) instead of the pre-built ORFS image.

1. Source `env.sh` of your local ORFS installation or set the `FLOW_HOME` environment variable:

   ```bash
   source <ORFS_path>/env.sh
   # Or
   export FLOW_HOME=<ORFS_path>/flow
   ```

2. Initialize dependencies and run the stage:

   ```bash
   # Initialize dependencies for the synthesis stage
   bazel run //:deps -- //test:L1MetadataArray_synth

   # Build synthesis using local ORFS
   tmp/test/L1MetadataArray_synth_deps/make do-yosys-canonicalize do-yosys do-1_synth

   # Initialize dependencies for the floorplan stage
   bazel run //:deps -- //test:L1MetadataArray_floorplan

   # Build floorplan
   tmp/test/L1MetadataArray_floorplan_deps/make do-floorplan
   ```

> **NOTE:** The synthesis stage requires `do-yosys-canonicalize` and `do-yosys` to be completed before `do-1_synth`. These steps generate the required `.rtlil` file.

> **NOTE:** If `FLOW_HOME` is not set and `env.sh` is not sourced, `make do-<stage>` uses the ORFS from [MODULE.bazel](./MODULE.bazel) by default.

> **NOTE:** Files are always placed in `tmp/<package>/<name>_deps/` under the workspace root (e.g. `tmp/sram/sdq_17x64_floorplan_deps/` for `//sram:sdq_17x64_floorplan`, `tmp/MyDesign_floorplan_deps/` for the root package), which is added to `.gitignore` automatically.
>
> You can override the installation directory with `--install`:
>
> ```bash
> bazel run //:deps -- <target>_<stage> --install /path/to/dir [<make args...>]
> ```
>
> This is useful on systems where `/tmp` is small or when you want to place the build artifacts in a specific location.

You can also forward arguments to make directly:

```bash
bazel run //:deps -- <target>_<stage> <make args...>
```

### Parallel local builds

Multiple dependency deployments are independent and can run in parallel. This
is useful when building multiple designs or deploying all stages at once:

```bash
# Deploy and build two independent designs in parallel
bazel run //:deps -- //test:tag_array_64x184_synth &
bazel run //:deps -- //test:lb_32x128_synth &
wait

# Run synthesis in parallel (each in its own directory)
tmp/test/tag_array_64x184_synth_deps/make do-yosys-canonicalize do-yosys do-1_synth &
tmp/test/lb_32x128_synth_deps/make do-yosys-canonicalize do-yosys do-1_synth &
wait
```

You can also pre-deploy all stages of a single design for faster iteration:

```bash
# Deploy all stages at once (each deployment is independent)
for stage in synth floorplan place cts grt route final; do
  bazel run //:deps -- //test:L1MetadataArray_${stage} &
done
wait

# Now iterate on any stage without re-deploying
tmp/test/L1MetadataArray_floorplan_deps/make do-floorplan
tmp/test/L1MetadataArray_place_deps/make do-place
```

> **NOTE:** Each stage's `make` invocation still requires its input artifacts
> from the previous stage to be present, so the `make` commands must run
> sequentially. Only the dependency deployments (which just set up the directory
> structure) can run in parallel.

## Define a design flow

### Use bazel-orfs as an external dependency

To use `orfs_flow()` in another project, add bazel-orfs as a dependency through one of [Bazel Module Methods](https://bazel.build/rules/lib/globals/module):

From a git repository:

```starlark
bazel_dep(name = "bazel-orfs")
git_override(
    module_name = "bazel-orfs",
    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs.git",
    commit = "<git hash for specific bazel-orfs revision>",
)
```

From a local directory:

```starlark
bazel_dep(name = "bazel-orfs")
local_path_override(
    module_name = "bazel-orfs",
    path = "<path to local bazel-orfs workspace>",
)
```

### Tool configuration

bazel-orfs builds all EDA tools from source by default. This works on all
platforms and requires only Bazelisk — no Docker, no system packages.

KLayout defaults to a mock implementation since GDS output is the end of
the flow and not needed for most development. Override with a real klayout
when you need actual GDS files.

#### Build OpenROAD from source (default)

Add OpenROAD to your `MODULE.bazel`. Run `bazelisk run @bazel-orfs//:bump`
to auto-fill the latest commit, or specify a version manually:

```starlark
bazel_dep(name = "openroad")
git_override(
    module_name = "openroad",
    commit = "<openroad-commit-sha>",
    init_submodules = True,
    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",
)
bazel_dep(name = "qt-bazel")
git_override(
    module_name = "qt-bazel",
    commit = "df022f4ebaa4130713692fffd2f519d49e9d0b97",
    remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
)
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default()
use_repo(orfs, "gnumake")
```

First build takes 30-60 minutes; subsequent builds are incremental.
See [docs/openroad.md](docs/openroad.md) for details and gotchas.

#### Use locally installed tools

To use OpenROAD, yosys, or klayout from your system PATH:

```starlark
orfs.default(
    openroad = "@bazel-orfs//:openroad",  # uses `openroad` from PATH
)
```

The `@bazel-orfs//:openroad` and `@bazel-orfs//:klayout` targets are thin
wrappers that `exec` the corresponding binary from PATH.

#### Configure klayout

KLayout defaults to mock-klayout. To use a real klayout, add to `user.bazelrc`:

```
build --@bazel-orfs//:klayout=@bazel-orfs//:klayout
```

Or override globally in `MODULE.bazel`:

```starlark
orfs.default(
    klayout = "@bazel-orfs//:klayout",  # system klayout from PATH
)
```

#### Per-target overrides

Any tool can be overridden on individual targets:

```starlark
orfs_flow(
    name = "my_design",
    openroad = "@openroad//:openroad",
    klayout = "@bazel-orfs//:klayout",
    verilog_files = ["my_design.v"],
)
```

### Write an orfs_flow() target

Core functionality is implemented as `orfs_flow()` Bazel macro in `openroad.bzl` file. Place the macro in your BUILD file:

```starlark
orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "route",
    arguments = {
        "CORE_MARGIN": "2",
        "CORE_UTILIZATION": "3",
        "MACRO_PLACE_HALO": "30 30",
        "PLACE_DENSITY": "0.20",
        "PLACE_PINS_ARGS": "-annealing",
        "SYNTH_HIERARCHICAL": "1",
    },
    macros = ["tag_array_64x184_generate_abstract"],
    sources = {
        "SDC_FILE": [":constraints-top.sdc"],
    },
    verilog_files = ["rtl/L1MetadataArray.sv"],
)
```

This spawns the following Bazel targets:

```
Stage targets:
  //test:L1MetadataArray_synth
  //test:L1MetadataArray_floorplan
  //test:L1MetadataArray_place
  //test:L1MetadataArray_cts
  //test:L1MetadataArray_grt
  //test:L1MetadataArray_route
  //test:L1MetadataArray_generate_abstract
```

To deploy dependencies for local iteration, use the `//:deps` wrapper:

```bash
bazel run //:deps -- //test:L1MetadataArray_synth
```

The example is based on the [test/BUILD](./test/BUILD) file in this repository.

### Use variants

To test different variants of the same design, provide the optional `variant` argument:

```starlark
orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "route",
    macros = ["tag_array_64x184_generate_abstract"],
    # [...]
    variant = "test",
)
```

This creates targets with the variant appended after the design name:

```
Stage targets:
  //test:L1MetadataArray_test_synth
  //test:L1MetadataArray_test_floorplan
  ...
  //test:L1MetadataArray_test_generate_abstract
```

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

See [`patches/`](patches/) for examples of ORFS patches used by bazel-orfs.

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
    stage_sources = {
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
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
    stage_sources = LB_STAGE_SOURCES,
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
bazel build @bazel-orfs//test:L1MetadataArray_generate_abstract
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
bazel run @bazel-orfs//test:tag_array_64x184_floorplan gui_floorplan
```

### Substep targets

Each ORFS stage runs multiple substeps internally — e.g., the `place` stage
runs global placement, IO placement, resizing, and detailed placement as a
single Bazel action via `do-place`. You can run individual substeps by
passing the substep name as a make argument to `//:deps`:

```bash
# Deploy place artifacts and run only the resizing substep
bazel run //:deps -- //coralnpu:CoreMiniAxi_place do-3_4_place_resized

# Open GUI to inspect
bazel run //:deps -- //coralnpu:CoreMiniAxi_place gui_place

# After editing BUILD, re-deploy and re-run
bazel run //:deps -- //coralnpu:CoreMiniAxi_place do-3_4_place_resized
```

The `//:deps` wrapper builds all preceding stages (synth, floorplan, place)
automatically via `--output_groups=deps` before deploying artifacts, so you
never need to manually build the dependency chain.

#### Available substeps per stage

| Stage | Substeps |
|-------|----------|
| floorplan | `2_1_floorplan`, `2_2_floorplan_macro`, `2_3_floorplan_tapcell`, `2_4_floorplan_pdn` |
| place | `3_1_place_gp_skip_io`, `3_2_place_iop`, `3_3_place_gp`, `3_4_place_resized`, `3_5_place_dp` |
| cts | `4_1_cts` |
| grt | `5_1_grt` |
| route | `5_2_route`, `5_3_fillcell` |
| final | `6_1_merge`, `6_report` |

Substep names are defined once in `STAGE_SUBSTEPS` in `private/stages.bzl` —
the single source of truth from which log and JSON file names in stage rules
are derived.

> **NOTE:** The synth stage is not listed above because it uses a different
> execution model (Yosys, not OpenROAD). Synth has two internal operations
> (`1_1_yosys_canonicalize` and `1_2_yosys`) but they are handled as a
> single Bazel action with built-in dependency checking via `.rtlil`
> canonicalization.

#### Caching substep intermediates (`substeps = True`)

By default, stage actions only declare the final `.odb` as a Bazel output.
Intermediate substep `.odb` files are produced by make but not captured —
they vanish with the sandbox.

With `substeps = True`, each intermediate `.odb` is declared as an
additional action output in a per-substep output group (e.g.
`substep_2_1_floorplan`, `substep_3_4_place_resized`). This means:

- **Shared cache**: one developer (or CI) builds the stage, all
  intermediates go to the remote cache. Another developer can pull a
  specific substep's `.odb` instantly.
- **On-demand access**: `bazel build --output_groups=substep_3_3_place_gp //target`
  fetches just that intermediate from cache.
- **No target explosion**: all intermediates are output groups on the
  existing stage target, not separate targets.

```python
orfs_flow(
    name = "MyDesign",
    verilog_files = [...],
    substeps = True,  # capture intermediate .odb files
)
```

`substeps = False` (default) keeps the cache footprint minimal — enable it
for designs under active development where substep-level debugging benefits
from shared caching.

> **NOTE:** ORFS could grow a metadata file (beyond `variables.yaml`) that
> lists substep names, their scripts, and dependencies. This would make
> `STAGE_SUBSTEPS` truly derived from ORFS rather than maintained as a copy
> in bazel-orfs.

#### Common `//:deps` workflows

| I want to... | Command |
|---|---|
| Run a single substep | `bazel run //:deps -- <target>_<stage> do-<substep>` |
| View result in GUI | `bazel run //:deps -- <target>_<stage> gui_<stage>` |
| Run arbitrary make targets | `bazel run //:deps -- <target>_<stage> <make args...>` |
| Edit Tcl scripts and re-run without Bazel | `tmp/<pkg>/<target>_<stage>_deps/make do-<substep>` |
| Create a `make issue` archive | `bazel run //:deps -- <target>_<stage>` then `tmp/.../make <stage>_issue` |
| Use a local ORFS installation | `bazel run //:deps -- <target>_<stage>` with `FLOW_HOME` set |
| Run `make bash` for interactive debugging | `tmp/<pkg>/<target>_<stage>_deps/make bash` |

### Use remote caching for instant reverts

If remote caching is enabled for Bazel, reverting a change and rebuilding completes instantaneously because the artifact already exists:

```bash
# Revert the change
git restore test/BUILD

# Rebuild — instant cache hit
bazel run @bazel-orfs//test:tag_array_64x184_floorplan gui_floorplan
```

## Speed up your builds

### Disable expensive operations for CI and development

For CI or iterative development where timing closure isn't needed, you can
disable expensive operations. The `FAST_SETTINGS` dict in [test/BUILD](test/BUILD)
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

### Set abstract_stage as early as possible

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

### Squashed flows

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

### Query timing interactively

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

### Monitor long-running builds

ORFS stages can take minutes to hours. To monitor progress, find the active
OpenROAD processes and tail their log files.

**Step 1: Find what's running with `ps`**

```bash
# Find active openroad processes — the command line shows the script and log path
ps -Af | grep openroad | grep -v grep
```

Example output:

```
oyvind 2175870 ... openroad -exit ... flow/scripts/global_place.tcl -metrics .../3_3_place_gp.json
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

### Where CI time goes

The CI pipeline (`.github/workflows/ci.yml`) runs 6 jobs. The `test-make-target` job
is a matrix of 9 targets that run in parallel on separate runners. Use `--profile` and
`analyze-profile` to profile your own builds:

```bash
bazel build <target> --profile=/tmp/profile.gz
bazel analyze-profile /tmp/profile.gz
```

#### Smoketests (`bazel test ...`)

The smoketests job builds *everything* including sram, chisel, and sky130 targets.
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

#### test-make-target matrix

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

#### Per-design timing (single-design, synth through CTS with FAST_SETTINGS)

| Design | Synth | Floorplan | Place | CTS | Abstract | Total |
|--------|-------|-----------|-------|-----|----------|-------|
| lb_32x128 (small) | 5s | 7s | 15s | 3s | - | 25s |
| tag_array_64x184 | 21s | 22s | 225s | 12s | 5s | 280s |
| sdq_17x64 (megaboom) | 37s | 28s | 298s | - | 9s | 362s |
| L1MetadataArray (hierarchical) | 16s | 19s | 135s | 8s | 3s | 181s |

Each OpenROAD sub-step has a minimum startup overhead of ~1.3s (loading the database,
reading libraries). For small designs, this overhead dominates. For large designs,
`global_place` dominates instead — it accounts for 50-85% of the placement stage.

### Force a cache miss for testing

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

### Debug cache misses

Use `--explain` to understand why Bazel is rebuilding a target:

```bash
bazel build <target> --explain=/tmp/explain.txt --verbose_explanations
```

Avoid `bazel clean --expunge` — it forces a full rebuild. If you need to force-rebuild
one target, use the [`PHONY` variable trick](#force-a-rebuild) instead.

### CI optimization opportunities

Potential improvements to the bazel-orfs CI pipeline:

- **Placement dominates**: 50-85% of build time is `global_place`. ORFS upstream
  improvements to placement speed would have the largest impact.
- **Duplicate builds across packages**: `subpackage/` targets rebuild the same
  designs as `test/`, but in a separate Bazel package. The `test-make-target` matrix
  runs them on separate runners without shared caches.
- **Consolidate FAST_SETTINGS**: Three copies exist in `test/BUILD`, `sram/BUILD`,
  and `subpackage/BUILD`. A shared `.bzl` file would prevent drift.
- **STA-1554 warning flood**: tag_array_64x184 emits ~1000 `STA-1554` warnings
  ("not a valid start point") per placement stage. These are harmless but slow
  down log processing. Fixing the SDC constraints would eliminate them.
- **OpenROAD startup overhead**: Each sub-step takes ~1.3s minimum for database/library
  loading. For small designs, this overhead is significant. ORFS sub-step consolidation
  would help.
- **`SKIP_REPORT_METRICS=1` for all CI targets**: Already applied via FAST_SETTINGS.
  Metrics reporting adds minutes per stage on large designs.

## Design space exploration

bazel-orfs supports design space exploration (DSE) by parameterizing
`orfs_flow()` targets with Bazel build settings. This lets you sweep or
optimize parameters like core utilization and placement density across
multiple flow instances, with Bazel handling parallelism and caching.

**Use-case:** Find parameter combinations (utilization, density, clock period,
macro placement, etc.) that optimize area, timing, or power for a given design.

**How it works:**

1. Declare parameters as `string_flag` build settings
2. Map them to ORFS variables via `orfs_flow(settings = {...})`
3. Create N parallel flow instances using list comprehensions
4. Invoke with overrides: `bazel build --//pkg:density0=0.7 --//pkg:util0=40 //pkg:design_0_place`

The `orfs_sweep` macro in `sweep.bzl` wraps this pattern for common cases.

Parameters only propagate to relevant stages — changing `PLACE_DENSITY` does not
invalidate the synthesis cache.

**External optimizers:** Any optimizer (Optuna, Vizier, hyperopt, etc.) can drive
DSE by scripting `bazel build` invocations with different `--//pkg:flag=value`
arguments and parsing PPA metrics from the build outputs.

### Examples

<!-- Add links to DSE example repos or PRs here -->

## Additional tools and integrations

| Tool | Description | Documentation |
|------|-------------|---------------|
| Chisel integration | Build Chisel designs, run tests | [chisel](chisel/README.md) |
| Artifact pinning | Cache long-running build results | [tools/pin](tools/pin/README.md) |
| Post-synthesis cleanup | najaeda netlist cleaning (experimental) | [naja](naja/README.md) |
| SRAM macros | fakeram and mock SRAM | [sram](sram/README.md) |
| Equivalence checking (LEC) | kepler-formal logic equivalence | [lec](lec/README.md) |
| Verilog generation | FIRRTL-to-SystemVerilog via firtool | [verilog](verilog/README.md) |

### Sub-modules

Several tools live in subdirectories that are **separate Bazel modules**.
Downstream consumers must add their own `bazel_dep` and `git_override` for each
sub-module they use:

| Sub-module directory | Bazel module name | What it provides |
|----------------------|-------------------|------------------|
| `verilog/` | `bazel-orfs-verilog` | `verilog_files`, `fir_library` rules |
| `lec/` | `bazel-orfs-lec` | Logic equivalence checking |

Example for adding `bazel-orfs-verilog` to a downstream `MODULE.bazel`:

```starlark
bazel_dep(name = "bazel-orfs-verilog")

git_override(
    module_name = "bazel-orfs-verilog",
    commit = "<same commit as bazel-orfs>",
    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs",
    strip_prefix = "verilog",
)
```

## Reference

### Stage targets

Each stage of the physical design flow is represented by a separate target following the naming convention `<target>_<stage>`.

The stages are:

* `synth` (synthesis)
* `floorplan`
* `place`
* `cts` (clock tree synthesis)
* `grt` (global route)
* `route`
* `final`
* `generate_abstract`

Individual substeps within a stage can be run via the `//:deps` wrapper.
See [Substep targets](#substep-targets).

### Dependency deployment

Dependencies are deployed using the `//:deps` wrapper, which uses `--output_groups=deps` to build and deploy stage artifacts:

```bash
bazel run //:deps -- <target>_<stage>
```

This prepares the environment for running ORFS stage targets locally. The deploy directory follows the naming convention `tmp/<package>/<target>_<stage>_deps/`.

Each stage depends on two generated `.mk` files that provide the ORFS configuration:

```bash
<path>/config.mk                                                             # Common for the whole design
<path>/results/<module>/<target>/<variant>/<stage_number>_<stage>.short.mk   # Specific for the stage
```

Additionally, the dependency targets generate shell scripts for running ORFS stages in both the Bazel and local flows:

```bash
<path>/make     # Running the ORFS stages
<path>/results  # Directory for the results of the flow
<path>/external # Directory for the external dependencies
```

### GUI and CLI targets

GUI and CLI targets can only be run from the generated shell script.

For the GUI:

```bash
bazel run <target>_<stage> gui_<stage>
```

For the CLI:

```bash
bazel run <target>_<stage> open_<stage>
```

GUI and CLI are available for: `floorplan`, `place`, `cts`, `grt`, `route`, `final`.

### orfs_genrule

`orfs_genrule` is a drop-in replacement for Bazel's native `genrule` that keeps
`srcs` and `tools` in the **exec** configuration (`cfg = "exec"`).

Native `genrule` forces `srcs` into the **target** configuration. When `srcs`
reference targets produced by ORFS rules (which always build in the exec
configuration), this configuration mismatch causes the entire ORFS pipeline —
synthesis, placement, routing — to be **rebuilt a second time** under the target
configuration. For large designs this can add hours to the build.

`orfs_genrule` avoids this by matching the configuration where ORFS outputs
already live. Use it for any post-processing rule (reports, plots, CSV
transformations) whose inputs come from `orfs_flow` or `orfs_synth` targets.

It supports the same `cmd` substitutions as native `genrule`:
`$(location)`, `$(execpath)`, `$(SRCS)`, `$(OUTS)`, `$<`, `$@`, `$$`.

```starlark
load("@bazel-orfs//:orfs_genrule.bzl", "orfs_genrule")

orfs_genrule(
    name = "my_report",
    srcs = [":MyDesign_synth_report"],
    outs = ["my_report.csv"],
    cmd = "$(execpath :my_script) --input $< --output $@",
    tools = [":my_script"],
)
```

### How Bazel replaces ORFS Makefile dependencies

When using bazel-orfs, dependency checking is done by Bazel instead of ORFS's Makefile, with the exception of the synthesis canonicalization stage.

ORFS `make do-yosys-canonicalize` is special and does dependency checking using the ORFS `Makefile`, outputting `$(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil`.

The `.rtlil` is Yosys's internal representation format of all the various input files that went into Yosys, however any unused modules have been deleted and the modules are in canonical form (ordering of the Verilog files provided to Yosys won't matter). However, `.rtlil` still contains line number information for debugging purposes. The canonicalization stage is quick compared to synthesis and adds no measurable overhead.

Canonicalization simplifies specifying `VERILOG_FILES` to ORFS in Bazel: simply glob them all and let Yosys figure out which files are actually used. This avoids redoing synthesis unnecessarily if, for instance, a Verilog file related to simulation changes.

The next stage is `make do-yosys` which does no dependency checking, leaving it to Bazel. `do-yosys` completes the synthesis using `$(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil`.

The subsequent ORFS stages are run with `make do-floorplan do-place ...` and these stages do no dependency checking, leaving it to Bazel.

bazel-orfs also does dependency checking of options provided to each stage. If a property to CTS is changed, then no steps ahead of CTS are re-run. bazel-orfs does not know which properties belong to which stage; it is the responsibility of the user to pass properties to the correct stage. This includes some slightly surprising responsibilities, such as passing IO pin constraints to both floorplan and placement.

### openroad.bzl internals

The `openroad.bzl` file contains simple helper functions written in Starlark as well as the `orfs_flow()` macro.
The implementation of this macro spawns multiple `genrule` native rules which are responsible for preparing and running ORFS physical design flow targets during the Bazel build stage.

These are the genrules spawned in this macro:

* ORFS stage-specific (named: `target_name + "_" + stage` or `target_name + "_" + variant + "_" + stage`)

Dependency deployment is handled via the `deps` output group on stage targets, accessed through the `//:deps` wrapper.

### Bazel flow

The ORFS flow scripts (Makefile, TCL scripts, PDKs) are fetched from the
[OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
repository via `git_override` in `MODULE.bazel`. All EDA tools default to
mock implementations for fast iteration; override with real tools for
production builds (see [Tool configuration](#tool-configuration) above).

```bash
bazel build <target>_<stage>
```

### Tools location after bazel run

A mutable build folder can be set up to prepare for a local synthesis run, useful when digging into some detail of the synthesis flow:

    $ bazel run //:deps -- //test:tag_array_64x184_synth

### Create a make issue archive

To create and test a `make issue` archive for floorplan:

    bazel run //:deps -- //test:lb_32x128_floorplan
    tmp/test/lb_32x128_floorplan_deps/make ISSUE_TAG=test floorplan_issue

This results in `tmp/test/lb_32x128_floorplan_deps/floorplan_test.tar.gz`, which can be run provided the `openroad` application is in the path.

You can use a local ORFS installation by running `source env.sh`.

Alternatively, use the ORFS installation from Bazel by running `make bash` to set up the environment:

    tmp/test/lb_32x128_floorplan_deps/make bash
    export PATH=$PATH:$(realpath $(dirname $(readlink -f $OPENROAD_EXE)))
    tar --strip-components=1 -xzf ../floorplan_test.tar.gz
    ./run-me-lb_32x128-asap7-base.sh

### Run all synth targets

```bash
bazel query :\* | grep '_synth$' | xargs -I {} bazel run {}
```

This runs all synth targets in the workspace and places the results in the `tmp/results` directory.

### Build the immediate dependencies of a target

```bash
bazel build --output_groups=deps @bazel-orfs//test:L1MetadataArray_synth
```

This builds the immediate dependencies of the `L1MetadataArray` target up to the `synth` stage and places the results in the `bazel-bin` directory.
Later, those dependencies are used by Bazel to build the `synth` stage for the `L1MetadataArray` target.

## Upgrade bazel-orfs

    bazelisk run @bazel-orfs//:bump

A single command that updates all version pins in your `MODULE.bazel` and
runs `bazelisk mod tidy`. It detects which project it's running in and does
the right thing — no need to remember which versions to update or where.

What it updates:

- **ORFS image** tag and sha256 (latest from the OCI registry)
- **bazel-orfs** git commit (latest from GitHub)
- **OpenROAD** git commit (latest from GitHub, if configured)

In downstream projects, it also injects commented-out boilerplate for
[building OpenROAD from source](docs/openroad.md) — uncomment to test the
latest OpenROAD before the ORFS image catches up. This is useful when an
OpenROAD bug fix or feature hasn't made it into the ORFS image yet.

## Repository layout

The root directory contains only external-facing concerns:

- `.bzl` rule files (`openroad.bzl`, `sweep.bzl`, `ppa.bzl`, etc.) loaded by downstream consumers
- `MODULE.bazel` and `BUILD` with public tools (`bump`, `plot_clock_period_tool`)
- Template files consumed by rules (`make.tpl`, `deploy.tpl`, `mock_area.tcl`)
- `tools/` (pin, deploy), `extensions/` (pin)

Test and demo content lives in subdirectories:

- `test/` — CI test flows (tag_array_64x184, lb_32x128, L1MetadataArray, etc.) and supporting files
- `sram/` — SRAM macro tests with fakeram and megaboom variants
- `subpackage/` — cross-package reference tests
- `chisel/` — Chisel integration tests

### Trivial test files

Most files under `test/` are short implementation details easily derived from
context. The TCL scripts (`cell_count.tcl`, `check_mock_area.tcl`, `report.tcl`,
`units.tcl`, `io.tcl`, `io-sram.tcl`, `fastroute.tcl`), SDC constraint files,
and simple RTL (`Mul.sv`, `lb_32x128_top.v`) are boilerplate — an LLM can
regenerate them from the BUILD target definitions.

Non-trivial files worth understanding: `wns_report.py` (complex report parsing),
`L1MetadataArray.sv` (cache metadata controller), and the plot scripts.

## Retired features

Features removed from bazel-orfs. Check git history for the original implementation.

- **netlistsvg** — SVG schematic generation from Yosys JSON netlists. Removed
  along with all JavaScript dependencies (`aspect_rules_js`, `rules_nodejs`,
  `npm`, `pnpm`). See `netlistsvg.bzl`, `main.js` in git history.
- **optuna/** — Multi-objective Bayesian optimization (Optuna TPE) for hardware
  DSE with multi-fidelity (synth→place→grt) progressive refinement. Included a
  parameterized `mock-cpu.sv` test design. See `optuna/` in git history.
- **dse/** — Bazel-native DSE example using `string_flag` build settings with
  `orfs_flow(settings = {...})` to sweep utilization and density. The pattern
  is now documented in the DSE section above. See `dse/` in git history.

### Deprecated

- **yosys.bzl** — standalone Yosys rule. Still present but unused in CI.
  Superseded by the synthesis stage in `orfs_flow`.

## Feature history

Development timeline generated from `git --numstat` (actual files changed, not
just commit messages). Bar opacity reflects lines of code changed. Numbers show
total LOC changed and commit count per activity.

![bazel-orfs Development Timeline](docs/gantt.png)

<!-- To regenerate: python docs/generate_gantt.py -o docs/gantt.png
     To update activities: edit docs/gantt_activities.yaml then regenerate -->
