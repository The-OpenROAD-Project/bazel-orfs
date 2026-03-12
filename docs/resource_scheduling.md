# Resource Scheduling for Bazel Actions

## The problem

Bazel defaults to 1 CPU per action, allowing many actions to run in parallel.
OpenROAD stages that spawn internal threads suffer severe slowdowns from this:
context switching and cache thrashing dominate when N actions each spawn
NUM_CORES threads on NUM_CORES physical cores.

Evidence: `tag_array_64x184` global placement (379 cells) takes 1.4s alone but
521s inside `bazelisk test ...`. Same computation, same output — 370x slower.

## The fix

Every `ctx.actions.run_shell()` call declares a `resource_set`. Multi-threaded
stages request all CPUs so Bazel runs at most one at a time. Single-threaded
stages request 1 CPU, allowing full parallelism.

A `repository_rule` (`detect_cpus`) runs hermetic Python's `os.cpu_count()`
once at workspace setup to determine the host CPU count. This is written to
`@host_cpus//:cpus.bzl` as `NUM_CPUS` and loaded by `openroad.bzl`.

## Stage threading classification

OpenROAD is always invoked with `-threads NUM_CORES`, but ORFS's `load.tcl`
immediately sets `sta::set_thread_count 1` (workaround for flaky STA in
rel_3.0+). Only algorithms with their own internal threading (OpenMP, etc.)
actually use multiple cores.

### Multi-threaded stages (request all CPUs)

| Stage   | Make target    | Multi-threaded sub-stages                                                                           |
|---------|----------------|------------------------------------------------------------------------------------------------------|
| place   | `do-place`     | `global_placement` (RePlAce, OpenMP), `global_placement -incremental` (resize), `detailed_placement` |
| cts     | `do-cts`       | `clock_tree_synthesis` (TritonCTS), `detailed_placement`, `repair_timing_helper`                      |
| grt     | `do-5_1_grt`   | `global_route` (FastRoute), `repair_design_helper`, `repair_timing_helper`, `detailed_placement`     |
| route   | `do-5_2_route` | `detailed_route` (TritonRoute, heavily threaded)                                                     |

### Single-threaded stages (request 1 CPU)

| Stage             | Make target            | Sub-stages                                              |
|-------------------|------------------------|---------------------------------------------------------|
| synth             | `do-yosys`             | Yosys synthesis (single-threaded)                       |
| floorplan         | `do-floorplan`         | `floorplan`, `macro_place`, `tapcell`, `pdn`            |
| final             | `do-final`             | `density_fill`, `final_report`, KLayout GDS merge       |
| generate_abstract | `do-generate_abstract` | `write_timing_model`, `write_abstract_lef`              |

### Empirical thread counts (tag_array_64x184, ASAP7, 16-core host)

Measured via `ps -eo nlwp` sampling at 200ms intervals:

| TCL script              | Max threads observed | Samples |
|-------------------------|---------------------:|--------:|
| `global_place_skip_io`  |                   16 |     146 |
| `global_place`          |                   16 |      16 |
| `floorplan`             |                    1 |      18 |
| `macro_place`           |                    1 |      16 |
| `tapcell`               |                    1 |      18 |
| `pdn`                   |                    1 |      16 |
| `io_placement`          |                    1 |      14 |
| `resize`                |                    1 |      12 |
| `detail_place`          |                    1 |      14 |
| `cts`                   |                    1 |      34 |
| `generate_abstract`     |                    1 |      29 |
| `synth_canonicalize`    |                    1 |      20 |
| `synth_odb`             |                    1 |      16 |

Note: `global_route`, `detail_route`, `density_fill`, and `final_report` were
too fast on this small design (379 cells) to capture. For larger designs,
`global_route` and `detail_route` are known to be heavily multi-threaded from
OpenROAD source code (FastRoute and TritonRoute both use internal threading).
CTS, resize, and detail_place also scale to multiple threads on larger designs.

## Memory

The `resource_set` also declares memory (8192 MB). Large designs can consume
significant memory, especially during global routing (`grt`) and detailed
routing. Bazel uses this for scheduling decisions, not as a hard limit.

## Why not break stages into substage actions?

A finer-grained approach would split each stage into individual Bazel actions
per substage (e.g., 5 actions for `place` instead of 1). This would allow
precise CPU allocation: 1 CPU for `io_placement`, all CPUs for
`global_placement`. This has two show-stoppers:

### Artifact explosion

Each substage produces an intermediate ODB file. ODB files are hundreds of MB
for real designs. Breaking `place` into 5 substage actions means 5 intermediate
ODB files in `bazel-out` instead of 1. Across all stages this would add ~20
extra ODB files per design, consuming significant disk space and remote cache.

### White-box coupling with ORFS

The ORFS Makefile provides stable `do-floorplan`, `do-place`, `do-cts`,
`do-route`, `do-final` targets. The Makefile comments explicitly state:

> *"The do- substeps of each of these stages are subject to change."*

Full substage decomposition requires hard-coding every `do-2_1_floorplan`,
`do-3_1_place_gp_skip_io`, etc. and their exact input/output ODB filenames.
Any ORFS update could break this coupling silently.

### The waste is small

For `place` (the stage with the most mixed threading), the multi-threaded
substages (`global_place_skip_io`, `global_place`) dominate runtime (~80% of
samples). Holding all CPUs during the ~20% single-threaded portion
(`io_placement`, `resize`, `detail_place`) is a minor inefficiency compared to
the 370x improvement from preventing oversubscription.

### Path to finer granularity

If the stage-level approach proves too coarse for real workloads, the right fix
is upstream in ORFS following the `variables.yaml` pattern:

- ORFS already exports `variables.yaml` with stage-to-variable mappings.
  `bazel-orfs` consumes this via `load_json_file` without white-boxing.
- ORFS could similarly export a `stages.yaml` describing substages, their
  threading profile (single/multi), and their input/output artifacts.
- `bazel-orfs` would consume this metadata to set `resource_set` per-substage
  or dynamically construct substage actions.
- This keeps the contract between ORFS and `bazel-orfs` explicit and versioned.

## Tuning for your environment

### Overriding CPU count

The detected CPU count can be verified by inspecting
`@host_cpus//:cpus.bzl` in your Bazel output base. If this value is wrong
(e.g., inside a container with limited cores), the `detect_cpus` repository
rule will re-run on the next `bazel sync` or clean build.

### Controlling parallelism

Bazel's `--local_cpu_resources` flag controls the total CPU budget. With
`NUM_CPUS=16` and `--local_cpu_resources=16` (default), Bazel will run at most
one multi-threaded OpenROAD stage at a time, while allowing up to 16
single-threaded stages in parallel.

To allow two multi-threaded stages to overlap (e.g., on a 32-core machine
detected as 16 cores due to containers):

```
bazel build --local_cpu_resources=32 //...
```

### Monitoring

To see which actions are running and their resource usage:

```
bazel build --show_progress //...
```

To verify resource_set values, add `--subcommands` to see the full action
command lines, or inspect the action graph with `bazel aquery`.
