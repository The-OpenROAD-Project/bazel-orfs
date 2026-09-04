# Local flow and substeps

Everything here runs an ORFS stage *outside* the Bazel sandbox, in a
deployed directory under `tmp/`, so you can edit Tcl, re-run one substep,
or point the flow at a locally built ORFS. Start from a working
`bazelisk build` of the stage you want to poke at.

Command lines use `//test:...` targets from a clone of this repository;
substitute your own design's targets.

## Use the local flow

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

> **NOTE:** If `FLOW_HOME` is not set and `env.sh` is not sourced, `make do-<stage>` uses the ORFS from [MODULE.bazel](../MODULE.bazel) by default.

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

## Parallel local builds

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

## Substep targets

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

### Available substeps per stage

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

### Caching substep intermediates (`substeps = True`)

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

### Common `//:deps` workflows

| I want to... | Command |
|---|---|
| Run a single substep | `bazel run //:deps -- <target>_<stage> do-<substep>` |
| View result in GUI | `bazel run //:deps -- <target>_<stage> gui_<stage>` |
| Run arbitrary make targets | `bazel run //:deps -- <target>_<stage> <make args...>` |
| Edit Tcl scripts and re-run without Bazel | `tmp/<pkg>/<target>_<stage>_deps/make do-<substep>` |
| Create a `make issue` archive | `bazel run //:deps -- <target>_<stage>` then `tmp/.../make <stage>_issue` |
| Use a local ORFS installation | `bazel run //:deps -- <target>_<stage>` with `FLOW_HOME` set |
| Run `make bash` for interactive debugging | `tmp/<pkg>/<target>_<stage>_deps/make bash` |

## Use remote caching for instant reverts

If remote caching is enabled for Bazel, reverting a change and rebuilding completes instantaneously because the artifact already exists:

```bash
# Revert the change
git restore test/BUILD

# Rebuild — instant cache hit
bazel run //test:tag_array_64x184_floorplan gui_floorplan
```
