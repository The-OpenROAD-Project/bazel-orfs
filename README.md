# Bazel-orfs

This repository contains [Bazel](https://bazel.build/) rules for wrapping Physical Design Flows provided by [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) (ORFS).
There are two variants of the Bazel flow available:

* Docker flow - based on the ORFS installed in the Docker container that is used for running Bazel targets
* Local flow - relies on local installation of the ORFS

There are many build flows on top of OpenROAD
---------------------------------------------

There are numerous build flows on top of OpenROAD, these are some:

- ORFS. The developers of OpenROAD use this flow
  to test the tool. It has features specifically for reporting bugs and
  is simple to understand for OpenROAD developers as well as novice
  users. It provides a lingua franca in the community to discuss features
  and test cases.
- [Hammer](https://chipyard.readthedocs.io/en/latest/VLSI/Hammer.html) is used with
  Chipyard.
- https://www.zeroasic.com/ has a Python based workflow that supports both
  commercial tools and OpenROAD.

Why Bazel on top of ORFS?
-------------------------

ORFS and OpenROAD is work in progress and one should expect for
large designs to get involved with the community or need a
support contract with Precision Innovations (https://www.linkedin.com/in/tomspyrou/).

Using ORFS directly, instead of modifying it or creating an alternative flow,
makes it easy to get the very latest features and version of OpenROAD and ORFS
as well as having access to the tools, `make issue` and `deltaDebug.py`,
required to articulate familiar and easily actionable github issues for
the OpenROAD and ORFS maintainers.

Challenges with large designs and ORFS that Bazel helps address
---------------------------------------------------------------

- **Long build times**; hours, days.
- **Artifacts** are needed. Synthesis, for instance, can
  be very time consuming and it is useful to share synthesis artifacts
  between developers and CI servers. On a large design with multiple
  developers and many pull requests in flight, it can become error
  prone to manually track exactly what version of built stages that
  are still valid. Ideally one should be able to check out a
  pull request and automatically get the right prebuilt artifacts.
- **Dependencies** in ORFS are at the file level. For instance, synthesis must be
  redone if the clock period changes, but many other changes to .sdc do not require
  resynthesis. With finer grained dependencies, superfluous time consuming
  resynthesis, floor planning, placement, cts and routing can be avoided.
- **Examining failures** for global/detailed place/route, that can take many
  hours to build, is useful. Artifacts for failed stages are needed to
  examine the problem: failed .odb file as well as any reports. This workflow
  always existed for detailed routing: detailed routing succeeds, has exit code 0,
  even if there are DRC errors.
- **Mocking abstracts** when doing initial top-level floorplanning is needed to
  separate concerns. It can be useful to skip one of place, cts, route for
  the macros until one starts to converge on a workable
  top level floorplan. This is supported via `abstract_stage` in `openroad.bzl`
- **Efficient local storage of build artifacts** are needed as .odb files are
  large and they should not exist in duplicates unnecessarily. Bazel
  uses symbolic links. ORFS can not use symbolic links for .odb files because,
  long story short, `make` does not work properly with symbolic links. This becomes
  especially important when working with many branches and pull requests where
  there is a large degree of shared .odb files.
- **Parallel builds** are required for macros.
- **Remote build services** are required for large projects where
  developers machines are powerful enough to examine results, but
  not to run builds.
- **Cross cutting builds** such as completing floor planning for all macros,
  then place, then cts, then route is required to be able to separate concerns.
  When iterating on the concerns, it can be useful to complete placement under
  human supervision to iterate quickly, but to leave routing for CI servers to complete.
- **Select level of detail of artifacts** is useful throughout the
  development process. Initially for a macro, artifacts are useful for inspection
  for synthesis, floorplan, place, cts, route and abstract. Later, for stable macros,
  abstracts are adequate(no .odb file, only .lef, .lib and .gds).

## Requirements

* [Bazelisk](https://bazel.build/install/bazelisk) or [Bazel](https://bazel.build/install) - if using Bazel, please refer to [.bazelversion](./.bazelversion) file for the recommended version of the tool.
* [Docker](https://docs.docker.com/get-docker/) - Bazel utilizes Docker to set up the environment using ORFS artifacts from the container.
  The Docker image used in the flow defaults to `openroad/orfs`, with tag specified in the [module](./MODULE.bzl) file.

  > **NOTE:** The `bazel-orfs` doesn't execute flows inside the Docker container, but rather uses the container as a source of ORFS artifacts.
* [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) - **Required only when using customized ORFS** - to use it, `env.sh` file from OpenROAD-flow-scripts has to be sourced or `FLOW_HOME` environment variable has to be set to the path of the local `OpenROAD-flow-scripts/flow` installation.
  Bazel-orfs intentionally does not treat ORFS as an installable versioned tool, but prefers to rely on local installation such that it is easy to modify ORFS and OpenROAD.

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
    stage_args = {
        "synth": {
            "SDC_FILE": "$(location :test/constraints-top.sdc)",
            "SYNTH_HIERARCHICAL": "1",
        },
        "floorplan": {
            "CORE_UTILIZATION": "3",
            "RTLMP_FLOW": "True",
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

Macro from the example above spawns the following Bazel targets:

```
Dependency targets:
  //:L1MetadataArray_cts_deps
  //:L1MetadataArray_floorplan_deps
  //:L1MetadataArray_place_deps
  //:L1MetadataArray_route_deps
  //:L1MetadataArray_synth_deps

Stage targets:
  //:L1MetadataArray_synth
  //:L1MetadataArray_floorplan
  //:L1MetadataArray_place
  //:L1MetadataArray_cts
  //:L1MetadataArray_route

Abstract targets:
  //:L1MetadataArray_generate_abstract
```

The example comes from the [BUILD](./BUILD) file in this repository.
For details about targets spawned by this macro please refer to [Implementation](#Implementation) chapter.

## Implementation

### openroad.bzl

This file contains simple helper functions written in Starlark as well as macro `orfs_flow()`.
The implementation of this macro spawns multiple `genrule` native rules which are responsible for preparing and running ORFS physical design flow targets during Bazel build stage.

These are the genrules spawned in this macro:

* ORFS stage-specific (named: `target_name + “_” + stage`)
* ORFS stage dependencies (named: `target_name + “_” + stage + “_deps”`)
* Abstract targets (named: `target_name + “_generate_abstract”`)

### Bazel flow

Regular Bazel flow uses artifacts from the Docker environment with preinstalled ORFS to run the Physical Design Flow.

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

Setting this attribute to a valid image and checksum will enable Bazel to automatically pull the image and extract ORFS artifacts.

```bash
bazel run @bazel-orfs//:<target>_<stage> -- <absolute_path>
```

If the directory under the `<absolute_path>` does not exist, it will be created.

> **NOTE:** It's important to provide an absolute path to the directory where the results of the flow will be stored.
> Otherwise, the flow will fail with an error message similar to:
>
> ```
> INFO: Running command line: bazel-bin/<target>_<stage>.sh build
> <target>_<stage>.sh: 'build' is not an absolute path
> Try '<target>_<stage>.sh -h' for more information.
> ```

### Local flow

The locally modified [OpenROAD-flow-scripts](https://openroad-flow-scripts.readthedocs.io/en/latest/user/UserGuide.html) can also be used to run the Physical Design Flow.
Once the environment is set up with Bazel, produced `make` script can be used to run the flow:

```bash
bazel run @bazel-orfs//:<target>_<stage>_deps -- <absolute_path>
<absolute_path>/make <stage>
```

A convenient way to re-run for floorplan and view the results would be:

```bash
bazel run MyDesign_floorplan -- `pwd`/build && build/make gui_floorplan
```

By default, the `make <stage>` invocation will rely on the ORFS from MODULE.bazel, unless the `env.sh` script is sourced, or the `FLOW_HOME` environment variable is set to the path of the local `OpenROAD-flow-scripts/flow` installation:

```bash
source <orfs_path>/env.sh

bazel run @bazel-orfs//:<target>_<stage>_deps -- <absolute_path>
<absolute_path>/make <stage>
```

> **NOTE:** This requires building of each stage sequentially, starting from the first one specified in the [Stage targets](#stage-targets) list.

For the ORFS installation guide please refer to the [build instructions](https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildLocally.html) guide.

### Stage targets

Each stage of the physical design flow is represented by a separate target and follows the naming convention: `target_name + “_” + stage`.

The stages are as follows:

* `synth` (synthesis)
* `floorplan`
* `place`
* `cts` (clock tree synthesis)
* `route`
* `final`

CLI and GUI is not available as Bazel targets, however, they can be run from the generated shell script as described in the [GUI targets](#gui-targets) paragraph.

### Abstract targets

Those targets are used to create mocked abstracts (`LEF` files) for macros.
The mock contains the description of macro which has its whole internal logic removed.
At the same time the mock has the same pinout as the original macro and similar size which makes it useful in early design stages.

Mocked abstracts are generated at the `target + "generate_abstract"` stage, which follows one defined via `abstract_stage` attribute passed to the `orfs_flow()` macro:

<pre lang="starlark">
orfs_flow(
    name = "tag_array_64x184",
    <b>abstract_stage = "floorplan",</b>
    stage_args = {
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

> **NOTE:** Mocked abstracts can be generated starting from the `floorplan` stage, thus skipping the `synth` stage.

Mocked abstracts are intended to be used in builds of other parts of the design that use the given macro.
They're useful for estimating sizes of macros with long build times and checking if they will fit in upper-level modules without running time consuming place and route flow.

> **NOTE:** Stages that follow the one passed to `abstract_stage` will not be created by the `orfs_flow()` macro.

### Constraints handling

Constraint files are passed down to `orfs_flow()` macro through [Stage targets](#stage-targets) arguments and sources:

<pre lang="starlark">
orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "synth",
    <b>stage_args = {
        "synth": {
            "SDC_FILE": "$(location :constraints-sram)",
        },
    },
    stage_sources = {
        "synth": [":constraints-sram"],
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

The dependency targets fall under the `target_name + “_” + stage + “_deps”` naming convention, and are used to prepare the environment for running the ORFS stage targets.
Each stage of the physical design flow depend on two generated `.mk` files that provide the configuration for the ORFS.
One is specific for the stage of the flow and the second one is common for the whole design being built.

They can be found under the following paths:

```bash
<path>/config.mk                                                        # Common for the whole design
<path>/results/<module>/<target>/base/<stage_number>_<stage>.short.mk   # Specific for the stage
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
bazel run @bazel-orfs//:<target>_<stage> -- <absolute_path>
<absolute_path>/make gui_<stage>
```

For the CLI:

```bash
bazel run @bazel-orfs//:<target>_<stage> -- <absolute_path>
<absolute_path>/make open_<stage>
```

CLI and GUI is not available for all stages, consequently these targets are created only for:

* `floorplan`
* `place`
* `cts` (clock tree synthesis)
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
  build/make synth

  # Initialize dependencies for the Floorplan stage for L1MetadataArray target
  bazel run @bazel-orfs//:L1MetadataArray_floorplan_deps -- `pwd`/build
  ```

3. Execute the shell script with ORFS make target relevant to given stage of the flow:

  ```bash
  build/make floorplan
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
+    abstract_stage = "floorplan",
     macros = ["tag_array_64x184_generate_abstract"],
     stage_args = {
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

For more information please refer to the description of [Abstract targets](#abstract-targets).

## Bazel hacking

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
     stage_args = {
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
