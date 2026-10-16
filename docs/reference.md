# Reference

Target naming, dependency deployment, GUI and CLI entry points, and how
Bazel takes over dependency tracking from the ORFS Makefile.

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

Individual substeps within a stage can be run in a tree deployed by `//:deps`.
See [Substep targets](local-flow.md#substep-targets).

### Dependency deployment

Dependencies are deployed with `//:deps`, which builds everything the stage needs (every earlier stage) and installs it, with the stage's scripts, in one tree per flow:

```bash
bazelisk run //:deps -- start <flow> <stage>   # e.g. //test:lb_32x128 place
<tree>/make do-<stage>
```

This prepares the environment for running ORFS stage targets locally. The tree is `tmp/<package>/<flow>[_<variant>]/` by default, or `--dir`. `next <stage>` carries a hand-run stage into the next in the same tree, `status` says what in the tree was run by hand, and `archive <flow> <stage> <file.tar.gz>` writes a self-contained reproducer. See [Local flow and substeps](local-flow.md).

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

See `orfs_genrule.bzl` for the rule docstring and usage. It is a drop-in replacement for Bazel's native `genrule` that correctly separates executable tools from data srcs (putting tools in the `exec` configuration) and allows `select()` in `srcs`.

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

### The ORFS Makefile contract

Make is a rich programming language behind a terse syntax: recursive and simple expansion, `=` against `:=` against `?=`, the origin of a variable, exports to sub-makes, a graph built in one pass and run in another. ORFS keeps `flow/Makefile` as simple as it can, and over time a handful of conventions have grown up that keep it that way. Most of them were never written down. This section writes them down as rules an automated review can check an AI's change to the Makefile against.

The rules are hard stops: a change that breaks one is wrong, whatever else it fixes. Each rule says what breaks when it is broken. Paths and names in a rule are ORFS's, under `flow/`. A line marked "In bazel-orfs" names files and functions in the bazel-orfs repository, which ORFS does not have; code there that depends on a rule points to this section.

#### Targets

- **A `do-` target never builds anything.** It runs its one step on the files already in the tree. Its prerequisites are checks (`check-kepler-formal`), the step's source files and one-time markers (`$(OBJECTS_DIR)/copyright.txt`): never an order-only prerequisite, never a file another target writes.
  Breaks: a flow that runs each `do-` target alone in a fresh tree rebuilds the prerequisite every time.
  In bazel-orfs: every stage action is such a fresh tree, a Bazel sandbox holding only that stage's declared inputs.
  In bazel-orfs: each stage action runs the `do-` targets listed in `make_targets` (`bazel-orfs/private/stages.bzl`).
- **Dependencies live only on the file targets and stage aliases** (`$(RESULTS_DIR)/2_1_floorplan.odb`, `synth`, `floorplan`, ...), never on a `do-` target. `do-yosys-canonicalize` is the one `do-` target that checks dependencies in make.
  In bazel-orfs: never calls a file target or a stage alias. The deployed-tree guard in `bazel-orfs/make.tpl` refuses one (`bazel-orfs/test/make_stage_guard_test.sh`).
- **`open_*`, `gui_*`, `web_*` and `run` never build anything.** `run` writes `$(LOG_DIR)/$(RUN_LOG_NAME_STEM).log` and nothing under `RESULTS_DIR`, `REPORTS_DIR` or `OBJECTS_DIR`.
  Breaks: a caller that runs several `make run` at once on one tree gets them writing the same files.
  In bazel-orfs: `orfs_run` and `orfs_run_executable` (`bazel-orfs/private/rules.bzl`) and the odb-debug server (`bazel-orfs/private/odb_debug.bzl`) run `make run` from Bazel's runfiles tree; `orfs_run_executable` runs concurrent trials on one tree.
- **The graph never depends on a variable.** No `ifeq` chooses which steps run or which files they write. A step with nothing to do for a design runs anyway and copies its `.odb` and `.sdc` through; the choice is made in its `.tcl`.
  Breaks: a flow that names a step's outputs before running it gets a different set for each design.
  In bazel-orfs: Bazel declares each stage's outputs before the action runs, and fails an action that does not write one.

#### Steps

- **A step never writes next to its inputs or into one.** It writes new files under names of its own, as `2_floorplan.odb` → `3_place.odb`.
  Breaks: a rerun reads what the last run wrote, and a flow that keeps inputs read-only cannot run the step.
  In bazel-orfs: a stage's inputs are read-only, and its outputs are files of its own.
- **A step never skips an output because the file exists.** "Up to date" is the make flow's file target's decision.
  Breaks: a tree that kept a file from an earlier run and a fresh tree give different results.
- **A step never reads a file it does not declare.**
  Breaks: it works under `make synth`, where an earlier target happened to build the file, and fails when the step runs alone.
  In bazel-orfs: a stage's inputs are what `source_inputs`, `data_inputs` and `flow_inputs` (`bazel-orfs/private/environment.bzl`) declare.
- **A step never reads an input it does not use.**
  Breaks: every change to that input reruns the step and every step after it.
- **A step never leaves configuration for a later step.** A command gets its options in its own `log_cmd` line; a setting it needs is set right before the call and reset right after. State that crosses steps is in the `.odb` or another result file.
  Breaks: the later step's log does not show what it ran with, and a checkpoint changes when the design did not.
- **A step never draws an unseeded random number.** The seed comes from a variable and is recorded.
  Breaks: caching a step's result, the QoR check against a baseline, and bisecting a regression.
- **A failing step never calls `exit`.** It writes `<step>-failed.odb` and calls `error`, as `flow/scripts/global_place.tcl` does.
- **A `PRE_<STEP>_TCL` hook never runs before the design is loaded.** Hooks run through `source_step_tcl` in `flow/scripts/util.tcl`.

#### Variables

- **A variable a design sets is never assigned with `=` in the Makefile.** It is assigned with `?=`. A flow that passes a design's variables in `DESIGN_CONFIG` as `export VAR?=value` lines is overridden by `=`. `RUN_CMD` in `flow/scripts/variables.mk` is the exception; it can be set only on the make command line.
  In bazel-orfs: every stage's variables arrive as `export VAR?=value` lines in a generated `stage.args.mk` (`bazel-orfs/docs/orfs_arguments.md`, "Precedence"); `log_timestamps_make_arg` (`bazel-orfs/private/environment.bzl`) sets `RUN_CMD` on the command line.
- **A variable the environment supplies is never exported with `export VAR := $(VAR)`.** It is exported bare, `export VAR`, and its default is a `?=` fallback to the in-tree install. `:=` rebinds it to origin "file", `UNSET_AND_MAKE` unsets it before the sub-make, and the fallback fires there with an in-tree path that a flow supplying its own tools does not have (the "HERE BE DRAGONS" comment in `flow/scripts/variables.mk`).
  In bazel-orfs: `flow_environment` and `yosys_environment` (`bazel-orfs/private/environment.bzl`) and `bazel-orfs/make.tpl` set `OPENROAD_EXE`, `OPENSTA_EXE`, `YOSYS_EXE`, `PYTHON_EXE` and `KLAYOUT_CMD` in the environment.
- **Only the Makefile sets `RESULTS_DIR`, `LOG_DIR`, `REPORTS_DIR` and `OBJECTS_DIR`.** It derives them from `WORK_HOME`, which a flow sets. A variable a flow adds never reuses one of these names.
  In bazel-orfs: sets `WORK_HOME`, and names its own output directory `RUN_OUTPUT_DIR`; `work_home_relative` and `out_dir_arguments` (`bazel-orfs/private/environment.bzl`), tested by `bazel-orfs/test/work_home_test.bzl`.
- **A variable is never missing from `flow/scripts/variables.yaml`.** Its entry has its default and, when not every stage reads it, `stages:`. The scoping is part of each stage's cache key, so changing a CTS variable reruns CTS and what follows, and nothing before.
  In bazel-orfs: `check_variables` (`bazel-orfs/private/stages.bzl`) fails the build on a name `variables.yaml` does not list; `check_stage_variables` and `write_stage_filter` scope each variable to its stages, tested by `bazel-orfs/test/stages_filter_test.bzl`.
- **A variable is never read through an existence check.** It is read as `$::env(VAR)`, never through `env_var_exists_and_non_empty` with a fallback, so a misspelled or unpropagated variable is an error at the line that reads it. A boolean is `0`/`1`.
- **A script never overwrites a variable that is set.** It sets one only when it is unset.
- **A platform default is never repeated in a design's `config.mk`.** It is in the platform's `config.mk`, assigned with `?=`.
- **A variable never has a negative name** (`LEC_CHECK=1`, never `DISABLE_LEC_CHECK`), **never duplicates an existing one** (`ADDITIONAL_LIBS` for an extra library), **and is never a default-off feature toggle** that no CI design sets. A variable with no effect is deleted, not deprecated.
- **A `.mk` file never computes a value with `awk` or `sed`.** That logic is in Python with unit tests.

When using bazel-orfs, dependency checking is done by Bazel instead of ORFS's Makefile, with the exception of the synthesis canonicalization stage.

ORFS `make do-yosys-canonicalize` is special and does dependency checking using the ORFS `Makefile`, outputting `$(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil`.

The `.rtlil` is Yosys's internal representation format of all the various input files that went into Yosys, however any unused modules have been deleted and the modules are in canonical form (ordering of the Verilog files provided to Yosys won't matter). However, `.rtlil` still contains line number information for debugging purposes. The canonicalization stage is quick compared to synthesis and adds no measurable overhead.

