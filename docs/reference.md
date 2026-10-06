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
