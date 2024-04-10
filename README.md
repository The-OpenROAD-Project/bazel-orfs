# Bazel-orfs

This repository contains [Bazel](https://bazel.build/) rules for wrapping Physical Design Flows provided by [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts).

## Requirements

* [Bazelisk](https://bazel.build/install/bazelisk) or [Bazel](https://bazel.build/install) - if using `bazel`, please refer to `.bazelversion` file for the recommended version of the tool.
* [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) - **Required only for running `Make` targets** - must reside under `~/OpenROAD-flow-scripts`. `bazel-orfs` intentionally does not treat OpenROAD-flow-scripts as a installable versioned tool, but prefers to rely on `~/OpenROAD-flow-scripts` such that it is easy to hack ORFS and OpenROAD.
* [Docker](https://docs.docker.com/get-docker/) - **Required only for running `Stage` targets**

## Usage

Core functionality is implemented as `build_openroad()` bazel macro in `openroad.bzl` file.

In order to use `build_openroad()` macro in Bazel Workspace in other project it is required to pull `bazel-orfs` as external dependency through one of [Bazel Workspace Rules](https://bazel.build/reference/be/workspace). For example in project's MODULE.bazel:

```
bazel_dep(name = "bazel-orfs")
git_override(
    module_name = "bazel-orfs",
    remote = "<URL to bazel-orfs repository>",
    commit = "<git hash for specific bazel-orfs revision>"
)
```

Then load the macro in BUILD file where it should be used:

```
load("@bazel-orfs//:openroad.bzl", "build_openroad")
```

The macro can now be placed in the BUILD file. The macro usage can look like this:

```
build_openroad(
    name = "L1MetadataArray",
    io_constraints = ":io",
    macros = ["tag_array_64x184"],
    mock_abstract = True,
    mock_stage = "grt",
    sdc_constraints = ":test/constraints-top.sdc",
    stage_args = {
        "synth": ["SYNTH_HIERARCHICAL=1"],
        "floorplan": [
            "CORE_UTILIZATION=3",
            "RTLMP_FLOW=True",
            "CORE_MARGIN=2",
            "MACRO_PLACE_HALO=10 10",
        ],
        "place": [
            "PLACE_DENSITY=0.20",
            "PLACE_PINS_ARGS=-annealing",
        ],
    },
    variant = "test",
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)
```

Macro from the example above spawns the following bazel targets:

```
Stage targets:
  //:L1MetadataArray_test_clock_period
  //:L1MetadataArray_test_synth_sdc
  //:L1MetadataArray_test_synth
  //:L1MetadataArray_test_floorplan
  //:L1MetadataArray_test_place
  //:L1MetadataArray_test_cts
  //:L1MetadataArray_test_grt
  //:L1MetadataArray_test_generate_abstract

Memory targets:
  //:L1MetadataArray_test_memory

Make targets:
  //:L1MetadataArray_test_clock_period_make
  //:L1MetadataArray_test_clock_period_make_script
  //:L1MetadataArray_test_synth_sdc_make
  //:L1MetadataArray_test_synth_sdc_make_script
  //:L1MetadataArray_test_synth_make
  //:L1MetadataArray_test_synth_make_script
  //:L1MetadataArray_test_floorplan_make
  //:L1MetadataArray_test_floorplan_make_script
  //:L1MetadataArray_test_place_make
  //:L1MetadataArray_test_place_make_script
  //:L1MetadataArray_test_cts_make
  //:L1MetadataArray_test_cts_make_script
  //:L1MetadataArray_test_grt_make
  //:L1MetadataArray_test_grt_make_script
  //:L1MetadataArray_test_generate_abstract_make
  //:L1MetadataArray_test_generate_abstract_make_script

Config generation targets:
  //:L1MetadataArray_test_config
  //:L1MetadataArray_test_config.mk
  //:L1MetadataArray_test_clock_period_config
  //:L1MetadataArray_test_clock_period_config.mk
  //:L1MetadataArray_test_synth_sdc_config
  //:L1MetadataArray_test_synth_sdc_config.mk
  //:L1MetadataArray_test_synth_config
  //:L1MetadataArray_test_synth_config.mk
  //:L1MetadataArray_test_floorplan_config
  //:L1MetadataArray_test_floorplan_config.mk
  //:L1MetadataArray_test_place_config
  //:L1MetadataArray_test_place_config.mk
  //:L1MetadataArray_test_cts_config
  //:L1MetadataArray_test_cts_config.mk
  //:L1MetadataArray_test_grt_config
  //:L1MetadataArray_test_grt_config.mk
  //:L1MetadataArray_test_generate_abstract_config
  //:L1MetadataArray_test_generate_abstract_config.mk
```

The example comes from the `BUILD` file in this repository.
For details about targets spawned by this macro please refer to `Implementation` chapter.

## Implementation

### openroad.bzl

This file contains simple helper functions written in starlark as well as macro `build_openroad()`.
The implementation of this macro spawns multiple `genrule` native rules which are responsible for preparing and running ORFS physical design flow targets during bazel build stage.

There are 5 kinds of genrules spawned in this macro:

* Config generation targets
  * Common for the whole design (named: `target_name + “_config”`)
  * ORFS stage-specific config (named: `target_name + “_” + stage + “_config”`)
* Stage targets (named: `target_name + “_” + stage`)
* Make targets (named: `target_name + “_” + stage + “_make”`)
* Mock Area targets (named: `target_name + “_” + stage + “_mock_area”`)
* Memory targets (named: `target_name + “_memory”`)

There are two kinds of flows available:
* docker flow (Stage targets)
* local flow (Make targets)

Docker flow uses containerized environment with preinstalled ORFS to run the physical design flow, while the local flow (`_make` bazel targets) depends on the locally installed ORFS (specifically under `~/OpenROAD-flow-scripts`).
Each stage of the physical design flow depend on two generated `config.mk` files that provide the configuration for the ORFS.
One is specific for the stage of the flow and the second one is common for the whole design being built.
Design-specific config includes the stage-specific config through `STAGE_CONFIG` environment variable that is set in the `build_openroad()` macro implementation.
Both docker and local flow does the same thing: for each stage of the physical design flow it writes config files, sets env vars pointing to those files, builds a command line to execute in ORFS environment and runs it through the `entrypoint` script.

#### Entrypoint scripts

There is one entrypoint script for each kind of the flow.
For the local flow it is the `orfs` script and for the docker flow it's the `docker_shell` script.
Both of those scripts have the same responsibility of preparing and entering the ORFS build environment and then executing the build command prepared for given ORFS stage.
`orfs` does this by setting some initial environment variables and sourcing `env.sh` from ORFS.
`docker_shell` is very similar in that matter except it runs the flow in a docker container.

#### Stage Targets

Main rules for executing each ORFS stage (synthesis, floorplan, clock tree synthesis, place, route, etc.).
The outputs and inputs are different for each ORFS stage and are defined by macro arguments and the implementation of the macro.
Those targets are built with the docker flow.
Before running stage targets it is required to first fetch and load ORFS docker image into local docker runtime.
This can be done with the following `run` rule:

```
bazel run orfs_env
```

#### Make Targets

Those scripts are used for local tests of ORFS stages and are built with locally installed ORFS.
Two targets are spawned for each ORFS stage. First generates a shell script, second makes it executable from `bazel-bin` directory.
The final usable script is generated under path:

```
bazel-bin/<target_name>_make
```

The shell script is produced by `genrule` by concatenating template script `make_script.template.sh` with the entrypoint command.
The entrypoint command consists of a call to `orfs`, essential environment variables definitions (e.g. with paths to generated `config.mk` files) and physical design make targets to execute in ORFS environment.
Template file contains boilerplate code for enabling features of [bazel bash runfiles library](https://github.com/bazelbuild/bazel/blob/master/tools/bash/runfiles/runfiles.bash).
The runfiles library is used for accessing script dependencies stored in `runfiles` driectory.
Attribute `srcs` of the genrule contains dependencies required for running the script (e.g.: `orfs` script, make target patterns, configs).
Those dependencies don't include results of previous flow stages and because of that, it is required to build those before running the generated script.
In the second rule (`sh_binary`) the `runfiles` directory for the script is created and filled with dependencies so that the script can be executed straight from the output directory.
It is important to remember that, by default, bazel output directory is not writeable so running the ORFS flow with generated script will fail unless correct permissions are set for the directory.
Example usage of `Make` targets can look like this:

```
bazel build $(bazel query "deps(L1MetadataArray_test_floorplan) except L1MetadataArray_test_floorplan")
bazel build L1MetadataArray_test_floorplan_make
./bazel-bin/L1MetadataArray_test_floorplan_make do-floorplan
```

#### Mock Area Targets

Those targets are used to run particular stages of the flow with a scaled area of the module evaluated in a given target.
Used for estimating sizes of macros with long build times and checking if they will fit in upper-level modules without running time consuming place and route flow.

#### Memory Targets

These targets print RAM summaries for a given module.

### Constraints handling

Constraint files are passed down to `build_openroad()` macro through attributes:
* io_constraints
* sdc_constraints

Those accept a bazel label that points to the file.
There are however cases, where e.g. IO constraints file includes additional TCL script.
In such scenario a filegroup should be defined like so:

```
filegroup(
    name = "util",
    srcs = [
        "test/util.tcl",
    ],
)

filegroup(
    name = "io",
    srcs = [
        "test/io.tcl",
    ],
    data = [
        ":util",
    ],
)
```

The constraint file should also source the additional TCL script in a very specific manner.
The additional sourced files have to be placed in the same directory as the constraint file.
Constraint file should use environment variable `SDC_FILE` or `IO_CONSTRAINT` defined for the ORFS flow to fetch the path to itself and use it to source the additional file.
Here is the example:

```
set script_path [ file dirname $::env(IO_CONSTRAINTS) ]
source $script_path/util.tcl
```
