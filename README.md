# Bazel-orfs

This repository contains [Bazel](https://bazel.build/) rules for wrapping Physical Design Flows provided by [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts).

## Requirements

* [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) - must reside under `~/OpenROAD-flow-scripts`. `bazel-orfs` intentionally does not treat OpenROAD-flow-scripts as a installable versioned tool, but prefers to rely on `~/OpenROAD-flow-scripts` such that it is easy to hack ORFS and OpenROAD.
* [Bazelisk](https://bazel.build/install/bazelisk) or [Bazel](https://bazel.build/install) - if using `bazel`, please refer to `.bazelversion` file for the recommended version of the tool.

## Usage

Core functionality is implemented as `build_openroad()` bazel macro in `openroad.bzl` file.

In order to use `build_openroad()` macro in Bazel Workspace in other project it is required to pull `bazel-orfs` as external dependency through one of [Bazel Workspace Rules](https://bazel.build/reference/be/workspace). For example in project's WORKSPACE:

```
git_hash = "<git hash for specific bazel-orfs revision>"
archive_sha256 = "<SHA256 checksum for archive with bazel-orfs>"

http_archive(
    name = "bazel-orfs",
    sha256 = archive_sha256,
    strip_prefix = "bazel-orfs-%s" % git_hash,
    url = "<URL to bazel-orfs repository>/archive/%s.tar.gz" % git_hash,
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
    entrypoint = "//:entrypoint.mk",
    verilog_files=["test/rtl/L1MetadataArray.sv"],
    variant="test",
    macros=["tag_array_64x184"],
    stage_sources={'synth': ["test/constraints-top.sdc"],
    'floorplan': ["util.tcl"],
    'place': ["util.tcl"]},
    io_constraints="io.tcl",
    stage_args={
        'synth': ['SYNTH_HIERARCHICAL=1'],
        'floorplan': [
            'CORE_UTILIZATION=3',
            'RTLMP_FLOW=True',
            'CORE_MARGIN=2',
        ],
        'place': ['PLACE_DENSITY=0.20', 'PLACE_PINS_ARGS=-annealing'],
    },
    mock_abstract=True,
    mock_stage="grt"
)
```

It is important to provide an `entrypoint` argument which contains a path to Makefile located inside the repository which loads `bazel-orfs`. This Makefile should include `config.mk` from `bazel-orfs`. This can be done with the help of `BAZEL_ORFS` environment variable:

```
include $(BAZEL_ORFS)/config.mk
```

Macro from the example above spawns the following bazel targets:

```
Stage targets:
  //:L1MetadataArray_test_synth_sdc
  //:L1MetadataArray_test_synth
  //:L1MetadataArray_test_floorplan
  //:L1MetadataArray_test_cts
  //:L1MetadataArray_test_place
  //:L1MetadataArray_test_grt
  //:L1MetadataArray_test_generate_abstract

Memory targets:
  //:L1MetadataArray_test_clock_period
  //:L1MetadataArray_test_memory

Make targets:
  //:L1MetadataArray_test_clock_period_make_script
  //:L1MetadataArray_test_clock_period_make
  //:L1MetadataArray_test_cts_make_script
  //:L1MetadataArray_test_cts_make
  //:L1MetadataArray_test_floorplan_make_script
  //:L1MetadataArray_test_floorplan_make
  //:L1MetadataArray_test_generate_abstract_make_script
  //:L1MetadataArray_test_generate_abstract_make
  //:L1MetadataArray_test_grt_make_script
  //:L1MetadataArray_test_grt_make
  //:L1MetadataArray_test_place_make_script
  //:L1MetadataArray_test_place_make
  //:L1MetadataArray_test_synth_make_script
  //:L1MetadataArray_test_synth_make
  //:L1MetadataArray_test_synth_sdc_make_script
  //:L1MetadataArray_test_synth_sdc_make
```

The example comes from the `BUILD` file in this repository. For details about targets spawned by this macro please refer to `Implementation` chapter.

## Implementation

### orfs script

This script loads the ORFS environment, sets the 'BAZEL_ORFS` environment variable and evaluates the rest of the command line that called the script.

### openroad.bzl

This file contains simple helper functions written in starlark as well as macro `build_openroad()`. The implementation of this macro spawns multiple `genrule` native rules which are responsible for running ORFS `make` targets during bazel build stage. Each `genrule()` does the same
thing: it sets env vars and runs one of make targets defined in *.mk files which then run make target from ORFS flow Makefile.

There are 4 kinds of genrules spawned in this macro:

* Stage targets (named: `target_name + “_” + stage`)
* Make targets (named: `target_name + “_” + stage + “_make”`)
* Mock Area targets (named: `target_name + “_” + stage + “_mock_area”`)
* Memory targets (named: `target_name + “_memory”`)

#### Stage Targets

Main rules for executing each ORFS stage (synthesis, floorplan, clock tree synthesis, place, route, etc.). The outputs and inputs are different for each ORFS stage and are defined by macro arguments and the implementation of the macro.

#### Make Targets

Those scripts are used for local tests of ORFS stages.
Two targets are spawned for each ORFS stage. First generates a shell script, second makes it executable from `bazel-bin` directory. The final usable script is generated under path:

```
bazel-bin/<target_name>_make
```

The shell script is produced by `genrule` by concatenating template script `make_script.template.sh` with `make` and environment variables specific for given stage. Template file contains boilerplate code for enabling features of [bazel bash runfiles library](https://github.com/bazelbuild/bazel/blob/master/tools/bash/runfiles/runfiles.bash) and a call to `orfs` script. The runfiles library is used for accessing script dependencies stored in `runfiles` driectory. Attribute `srcs` of the genrule contains dependencies required for running the script (e.g.: `orfs` script, make target patterns, TCL scripts). Those dependencies don't include results of previous flow stages and because of that, it is required to build those before running the generated script.
In the second rule (`sh_binary`) the `runfiles` directory for the script is created and filled with dependencies so that the script can be executed straight from the output directory. It is important to remember that, by default, bazel output directory is not writeable so running the ORFS flow with generated script will fail unless correct permissions are set for the directory. Example usage of `Make` targets can look like this:

```
bazel build $(bazel query "deps(L1MetadataArray_test_floorplan) except L1MetadataArray_test_floorplan")
bazel build L1MetadataArray_test_floorplan_make
cd bazel-bin && chmod -R +w . && cd ..
./bazel-bin/L1MetadataArray_test_floorplan_make do-floorplan
```

#### Mock Area Targets

Those targets are used to run particular stages of the flow with a scaled area of the module evaluated in a given target. Used for estimating sizes of macros with long build times and checking if they will fit in upper-level modules without running time consuming place and route flow.

#### Memory Targets

These targets print RAM summaries for a given module.
