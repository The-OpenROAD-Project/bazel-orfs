# Bazel-orfs

This repository contains [Bazel](https://bazel.build/) rules for wrapping [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) (ORFS).

Why Bazel on top of ORFS?
-------------------------

bazel-orfs gives all the expected Bazel advantages to ORFS: artifacts, parallel builds, remote execution, repeatable builds, etc.

Also, ORFS and OpenROAD is work in progress and one should expect for
large designs to get involved with the community or need a
support contract with Precision Innovations (https://www.linkedin.com/in/tomspyrou/).

Using ORFS directly, instead of modifying it or creating an alternative flow,
makes it easy to get the very latest features and version of OpenROAD and ORFS
as well as having access to all ORFS features, including debugging
features such as `make issue` and `deltaDebug.py`.

Since bazel-orfs uses the unmodified ORFS, it is easy to articulate familiar
and easily actionable github issues for the OpenROAD and ORFS maintainers.

## Requirements

* [Bazelisk](https://bazel.build/install/bazelisk) or [Bazel](https://bazel.build/install) - if using Bazel, please refer to [.bazelversion](./.bazelversion) file for the recommended version of the tool.
* [Docker](https://docs.docker.com/get-docker/) - Bazel utilizes Docker to set up the environment using ORFS artifacts from the container.
  The Docker image used in the flow defaults to `openroad/orfs`, with tag specified in the [module](./MODULE.bazel) file.

  > **NOTE:** The `bazel-orfs` doesn't execute flows inside the Docker container, but rather uses the container as a source of ORFS artifacts.
* (Optional) Locally built [ORFS](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts). To use it, `env.sh` file from OpenROAD-flow-scripts has to be sourced or `FLOW_HOME` environment variable has to be set to the path of the local `OpenROAD-flow-scripts/flow` installation.

## Usage

Core functionality is implemented as `orfs_flow()` Bazel macro in `openroad.bzl` file.

In order to use `orfs_flow()` macro in Bazel Workspace in other project it is required to use bazel-orfs as an external dependency through one of [Bazel Module Methods](https://bazel.build/rules/lib/globals/module):
* from git repository

  ```starlark
  bazel_dep(name = "bazel-orfs")
  git_override(
      module_name = "bazel-orfs",
      remote = "<URL to bazel-orfs repository>",
      commit = "<git hash for specific bazel-orfs revision>",
  )
  ```

* from local directory

  ```starlark
  bazel_dep(name = "bazel-orfs")
  local_path_override(
      module_name = "bazel-orfs",
      path = "<path to local bazel-orfs workspace>",
  )
  ```

The macro can now be placed in the BUILD file. The macro usage can look like this:

```starlark
orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "route",
    macros = ["tag_array_64x184_generate_abstract"],
    stage_arguments = {
        "synth": {
            "SDC_FILE": "$(location :test/constraints-top.sdc)",
            "SYNTH_HIERARCHICAL": "1",
        },
        "floorplan": {
            "CORE_UTILIZATION": "3",
            
            "CORE_MARGIN": "2",
            "MACRO_PLACE_HALO": "30 30",
        },
        "place": {
            "PLACE_DENSITY": "0.20",
            "PLACE_PINS_ARGS": "-annealing",
        },
    },
    stage_sources = {
        "synth": [":test/constraints-top.sdc"],
    },
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)
```

The macro from the example above spawns the following Bazel targets:

```
Dependency targets:
  //:L1MetadataArray_cts_deps
  //:L1MetadataArray_floorplan_deps
  //:L1MetadataArray_generate_abstract_deps
  //:L1MetadataArray_grt_deps
  //:L1MetadataArray_place_deps
  //:L1MetadataArray_route_deps
  //:L1MetadataArray_synth_deps

Stage targets:
  //:L1MetadataArray_cts
  //:L1MetadataArray_floorplan
  //:L1MetadataArray_generate_abstract
  //:L1MetadataArray_grt
  //:L1MetadataArray_place
  //:L1MetadataArray_route
  //:L1MetadataArray_synth
```

The example comes from the [BUILD](./BUILD) file in this repository.

To test different variants of the same design, the `orfs_flow` can be provided with an optional argument `variant`.

```starlark
orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "route",
    macros = ["tag_array_64x184_generate_abstract"],
    # [...]
    variant = "test",
)
```

This definition creates similar Bazel targets with additional variant appended after the design name:

```
Dependency targets:
  //:L1MetadataArray_test_cts_deps
  //:L1MetadataArray_test_floorplan_deps
  ...
  //:L1MetadataArray_test_generate_abstract_deps

Stage targets:
  //:L1MetadataArray_test_synth
  //:L1MetadataArray_test_floorplan
  ...
  //:L1MetadataArray_test_generate_abstract
```

## Implementation

### openroad.bzl

This file contains simple helper functions written in Starlark as well as macro `orfs_flow()`.
The implementation of this macro spawns multiple `genrule` native rules which are responsible for preparing and running ORFS physical design flow targets during Bazel build stage.

These are the genrules spawned in this macro:

* ORFS stage-specific (named: `target_name + “_” + stage` or `target_name + “_” + variant + “_” + stage`)
* ORFS stage dependencies (named: `target_name + “_” + stage + “_deps”` or `target_name + “_” + variant + “_” + stage + “_deps”`)

### Bazel flow

Regular Bazel flow uses artifacts from the Docker environment with preinstalled ORFS.

It implicitly depends on a Docker image with ORFS environment pre-installed being present.
The Docker image used in the flow is defined in the [module](./MODULE.bazel) file, the default can be overridden by specifying `image` and `sha256` attributes:

```starlark
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default(
    image = <image>,
    sha256 = <sha256>,
)
use_repo(orfs, "docker_orfs")
```

Setting this attribute to a valid image and checksum will enable Bazel to automatically pull the image and extract ORFS artifacts on `bazel run` or `bazel build`:

```bash
bazel build <target>_<stage>
```

> **NOTE:** If `sha256` is set to an empty string `""`, Bazel will attempt to use a local image with name provided in the `image` field.

### Local flow

A locally built and modified [ORFS](https://openroad-flow-scripts.readthedocs.io/en/latest/user/UserGuide.html) can also be used to run the flow:

```bash
bazel run <target>_<stage>_deps -- <absolute_path>
<absolute_path>/make do-<stage>
```

The `_deps` is used to distinguish between copying the results into the mutable folder for that stage versus copying the required files to execute said stage.

It is also possible and convenient to run within the sandbox as the arguments after the absolute path are forwarded to make:

```bash
bazel run <target>_<stage>_deps -- <absolute_path> <make args...>
```

To view the floorplan:

```bash
bazel run tag_array_64x184_floorplan $(pwd)/tmp gui_floorplan
```

> **NOTE:** If the directory under the `<absolute_path>` does not exist, it will be created. If a relative path is provided, the `bazel run` command above will fail.

A convenient way to run the floorplan and view the results would be:

```bash
bazel run MyDesign_floorplan_deps -- `pwd`/build
build/make do-floorplan
build/make gui_floorplan
```

By default, the `make do-<stage>` invocation will rely on the ORFS from [MODULE.bazel](./MODULE.bazel), unless the `env.sh` script is sourced, or the `FLOW_HOME` environment variable is set to the path of the local `OpenROAD-flow-scripts/flow` installation:

```bash
source <orfs_path>/env.sh

bazel run <target>_<stage>_deps -- <absolute_path>
<absolute_path>/make do-<stage>
```

> **NOTE:** The synthesis stage requires the `do-yosys-canonicalize` and `do-yosys` steps to be completed beforehand.
> These steps are necessary to generate the required `.rtlil` file for the synthesis stage.
>
> ```bash
> source <orfs_path>/env.sh
>
> bazel run <target>_synth_deps -- <absolute_path>
> <absolute_path>/make do-yosys-canonicalize do-yosys do-1_synth
> ```

### Override BUILD configuration variables

Configuration variables can be overwritten on the command line by passing them in as arguments to the local flow:

```bash
$ bazel run tag_array_64x184_floorplan $(pwd)/tmp print-CORE_UTILIZATION
[deleted]
CORE_UTILIZATION = 40
```bash
$ bazel run tag_array_64x184_floorplan $(pwd)/tmp CORE_UTILIZATION=5 print-CORE_UTILIZATION
[deleted]
CORE_UTILIZATION = 5
```

### Stage targets

Each stage of the physical design flow is represented by a separate target and follows the naming convention: `target_name + “_” + stage`.

The stages are as follows:

* `synth` (synthesis)
* `floorplan`
* `place`
* `cts` (clock tree synthesis)
* `grt` (global route)
* `route`
* `final`
* `generate_abstract`

### Generate abstract targets

Those targets are used to create abstracts (`.lef` and `.lib` files) for macros.

Abstracts are generated at the `target + "generate_abstract"` stage, which follows one defined via `abstract_stage` attribute passed to the `orfs_flow()` macro:

<pre lang="starlark">
orfs_flow(
    name = "tag_array_64x184",
    <b>abstract_stage = "place",</b>
    stage_arguments = {
        "synth": SRAM_SYNTH_ARGUMENTS,
        "floorplan": SRAM_FLOOR_PLACE_ARGUMENTS | {
            "CORE_UTILIZATION": "40",
            "CORE_ASPECT_RATIO": "2",
        },
        "place": SRAM_FLOOR_PLACE_ARGUMENTS | {
            "PLACE_DENSITY": "0.65",
        },
    },
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)
</pre>

By default it's the latest ORFS-specific target (`final`).

> **NOTE:** Abstracts can be generated starting from the `floorplan` stage, thus skipping the `synth` stage.

Abstracts are intended to be used in builds of other parts of the design that use the given macro.
They're useful for estimating sizes of macros with long build times and checking if they will fit in upper-level modules without running time consuming place and route flow.

> **NOTE:** Stages that follow the one passed to `abstract_stage` will not be created by the `orfs_flow()` macro.

### Mock area targets

Mock area targets are created on top of the stage targets and overrides `_generate_abstract` target to produced mocked abstracts.

The flow contains:
* `target_name_variant + “_synth_mock_area”` - synthesis which has its whole internal logic removed,
* `target_name_variant + “_mock_area”` - reads `DIE_AREA` and `CORE_AREA` from default floorplan results and scale them by value defined in `mock_area`,
* `target_name_variant + “_floorplan_mock_area”` - floorplan with overridden `DIE_AREA` and `CORE_AREA` values,
* `target_name_variant + “_generate_abstract”` - abstracts generated based on mocked synthesis and floorplan.

To create mock area targets, `mock_area` has to be added to `orfs_flow` definition:

```starlark
orfs_flow(
    name = "lb_32x128",
    stage_arguments = LB_STAGE_ARGS,
    stage_sources = LB_STAGE_SOURCES,
    verilog_files = LB_VERILOG_FILES,
    mock_area = 0.5,
)
```

The mock has the same pinout as the original macro and similar size which makes it useful in early design stages.

### Constraints handling

Constraint files are passed down to `orfs_flow()` macro through [Stage targets](#stage-targets) arguments and sources:

<pre lang="starlark">
orfs_flow(
    name = "tag_array_64x184",
    <b>sources = {
        "SDC_FILE": ":constraints-sram",
    },</b>
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)
</pre>

Those accept a Bazel label that points to the file.
There are however cases, where e.g. SRAM constraints file includes additional TCL script.
In such scenario a filegroup should also define the `data` attribute with the additional script.

<pre lang="starlark">
filegroup(
    name = "constraints-sram",
    srcs = [
        ":test/constraints-sram.sdc",
    ],
    <b>data = [
        ":test/util.tcl",
    ],</b>
    visibility = [":__subpackages__"],
)
</pre>

### Dependency targets

The dependency targets fall under the `target_name + “_” + variant + “_” +stage + “_deps”` naming convention, and are used to prepare the environment for running the ORFS stage targets.
Each stage of the physical design flow depend on two generated `.mk` files that provide the configuration for the ORFS.
One is specific for the stage of the flow and the second one is common for the whole design being built.

They can be found under the following paths:

```bash
<path>/config.mk                                                             # Common for the whole design
<path>/results/<module>/<target>/<variant>/<stage_number>_<stage>.short.mk   # Specific for the stage
```

Additionally, the dependency targets are responsible for constraints handling and generating the shell scripts that are used to run the ORFS stages both in the Bazel and Local flow:

```bash
<path>/make     # Running the ORFS stages
<path>/results  # Directory for the results of the flow
<path>/external # Directory for the external dependencies
```

### GUI targets

The GUI and CLI targets can only be run from the generated shell script.

For the GUI:

```bash
bazel run <target>_<stage> -- <absolute_path>
<absolute_path>/make gui_<stage>
```

For the CLI:

```bash
bazel run <target>_<stage> -- <absolute_path>
<absolute_path>/make open_<stage>
```

CLI and GUI is not available for all stages, consequently these targets are created only for:

* `floorplan`
* `place`
* `cts` (clock tree synthesis)
* `grt` (global route)
* `route`
* `final`

## Tutorial

To execute the build flow for the `cts` (Clock Tree Synthesis) stage of the `L1MetadataArray` target, use the following command:

```bash
bazel run @bazel-orfs//:L1MetadataArray_cts -- `pwd`/build
```

Bazel will automatically download the Docker image with the ORFS environment and run the flow.

This will build the `L1MetadataArray` target up to the `cts` stage and place the results in the `build/results` directory.
It's important to provide an absolute path to the directory where the flow artifacts will be stored.

### Dependencies in ORFS Makefile versus Bazel

When using bazel-orfs, the dependency checking is done by Bazel instead of ORFS's makefile, with the exception of the synthesis canonicalization stage.

ORFS `make do-yosys-canonicalize` is special and will do dependency checking using ORFS `Makefile` and output `$(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil`.

The `.rtlil` is Yosys's internal representation format of all the various input files that went into Yosys, however any unused modules have been deleted and the modules are in canonical form(ordering of the Verilog files provided to Yosys won't matter). However, `.rtlil` still contains line number information for debugging purposes. The canonicalization stage is quick compared to synthesis and adds no measurable overhead.

Canonicalization simplifies specifying `VERILOG_FILES` to ORFS in Bazel, simply glob them all and let Yosys figure out which files are actually used. This avoids redoing synthesis unnecessarily if, for instance, a Verilog file related to simulation changes.

The next stage is `make do-yosys` which does no dependency checking, leaving it to Bazel. `do-yosys` completes the synthesis using `$(RESULTS_DIR)/1_1_yosys_canonicalize.rtlil`.

The subsequent ORFS stages are run with `make do-floorplan do-place ...` and these stages do no dependency checking, leaving it to Bazel.

bazel-orfs also does dependency checking of options provided to each stage. If a property to CTS is changed, then no steps ahead of CTS is re-run. bazel-orfs does not know which properties belong to which stage, it is the responsibility of the user to pass properties to the correct stage. This includes some slightly surprising responsibilities, such as passing IO pin constraints to both floorplan and placement.

### Using the local flow

The local flow allows testing the build with locally built OpenROAD-flow-scripts.
It is based on Bazel `make` targets, for more information on those, please refer to [Dependency targets](#dependency-targets) paragraph.

Let's assume we want to perform a `floorplan` stage for the `L1MetadataArray` design using the locally built ORFS.

1. Source `env.sh` of your local ORFS installation or set the `FLOW_HOME` environment variable to the path to your local `OpenROAD-flow-scripts/flow` directory:

  ```bash
  source <ORFS_path>/env.sh
  # Or
  export FLOW_HOME=<ORFS_path>/flow
  ```

2. Build the stages prior to the `floorplan` stage:

  ```bash
  # Initialize dependencies for the Synthesis stage for L1MetadataArray target
  bazel run @bazel-orfs//:L1MetadataArray_synth_deps -- `pwd`/build

  # Build Synthesis stage for L1MetadataArray target using local ORFS
  build/make do-yosys-canonicalize do-yosys do-1_synth

  # Initialize dependencies for the Floorplan stage for L1MetadataArray target
  bazel run @bazel-orfs//:L1MetadataArray_floorplan_deps -- `pwd`/build
  ```

3. Execute the shell script with ORFS make target relevant to given stage of the flow:

  ```bash
  build/make do-floorplan
  ```

### Running OpenROAD GUI

Let's assume we want to run a GUI for the `route` stage for the `L1MetadataArray` target.

1. Initialize and build stages up to the `route` stage:

  ```bash
  bazel run @bazel-orfs//:L1MetadataArray_route -- `pwd`/build
  ```

2. Execute the GUI shell script:

  ```bash
  # Start the GUI for the Route stage for L1MetadataArray target
  build/make gui_route

  # Or open the GUI through the CLI
  build/make open_route
  gui::show
  ```

### Tweaking aspect ratio of a floorplan

Notice how the `CORE_ASPECT_RATIO` parameter is associated with
the floorplan and *only* the floorplan stage below:

```diff
diff --git a/BUILD b/BUILD
index 095d63b..4b78dea 100644
--- a/BUILD
+++ b/BUILD
@@ -74,7 +74,7 @@ orfs_flow(
         "synth": SRAM_SYNTH_ARGUMENTS,
         "floorplan": SRAM_FLOOR_PLACE_ARGUMENTS | {
             "CORE_UTILIZATION": "40",
-            "CORE_ASPECT_RATIO": "2",
+            "CORE_ASPECT_RATIO": "4",
         },
         "place": SRAM_FLOOR_PLACE_ARGUMENTS | {
             "PLACE_DENSITY": "0.65",
```

Bazel will detect this change specifically as a change to the floorplan, re-use the synthesis result and rebuild from the floorplan stage.
Similarly, if the `PLACE_DENSITY` is modified, only stages from the placement and on are re-built.

To apply and view the changes:

```bash
# Build tag_array_64x184 macro up to the floorplan stage
bazel run @bazel-orfs//:tag_array_64x184_floorplan -- `pwd`/build

# View final results from GUI
build/make gui_floorplan
```

If the remote caching is enabled for Bazel, reverting the change and rebuilding the floorplan stage will be completed instantaneously, as the artifact already exists:

```bash
# Revert the change
git restore BUILD

# Rebuild the floorplan stage
bazel run @bazel-orfs//:tag_array_64x184_floorplan -- `pwd`/build

# View final results from GUI
build/make gui_floorplan
```

### Fast floorplanning and mock abstracts

Let's say we want to skip place, cts and route and create a mock abstract where we can at least check that there is enough place for the macros at the top level.

> **WARNING:** Although mock abstracts can speed up turnaround times, skipping place, cts or route can lead to errors and problems that don't exist when place, cts and route are not skipped.

To do so, we modify in `BUILD` file the `abstract_stage` attribute of `orfs_flow` macro to `floorplan` stage:

```diff
diff --git a/BUILD b/BUILD
index 095d63b..9756fbf 100644
--- a/BUILD
+++ b/BUILD
@@ -110,7 +110,7 @@ orfs_flow(

 orfs_flow(
     name = "L1MetadataArray",
-    abstract_stage = "route",
+    abstract_stage = "place",
     macros = ["tag_array_64x184_generate_abstract"],
     stage_arguments = {
         "synth": {
```

This will generate targets that can be verified in the `bazel query` output:

```bash
bazel query '...:*' | grep 'L1MetadataArray'

//:L1MetadataArray_synth_deps
//:L1MetadataArray_synth
//:L1MetadataArray_floorplan_deps
//:L1MetadataArray_floorplan
//:L1MetadataArray_generate_abstract
```

The abstract stage follows the one defined via `abstract_stage` attribute passed to the `orfs_flow()` macro.
However it always falls down to the `<target>_generate_abstract` pattern and can be built with the following command:

```bash
bazel build @bazel-orfs//:L1MetadataArray_generate_abstract
```

This will cause the Bazel to generate the abstracts for the design right after the `floorplan` stage instead of `route` stage.
The output `LEF` file can be found under the `bazel-bin/results/<module>/<target>/base/<target.lef>` path.

For more information please refer to the description of [Abstract targets](#generate-abstract-targets).

## Bazel hacking

### Upgrading bazel-orfs and ORFS in a repository using bazel-orfs and ORFS

    bazelisk run @bazel-orfs//:bump

This will update your MODULE.bazel with the latest ORFS and bazel-orfs and run `bazelisk mod tidy`.

### Run all synth targets

```bash
bazel query :\* | grep '_synth$' | xargs -I {} bazel run {} -- `pwd`/build
```

This will run all synth targets in the workspace and place the results in the `build/results` directory.

### Forcing a rebuild of a stage

Sometimes it is desirable, such as when hacking ORFS, to redo a build stage even
if none of the dependencies for that stage changed. This can be achieved by changing
a `PHONY` variable to that stage and bumping it:

```diff
diff --git a/BUILD b/BUILD
index 095d63b..5b618ba 100644
--- a/BUILD
+++ b/BUILD
@@ -114,6 +114,7 @@ orfs_flow(
     name = "L1MetadataArray",
     abstract_stage = "route",
     macros = ["tag_array_64x184_generate_abstract"],
     stage_arguments = {
         "synth": {
+            "PHONY": "1",
             "SDC_FILE": "$(location :test/constraints-top.sdc)",
             "SYNTH_HIERARCHICAL": "1",
         },
```

### Building the immediate dependencies of a target

```bash
bazel build @bazel-orfs//:L1MetadataArray_synth_deps
```

This will build the immediate dependencies of the `L1MetadataArray` target up to the `synth` stage and place the results in the `bazel-bin` directory.
Later, those dependencies will be used by Bazel to build the `synth` stage for `L1MetadataArray` target.

### Tools location after `bazel run ...`

A mutable build folder can be set up to prepare for a local synthesis run, useful when digging into some detail of synthesis flow:

    $ bazel build tag_array_64x184_synth_deps -- `pwd`/build
    $ build/make print-YOSYS_EXE
    YOSYS_EXE = external/_main~orfs_repositories~docker_orfs/OpenROAD-flow-scripts/tools/install/yosys/bin/yosys

This is actually a symlink pointing to the read only executables, which is how yosys is able to find the yosys-abc alongside itself needed for the abc part of the synthesis stage:

    $ ls -l $(dirname $(readlink -f build/external/_main~orfs_repositories~docker_orfs/OpenROAD-flow-scripts/tools/install/yosys/bin/yosys))
    total 37456
    -rwxr-xr-x 1 oyvind oyvind 23449673 Aug 15 07:05 yosys
    -rwxr-xr-x 1 oyvind oyvind 14725193 Aug 15 07:05 yosys-abc
    -rwxr-xr-x 1 oyvind oyvind     3904 Aug  7 23:11 yosys-config
    -rwxr-xr-x 1 oyvind oyvind    65609 Aug 15 07:05 yosys-filterlib
    -rwxr-xr-x 1 oyvind oyvind    73845 Aug  7 23:11 yosys-smtbmc
    -rwxr-xr-x 1 oyvind oyvind    17377 Aug  7 23:11 yosys-witness

### `make issue` floorplan example

To create and test a `make issue` archive for floorplan:

    bazel run lb_32x128_floorplan_deps `pwd`/build
    build/make ISSUE_TAG=test floorplan_issue

This results in `build/floorplan_test.tar.gz`, which can be run provided there `openroad` application is in the path.

A local ORFS installation can be used by running `source env.sh`.

Alternatively, the ORFS installation used with Bazel, can be used by using `make bash` to set up the environment of the ORFS extracted into the Bazel build environment:

    build/make bash
    export PATH=$PATH:$(realpath $(dirname $(readlink -f $OPENROAD_EXE)))
    tar --strip-components=1 -xzf ../floorplan_test.tar.gz
    ./run-me-lb_32x128-asap7-base.sh
