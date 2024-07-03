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

* [Bazelisk](https://bazel.build/install/bazelisk) or [Bazel](https://bazel.build/install) - if using `bazel`, please refer to [.bazelversion](./.bazelversion) file for the recommended version of the tool.
* [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) - **Required only for running local scripts** - to use it, `env.sh` file from OpenROAD-flow-scripts has to be sourced or `FLOW_HOME` environmental variable has to be set manually to `OpenROAD-flow-scripts/flow` location.
  Bazel-orfs intentionally does not treat ORFS as a installable versioned tool, but prefers to rely on local installation such that it is easy to hack ORFS and OpenROAD.
* [Docker](https://docs.docker.com/get-docker/) - **Required for running `Stage` targets and Docker scripts**
* Docker image with ORFS used in `build_openroad` macro - **Required only for running `Stage` targets**. If `docker_image` points to locally available image, it will be used.
  Otherwise, ORFS will pull the requested image, if available.

## Usage

Core functionality is implemented as `build_openroad()` bazel macro in `openroad.bzl` file.

In order to use `build_openroad()` macro in Bazel Workspace in other project it is required to use bazel-orfs as external dependency through one of [Bazel Module Methods](https://bazel.build/rules/lib/globals/module):
* from git repository
  ```
  bazel_dep(name = "bazel-orfs")
  git_override(
      module_name = "bazel-orfs",
      remote = "<URL to bazel-orfs repository>",
      commit = "<git hash for specific bazel-orfs revision>"
  )
  ```
* from local directory
  ```
  bazel_dep(name = "bazel-orfs")
  local_path_override(
      module_name = "bazel-orfs", path = "<path to local bazel-orfs workspace>"
  )
  ```

Then load the macro in BUILD file where it should be used, and create rule for `out` script, which can find the latest file with logs:

```
load("@bazel-orfs//:openroad.bzl", "build_openroad", "create_out_rule")
create_out_rule()
```

The macro can now be placed in the BUILD file. The macro usage can look like this:

```
build_openroad(
    name = "L1MetadataArray",
    docker_image = "openroad/orfs:f8d87d5bf1b2fa9a7e8724d1586a674180b31ae9",
    io_constraints = ":io",
    macros = ["tag_array_64x184"],
    abstract_stage = "grt",
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
Scripts targets:
  //:L1MetadataArray_test_clock_period_scripts
  //:L1MetadataArray_test_synth_sdc_scripts
  //:L1MetadataArray_test_synth_scripts
  //:L1MetadataArray_test_floorplan_scripts
  //:L1MetadataArray_test_place_scripts
  //:L1MetadataArray_test_cts_scripts
  //:L1MetadataArray_test_grt_scripts
  //:L1MetadataArray_test_generate_abstract_scripts

Make targets:
  //:L1MetadataArray_test_clock_period_make
  //:L1MetadataArray_test_synth_sdc_make
  //:L1MetadataArray_test_synth_make
  //:L1MetadataArray_test_floorplan_make
  //:L1MetadataArray_test_place_make
  //:L1MetadataArray_test_cts_make
  //:L1MetadataArray_test_grt_make
  //:L1MetadataArray_test_generate_abstract_make

GUI targets:
  //:L1MetadataArray_test_synth_gui
  //:L1MetadataArray_test_floorplan_gui
  //:L1MetadataArray_test_place_gui
  //:L1MetadataArray_test_cts_gui
  //:L1MetadataArray_test_grt_gui

Config generation targets:

  Design config:
    //:L1MetadataArray_test_config
    //:L1MetadataArray_test_config.mk

  Stage configs:
    //:L1MetadataArray_test_clock_period_config
    //:L1MetadataArray_test_clock_period_config.mk
    //:L1MetadataArray_test_synth_sdc_config
    //:L1MetadataArray_test_synth_sdc_config.mk
    //:L1MetadataArray_test_synth_config
    //:L1MetadataArray_test_synth_config.mk
    //:L1MetadataArray_test_gui_synth_config
    //:L1MetadataArray_test_gui_synth_config.mk
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

The example comes from the [BUILD](./BUILD) file in this repository.
For details about targets spawned by this macro please refer to [Implementation](#Implementation) chapter.

## Implementation

### openroad.bzl

This file contains simple helper functions written in starlark as well as macro `build_openroad()`.
The implementation of this macro spawns multiple `genrule` native rules which are responsible for preparing and running ORFS physical design flow targets during bazel build stage.

These are the genrules spawned in this macro:

* Config generation targets
  * Common for the whole design (named: `target_name + “_config”`)
  * ORFS stage-specific config (named: `target_name + “_” + stage + “_config”`)
* Scripts targets (named: `target_name + “_” + stage + “_scripts”`)
  * Prepares local and Docker flow scripts which run the ORFS
* Make targets (named: `target_name + “_” + stage + “_make”`)
  * Builds all dependencies required for the stage and generates scripts
* Special mock flow: Mock Area targets (named: `target_name + “_” + stage + “_mock_area”`)
* GUI targets (named: `target_name + “_” + stage + “_gui”`)
  * Generates scripts and prepare dependencies required for running GUI for `stage`

#### Docker flow

Docker flow uses containerized environment with preinstalled ORFS to run the Physical Design Flow.

It implicitly depends on a Docker image with installed ORFS environment being present in Docker runtime of the machine running Bazel targets.
Each `build_openroad` instance has to define `docker_image` attribute - list of publicly available images: https://hub.docker.com/r/openroad/orfs/tags.
Setting this attribute to a valid registry and image within this registry will enable Docker to automatically pull the image if it's not available locally.
Users can also build the image from ORFS sources following [the guide](https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildWithDocker.html#build-using-docker-from-sources) and update the `docker_image` to use the same name as the built image.

#### Local flow

The local flow depends on the locally installed ORFS.
Path to `OpenROAD-flow-scripts/flow` is expected to be specified in `FLOW_HOME` environmental variable.
For the installation guide please refer to the [build instructions](https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildLocally.html).

#### Config files

Each stage of the physical design flow depend on two generated `config.mk` files that provide the configuration for the ORFS.
One is specific for the stage of the flow and the second one is common for the whole design being built.
Design-specific config includes the stage-specific config through `STAGE_CONFIG` environment variable that is set in the `build_openroad()` macro implementation.

#### Entrypoint scripts

There is one entrypoint script for each kind of the flow.
For the local flow it is the [orfs](./orfs) script and for the Docker flow it's the [docker_shell](./docker_shell.sh) script.
Both of those scripts have the same responsibility of preparing and entering the ORFS build environment and then executing the build command for given ORFS stage.
`orfs` does this by setting some initial environment variables and sourcing `env.sh` from ORFS.
`docker_shell` is very similar in that matter except it runs the flow in a Docker container.
The input and output files for the flow stage are passed to the running container through [bind mounts](https://docs.docker.com/storage/#bind-mounts).

#### Scripts targets

These rules generate two scripts, one for local flow and other for Docker flow.
They can be found under path:

```
bazel-bin/<target_name>_local_make  # Local flow
bazel-bin/<target_name>_docker      # Docker flow
```

Shell scripts are produced by `genrule` by concatenating shell shebang line with the entrypoint command.
The entrypoint command consists of a call to `orfs` or `docker_shell`, essential environment variables definitions (e.g. with paths to generated `config.mk` files) and physical design make targets to execute in ORFS environment.
Attribute `srcs` of the genrule contains dependencies required for running the script (e.g.: `orfs` script, make target patterns, configs).
Those dependencies don't include results of previous flow stages and because of that, it is required to build those before running the generated script.
In the second rule (`sh_binary`), the script is created so that it can be executed straight from the output directory.

Created shell scripts, apart from facilitating quick tests of ORFS modifications, can be used to run ORFS stages straight from the bazel-orfs repository and to allow tweaking the "moving parts" of the flow, like e.g.:
* Design and stage configs
* Make targets patterns
* entrypoint command line

Additionally, script finding the latest log files will be created - by default it displays full path (without symlinks) to the `bazel-bin` and with `--tail` option it shows full path to the latest log.
It can be found under the path:
```
bazel-bin/out
```

#### Make targets

Targets build all necessary dependencies for chosen stage and scripts from [scripts target](#scripts-targets).
Those dependencies are built with the Docker flow.
Before running stage targets it is required to first pull the ORFS Docker image into local Docker runtime.

#### Mock Area targets

Those targets are used to create mocked abstracts (LEF files) for macros.
The mock contains the description of macro which has its whole internal logic removed.
At the same time the mock has the same pinout as the original macro and similar size which makes it useful in early design stages.
Mocked abstracts are generated after the floorplan stage to be then used in builds of other parts of the design that use given macro.
Used for estimating sizes of macros with long build times and checking if they will fit in upper-level modules without running time consuming place and route flow.

#### GUI targets

Those targets are used to prepare environment for running OpenROAD CLI or GUI.
E.g. `bazel build L1MetadataArray_full_final_gui` builds all dependencies required for running `open_final` and `gui_final` targets.

CLI and GUI is not available for all stages, consequently these targets are created only for:
* synthesis
* floorplan
* place
* cts (clock tree synthesis)
* grt (global route)
* route
* final

### Constraints handling

Constraint files are passed down to `build_openroad()` macro through attributes:
* io_constraints
* sdc_constraints

Those accept a Bazel label that points to the file.
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
        ":util",
    ],
)
```

Please, note that only the first script from filegroup will be used.
So `:io` defines `test/io.tcl` as constraints and `test/utils.tcl` as its dependency.

## Tutorial

This tutorial uses the Docker flow to run the Physical Design Flow with ORFS.
Before starting, it is required to have available in your Docker runtime a image with `OpenROAD-flow-scripts` installation.
For more information, please refer to the [Requirements](#requirements) paragraph.

### Hello world

A quick test-build:

```
# Build L1MetadataArray dependencies for the CTS stage
bazel build L1MetadataArray_test_cts_make

# Build CTS stage for L1MetadataArray macro with local of Docker flow
./bazel-bin/L1MetadataArray_test_cts_local_make bazel-cts
./bazel-bin/L1MetadataArray_test_cts_docker bazel-cts

# Tail the latest log file
tail -f $(./bazel-bin/out -t)
```

### Using the local flow

The local flow allows testing the build with locally built OpenROAD-flow-scripts.
It is based on bazel `Make` targets, for more information on those, please refer to relevant [implementation](#make-targets) paragraph.
Example usage of `Make` targets can look like this:

Let's assume we want to perform a floorplan stage for the `L1MetadataArray` design using the locally built ORFS.

1. Provide all the dependencies for running the target and generate scripts.
  ```
  bazel build L1MetadataArray_test_floorplan_make
  ```

2. Source `env.sh` of your local ORFS installation or set the `FLOW_HOME` environment variable to the path to your local `OpenROAD-flow-scripts/flow` directory.
  ```
  source <path-to-ORFS>/env.sh
  # or
  export FLOW_HOME=<path-to-ORFS>/flow
  ```

3. Execute the shell script with ORFS make target relevant to given stage of the flow.
  The script is capable of running all make targets that have the same requirements as e.g. `do-floorplan` target
  ```
  ./bazel-bin/L1MetadataArray_test_floorplan_local_make bazel-floorplan
  ```

### Running OpenROAD GUI

Let's assume we want to run a GUI for final stage for the `L1MetadataArray`.

1. Build dependencies needed for final stage.
  ```
  bazel build L1MetadataArray_full_final_gui
  ```
2. Run GUI with local of Docker flow.
  ```
  # local flow
  export FLOW_HOME=<path-to-ORFS>/flow
  ./bazel-bin/L1MetadataArray_full_final_local_make gui_final

  # Docker flow
  ./bazel-bin/L1MetadataArray_full_final_docker gui_final
  ```

### Tweaking aspect ratio of a floorplan

Notice how the `CORE_ASPECT_RATIO` parameter is associated with
the floorplan and *only* the floorplan stage below.

Bazel will detect this change specifically as a change to the
floorplan, re-use the synthesis result and rebuild from the
floorplan stage. Similarly, if the `PLACE_DENSITY` is modified,
only stages from the placement and on are re-built.

Also, notice that when the aspect ratio is changed back to
a value for which there exists artifacts, Bazel completes
instantaneously as the artifact already exists:

```
diff --git a/BUILD b/BUILD
index 92d1a62..58c0ec0 100644
--- a/BUILD
+++ b/BUILD
@@ -59,7 +59,7 @@ build_openroad(
     stage_args = {
         "floorplan": [
             "CORE_UTILIZATION=40",
-            "CORE_ASPECT_RATIO=2",
+            "CORE_ASPECT_RATIO=4",
         ],
         "place": ["PLACE_DENSITY=0.65"],
     },
```

Then run a quick test-build Bazel:

```
# Build tag_array_64x184 macro up to the floorplan stage
bazel build tag_array_64x184_floorplan

# View final results from Bazel
bazel build tag_array_64x184_floorplan_gui
./bazel-bin/tag_array_64x184_floorplan_docker gui_floorplan
```

### Fast floorplanning and mock abstracts


Let's say we want to skip place, cts and route and create a mock abstract where
we can at least check that there is enough place for the macros at the top level.

> **Warning:**
Although mock abstracts can speed up turnaround times, skipping place, cts or route can lead to errors and problems that don't exist when place, cts and route are not skipped.

To do so, we modify in `BUILD` file the `abstract_stage` attribute of `build_openroad` macro to `floorplan` stage:

```
diff --git a/BUILD b/BUILD
index 92d1a62..1f6e46b 100644
--- a/BUILD
+++ b/BUILD
@@ -88,7 +88,7 @@ build_openroad(
     io_constraints = ":io",
     macros = ["tag_array_64x184"],
-    abstract_stage = "grt",
+    abstract_stage = "cts",
     sdc_constraints = ":test/constraints-top.sdc",
     stage_args = {
         "synth": ["SYNTH_HIERARCHICAL=1"],
```

Then run:

```
bazel build L1MetadataArray_test_generate_abstract
```

This will cause the `mock area` targets to generate the abstracts for the design right after the `floorplan` stage instead of `grt` stage.
For more information please refer to the description of [mock area targets](#mock-area-targets).

### Using external PDK

Bazel-orfs allows the usage of external PDKs.
The external PDK should be delivered as a link to archive with PDK contents.
PDK should consist of all files described in [ORFS platform configuration](https://openroad-flow-scripts.readthedocs.io/en/latest/contrib/PlatformBringUp.html#platform-configuration) paragraph.
The link to the archive should be used to specify the PDK as an external bazel dependency through [archive_override](https://bazel.build/rules/lib/globals/module#archive_override).
For example in `MODULE.bazel` file:

```
bazel_dep(name = "external_pdk", version = "1.0.0")
archive_override(
    module_name = "external_pdk",
    patches = ["//external_pdk:external_pdk.patch"],
    urls = "<URL to PDK archive>",
)
```

Additionally, a `patch` is provided to set up a proper bazel module with subpackages for the particular PDK (in this example it is asap7).

```
diff --git a/BUILD b/BUILD
new file mode 100644
index 0000000..0d57ccb
--- /dev/null
+++ BUILD
@@ -0,0 +1,3 @@
+package(
+       default_visibility = ["//visibility:public"],
+)
diff --git a/MODULE.bazel b/MODULE.bazel
new file mode 100644
index 0000000..8419e9b
--- /dev/null
+++ MODULE.bazel
@@ -0,0 +1 @@
+module(name="external_pdk")
diff --git a/asap7/BUILD b/asap7/BUILD
new file mode 100644
index 0000000..c92202a
--- /dev/null
+++ asap7/BUILD
@@ -0,0 +1,10 @@
+package(
+       default_visibility = ["//visibility:public"],
+)
+filegroup(
+       name = "asap7",
+       srcs = glob([
+               "**"
+       ]),
+    visibility = ["//visibility:public"],
+)
```

In order to use such imported external PDK it is required to use `external_pdk` attribute of the `build_openroad()` macro.
The attribute accepts label-like strings that point to the bazel package containing all PDK files e.g.:

```
build_openroad(
    name = "tag_array_64x184",
    external_pdk = "@external_pdk//asap7",
    ...
    variant = "external_pdk",
    ...
)

build_openroad(
    name = "L1MetadataArray",
    external_pdk = "@external_pdk//asap7",
    ...
    macro_variants = {"tag_array_64x184": "external_pdk"},
    macros = ["tag_array_64x184"],
    ...
    variant = "external_pdk",
    ...
)
```

> **Note:** In order to specify correct macro variants when building macros/modules higher in design hierarchy please use `macro_variants` attribute.

## Bazel hacking

### Run all synth targets

```
bazel build $(bazel query '...:*' | grep '_synth$')
```

### Forcing a rebuild of a stage

Sometimes it is desirable, such as when hacking ORFS, to redo a build stage even
if none of the dependencies for that stage changed. This can be achieved by changing
a `PHONY` variable to that stage and bumping it:

```
diff --git a/BUILD b/BUILD
index 92d1a62..4dba0dd 100644
--- a/BUILD
+++ b/BUILD
@@ -97,6 +97,7 @@ build_openroad(
             "RTLMP_FLOW=True",
             "CORE_MARGIN=2",
             "MACRO_PLACE_HALO=10 10",
+            "PHONY=1",
         ],
         "place": [
             "PLACE_DENSITY=0.20",
```

### Building the immediate dependencies of a target

```
bazel build L1MetadataArray_test_synth_make
```