Canonicalization simplifies specifying `VERILOG_FILES` to ORFS in Bazel: simply glob them all and let Yosys figure out which files are actually used. This avoids redoing synthesis unnecessarily if, for instance, a Verilog file related to simulation changes.

The next stage is `make do-yosys` which does no dependency checking, leaving it to Bazel. `do-yosys` completes the synthesis using `$(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil`.

The subsequent ORFS stages are run with `make do-floorplan do-place ...` and these stages do no dependency checking, leaving it to Bazel.

### openroad.bzl internals

The `openroad.bzl` file contains simple helper functions written in Starlark as well as the `orfs_flow()` macro.
The implementation of this macro spawns multiple `genrule` native rules which are responsible for preparing and running ORFS physical design flow targets during the Bazel build stage.

These are the genrules spawned in this macro:

* ORFS stage-specific (named: `target_name + "_" + stage` or `target_name + "_" + variant + "_" + stage`)

Dependency deployment is handled via output groups on stage targets (`deps_files` for a tree, `deps` for an archive), accessed through `//:deps`.

### Bazel flow

The ORFS flow scripts (Makefile, TCL scripts, PDKs) are fetched from the
[OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
repository via `git_override` in `MODULE.bazel`. All EDA tools default to
mock implementations for fast iteration; override with real tools for
production builds (see [Tool configuration](tools.md)).

```bash
bazel build <target>_<stage>
```

### Tools location after bazel run

A mutable build folder can be set up to prepare for a local synthesis run, useful when digging into some detail of the synthesis flow:

    $ bazelisk run //:deps -- start //test:tag_array_64x184 synth

### Create a make issue archive

To create and test a `make issue` archive for floorplan:

    bazelisk run //:deps -- start //test:lb_32x128 floorplan
    tmp/test/lb_32x128/make ISSUE_TAG=test floorplan_issue

This results in `tmp/test/lb_32x128/floorplan_test.tar.gz`, which can be run provided the `openroad` application is in the path.

You can use a local ORFS installation by running `source env.sh`.

Alternatively, use the ORFS installation from Bazel by running `make bash` to set up the environment:

    tmp/test/lb_32x128/make bash
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
bazel build --output_groups=deps //test:L1MetadataArray_synth
```

This builds the immediate dependencies of the `L1MetadataArray` target up to the `synth` stage and places the results in the `bazel-bin` directory.
Later, those dependencies are used by Bazel to build the `synth` stage for the `L1MetadataArray` target.
