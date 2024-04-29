# Bazel-orfs

This repository contains [Bazel](https://bazel.build/) rules for wrapping Physical Design Flows provided by [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts). It provides two variants of the bazel flow:

* Docker flow - based on ORFS installed in the docker container that is used for running bazel targets
* Local flow - relies on local installation of the ORFS

## Requirements

* [Bazelisk](https://bazel.build/install/bazelisk) or [Bazel](https://bazel.build/install) - if using `bazel`, please refer to `.bazelversion` file for the recommended version of the tool.
* [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) - **Required only for running local scripts** - to use it, `env.sh` file from OpenROAD-flow-scripts has to be sourced or `FLOW_HOME` environmental variable has to be set manually to `OpenROAD-flow-scripts/flow` location. `bazel-orfs` intentionally does not treat OpenROAD-flow-scripts as a installable versioned tool, but prefers to rely on local installation such that it is easy to hack ORFS and OpenROAD.
* [Docker](https://docs.docker.com/get-docker/) - **Required for running `Make` targets and Docker scripts**
* Docker image with ORFS installation - **Required only for running `Stage` targets** - can be obtained in two ways:

  * running `bazel run orfs_env` which downloads the docker image from container registry and loads it to docker runtime under name: `openroad/flow-ubuntu22.04-builder:latest`
  * [Building the image locally](https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildWithDocker.html#build-using-docker-from-sources)
  * Pulling the image manually from the container registry with:
    ```
    docker pull ghcr.io/antmicro/openroad-flow-scripts/ubuntu22.04:latest
    ```
    In such case the `docker_image` attribute of `build_openroad` macro must be set to `ghcr.io/antmicro/openroad-flow-scripts/ubuntu22.04:latest`
  * Providing different docker image and overriding default used in the flow through `docker_image` attribute of `build_openroad` macro

## Usage

Core functionality is implemented as `build_openroad()` bazel macro in `openroad.bzl` file.

In order to use `build_openroad()` macro in Bazel Workspace in other project it is required to pull `bazel-orfs` as external dependency through one of [Bazel Module Methods](https://bazel.build/rules/lib/globals/module). For example in project's MODULE.bazel:

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
Scripts targets:
  //:L1MetadataArray_test_clock_period_scripts
  //:L1MetadataArray_test_synth_sdc_scripts
  //:L1MetadataArray_test_synth_scripts
  //:L1MetadataArray_test_memory_scripts
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
  //:L1MetadataArray_test_memory_make

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
    //:L1MetadataArray_test_memory_config
    //:L1MetadataArray_test_memory_config.mk
```

The example comes from the `BUILD` file in this repository.
For details about targets spawned by this macro please refer to `Implementation` chapter.

## Implementation

### openroad.bzl

This file contains simple helper functions written in starlark as well as macro `build_openroad()`.
The implementation of this macro spawns multiple `genrule` native rules which are responsible for preparing and running ORFS physical design flow targets during bazel build stage.

These are the genrules spawned in this macro:

* Config generation targets
  * Common for the whole design (named: `target_name + “_config”`)
  * ORFS stage-specific config (named: `target_name + “_” + stage + “_config”`)
* Scripts targets (named: `target_name + “_” + stage + “_scripts”`)
  * Prepares local and Docker flow scripts which build the stage
* Make targets (named: `target_name + “_” + stage + “_make”`)
  * Builds all dependencies required for the stage and generates scripts
* Special mock flow: Mock Area targets (named: `target_name + “_” + stage + “_mock_area”`)

#### Docker flow

Docker flow uses containerized environment with preinstalled ORFS to run the physical design flow.

It implicitly depends on a docker image with installed ORFS environment being present in docker runtime of the machine running bazel targets.
The docker image used in the flow defaults to `ghcr.io/antmicro/openroad-flow-scripts/ubuntu22.04:latest`.
The default can be overridden per `build_openroad` instance with a `docker_image` attribute.
Setting this attribute to a valid registry and image within this registry will enable docker to automatically pull the image if it's not available locally.
Users can also build the image from ORFS sources following [the guide](https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildWithDocker.html#build-using-docker-from-sources).

#### Local flow

The local flow depends on the locally installed ORFS.
Path to `OpenROAD-flow-scripts/flow` is expected to be specified in `FLOW_HOME` environmental variable.
For the installation guide please refer to the [build instructions](https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildLocally.html).
The local flow relies on `_scripts` bazel targets which are used to generate shell scripts.

#### Config files

Each stage of the physical design flow depend on two generated `config.mk` files that provide the configuration for the ORFS.
One is specific for the stage of the flow and the second one is common for the whole design being built.
Design-specific config includes the stage-specific config through `STAGE_CONFIG` environment variable that is set in the `build_openroad()` macro implementation.

#### Entrypoint scripts

There is one entrypoint script for each kind of the flow.
For the local flow it is the `orfs` script and for the docker flow it's the `docker_shell` script.
Both of those scripts have the same responsibility of preparing and entering the ORFS build environment and then executing the build command prepared for given ORFS stage.
`orfs` does this by setting some initial environment variables and sourcing `env.sh` from ORFS.
`docker_shell` is very similar in that matter except it runs the flow in a docker container.
The input and output files for the flow stage are passed to the running container through [bind mounts](https://docs.docker.com/storage/#bind-mounts).

#### Scripts Targets

These rules generate two scripts, one for local flow and other for Docker flow.
They can be found under path:

```
bazel-bin/<target_name>_local_make
bazel-bin/<target_name>_docker
```

Shell scripts are produced by `genrule` by concatenating shell shebang line with the entrypoint command.
The entrypoint command consists of a call to `orfs` or `docker_shell`, essential environment variables definitions (e.g. with paths to generated `config.mk` files) and physical design make targets to execute in ORFS environment.
Attribute `srcs` of the genrule contains dependencies required for running the script (e.g.: `orfs` script, make target patterns, configs).
Those dependencies don't include results of previous flow stages and because of that, it is required to build those before running the generated script.
In the second rule (`sh_binary`) for the script is created so that it can be executed straight from the output directory.

Created shell scripts, apart from facilitating quick tests of ORFS modifications, can be used to run ORFS stages straight from the bazel-orfs repository and to allow tweaking the "moving parts" of the flow, like e.g.:
* Design and stage configs
* Make targets patterns
* entrypoint command line

#### Make Targets

Targets build all necessary dependencies for chosen stage and both scripts from scripts target.
Those dependencies are built with the docker flow.
Before running stage targets it is required to first pull the ORFS docker image into local docker runtime.

#### Mock Area Targets

Those targets are used to create mocked abstracts (LEF files) for macros.
The mock contains the description of macro which has its whole internal logic removed.
At the same time the mock has the same pinout as the original macro and similar size which makes it useful in early design stages.
Mocked abstracts are generated after the `floorplan` stage to be then used in builds of other parts of the design that use given macro.
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

## Tutorial

This tutorial uses the `docker flow` to run the physical design flow with ORFS.
Before starting, it is required to have available in your docker runtime a docker image with `OpenROAD-flow-scripts` installation.
For more information, please refer to the [Requirements](#requirements) paragraph.

### Hello world

A quick test-build:

```
# Download and load docker image with ORFS
bazel run @bazel-orfs//:orfs_env

# Build L1MetadataArray dependencies for the CTS stage
bazel build L1MetadataArray_test_cts_make

# Build CTS stage for L1MetadataArray macro with local of Docker flow
./bazel-bin/L1MetadataArray_test_cts_local_make bazel-cts
./bazel-bin/L1MetadataArray_test_cts_docker bazel-cts
```

### Using the local flow

The local flow allows testing the build with locally built OpenROAD-flow-scripts.
It is based on bazel `Make` targets, for more information on those, please refer to relevant [implementation](#make-targets) paragraph.
Example usage of `Make` targets can look like this:

Let's assume we want to perform a `floorplan` stage for the `L1MetadataArray` design using the locally built ORFS.

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
```

### Fast floorplanning and mock abstracts


Let's say we want to skip place, cts and route and create a mock abstract where
we can at least check that there is enough place for the macros at the top level.

---

**Warning:**
Although mock abstracts can speed up turnaround times, skipping place, cts or route can lead to errors and problems that don't exist when place, cts and route are not skipped.

---

To do so, we modify in `BUILD` file the `mock_stage` attribute of `build_openroad` macro to `floorplan` stage:

```
diff --git a/BUILD b/BUILD
index 92d1a62..1f6e46b 100644
--- a/BUILD
+++ b/BUILD
@@ -88,7 +88,7 @@ build_openroad(
     io_constraints = ":io",
     macros = ["tag_array_64x184"],
     mock_abstract = True,
-    mock_stage = "grt",
+    mock_stage = "cts",
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
bazel build $(bazel query 'deps(<target label e.g. L1MetadataArray_test_synth>, 1)' --noimplicit_deps)
```

## Tentative roadmap

- ORFS and orfs_rules should be independently versioned dependencies
  while it should still be easy to do local hacking of ORFS. There should be a version
  number for the ORFS dependency and orfs_rules separately. It should be possible to
  specify the ORFS version per invocation of orfs_rules such that e.g. macros are not
  rebuilt unless the user wants them to be rebuilt. Some macros can take days to build
  and there could be manual verification involved and hence rebuilding should be
  more controllable than for your typical Bazel build that is reasonably fast (C++, Scala,
  etc.)
- Once a reasonable structure is in place, set up CI for pull requests and invite
  refinements and developments from the community.

