# Substep Targets: Fast Iteration on Individual ORFS Steps

## Status: Prototype (patch attached)

## Background

bazel-orfs wraps OpenROAD-flow-scripts (ORFS) stages as Bazel rules. Each
stage (floorplan, place, cts, grt, route, final) runs multiple substeps
internally — e.g., the `place` stage runs global placement, IO placement,
resizing, and detailed placement as a single Bazel action via `do-place`.

ORFS already exposes individual substeps as make targets (`do-3_4_place_resized`,
`do-2_4_floorplan_pdn`, etc.) and the `_deps` mechanism in bazel-orfs deploys
stage artifacts to a local directory where users can manually invoke these
targets. However, `_deps` has high cognitive load:

1. **Manual dependency management**: The user must know to build preceding
   stages first (`bazel build synth`, then `floorplan`, then `place`) before
   running a substep via `_deps`.
2. **No change tracking**: `_deps` doesn't detect when BUILD.bazel parameters
   change — the user must re-run `bazelisk run ..._deps` manually.
3. **Opaque naming**: The user must know internal ORFS make target names
   (e.g., `do-3_4_place_resized`) and run them through the `tmp/.../make`
   wrapper.
4. **Error-prone workflow**: Forgetting to rebuild a preceding stage silently
   uses stale artifacts, leading to confusing results.

## Proposal: `orfs_step` substep targets

Add manual-tagged Bazel targets for individual ORFS substeps. These targets:

- **Automatically build the full dependency chain** — Bazel handles
  synth -> floorplan -> place before deploying and running the substep
- **Use ORFS naming directly** — `3_4_place_resized` maps 1:1 to
  `do-3_4_place_resized` in the ORFS Makefile, reducing cognitive load
- **Support GUI inspection** — `bazel run //test:foo_place_3_4_place_resized gui_3_4_place_resized`
  opens the result in the OpenROAD GUI
- **Are tagged `manual`** — never built by `bazel build //...`, no impact
  on existing workflows
- **Derive from a single source of truth** — `STAGE_SUBSTEPS` in
  `private/stages.bzl` lists substep names once; log/json names in stage
  rules are derived from it

## What stays the same

`orfs_flow()` and `orfs_synth()` are unchanged. The existing stage rules
(`orfs_floorplan`, `orfs_place`, etc.) continue to run all substeps as a
single Bazel action — this is intentional and important.

**Why not split stages into separate Bazel actions per substep?** ORFS
substeps share a single ODB file that is modified in-place through the
pipeline. If each substep were a separate Bazel action, every substep would
need to declare its own ODB output, and Bazel would store each intermediate
checkpoint. For a design with 5 placement substeps, that means 5 copies of
the ODB instead of 1. Across all stages, this artifact explosion would
multiply storage by ~4-5x per design. For CI with multiple PDKs and
variants, this quickly becomes prohibitive.

The substep targets introduced here avoid this entirely: they are
deploy-and-run wrappers (like `orfs_deps`) that reuse the parent stage's
single set of artifacts. No new Bazel actions, no new ODB checkpoints, no
artifact explosion.

## Design

### Single source of truth: `STAGE_SUBSTEPS`

```python
STAGE_SUBSTEPS = {
    "floorplan": ["2_1_floorplan", "2_2_floorplan_macro", ...],
    "place": ["3_1_place_gp_skip_io", ..., "3_4_place_resized", "3_5_place_dp"],
    "route": ["5_2_route", "5_3_fillcell"],
    ...
}
```

Stage rules derive `log_names`/`json_names` from this instead of hardcoding:
```python
log_names = [s + ".log" for s in STAGE_SUBSTEPS["place"]]
```

### `orfs_step` rule

A deploy-and-run rule (like `orfs_deps`) that bakes in a specific make
target. No new Bazel actions or artifacts — it deploys the parent stage's
outputs and runs one substep via Make.

### Auto-generation in `orfs_flow`

`_orfs_pass()` generates substep targets for every stage with multiple
substeps:
```
lb_32x128_place_3_1_place_gp_skip_io  (manual)
lb_32x128_place_3_3_place_gp          (manual)
lb_32x128_place_3_4_place_resized     (manual)
lb_32x128_place_3_5_place_dp          (manual)
```

## How openroad-demo becomes simpler

### Before: iterating on resizing

```bash
# 1. Build all preceding stages manually
bazelisk build //coralnpu:CoreMiniAxi_synth
bazelisk build //coralnpu:CoreMiniAxi_floorplan
bazelisk build //coralnpu:CoreMiniAxi_place

# 2. Deploy place artifacts
bazelisk run //coralnpu:CoreMiniAxi_place_deps

# 3. Know and run the internal make target
tmp/coralnpu/CoreMiniAxi_place_deps/make do-3_4_place_resized

# 4. If BUILD.bazel changed, re-deploy (easy to forget!)
bazelisk run //coralnpu:CoreMiniAxi_place_deps
tmp/coralnpu/CoreMiniAxi_place_deps/make do-3_4_place_resized
```

### After: one command

```bash
# Builds entire chain, deploys, runs only resizing
bazel run //coralnpu:CoreMiniAxi_place_3_4_place_resized

# Open GUI to inspect
bazel run //coralnpu:CoreMiniAxi_place_3_4_place_resized gui_place

# After editing BUILD.bazel, same command picks up changes automatically
bazel run //coralnpu:CoreMiniAxi_place_3_4_place_resized
```

### Before: debugging PDN after floorplan

```bash
bazelisk build //gemmini:MeshWithDelays_synth
bazelisk build //gemmini:MeshWithDelays_floorplan
bazelisk run //gemmini:MeshWithDelays_floorplan_deps
tmp/gemmini/MeshWithDelays_floorplan_deps/make do-2_4_floorplan_pdn
# Oops, forgot to rebuild after changing CORE_UTILIZATION in BUILD.bazel
# Stale artifacts, confusing results...
```

### After

```bash
bazel run //gemmini:MeshWithDelays_floorplan_2_4_floorplan_pdn
# Always uses current BUILD.bazel parameters, no stale state possible
```

### Before: Claude-driven debugging workflow

The openroad-demo `demo-debug` command instructs Claude to:
1. Build each stage sequentially
2. Deploy with `_deps`
3. Run substeps manually via `tmp/.../make do-...`
4. Monitor logs with `tail`
5. Remember to re-deploy after BUILD.bazel changes

This is ~15 lines of instructions per substep iteration.

### After

Claude runs `bazel run //project:module_stage_substep` — one command that
handles everything. The full chain is built, deployed, and the substep
runs. BUILD.bazel changes are automatically picked up on next run.

## Squashed flows: `orfs_flow(squash=True)`

The default `squash=False` creates one Bazel target per stage, each with
its own ODB checkpoint. This is useful when debugging — you can inspect
any intermediate stage, re-run from a checkpoint, and iterate on individual
substeps.

`squash=True` combines all stages after synthesis into a single Bazel action.
Only the final stage's ODB is stored as an artifact. This is for mature,
stable designs like RAM macros where nobody needs to inspect intermediate
stages. The reduction in artifact count is significant: instead of 7 ODB
checkpoints (synth through final), you get 2 (synth + final).

Which ODB files to checkpoint as artifacts is flow-specific — the current
per-stage boundaries are just one common case that `orfs_flow()` encodes.
`squash=True` is the other extreme. Advanced users can use `orfs_squashed`
directly for custom groupings.

```python
# Stable RAM macro — no need to inspect intermediate stages
orfs_flow(
    name = "sram_64x128",
    abstract_stage = "cts",
    squash = True,
    ...
)
```

By default, substep targets are still generated (manual-tagged) even with
`squash=True` for debugging if something goes wrong later. Disable with
`substeps=False` to minimize target count for designs that don't need it:

```python
# Minimal target footprint for stable RAM macro
orfs_flow(
    name = "sram_64x128",
    abstract_stage = "cts",
    squash = True,
    substeps = False,
    ...
)
```

## `orfs_deps` becomes a hacking tool

`orfs_deps` will never be retired — it remains essential for local ORFS
and bazel-orfs development where users need the full Make wrapper for
low-level hacking. But with substep targets, `orfs_deps` is no longer
user-facing for normal design iteration. Ideally `orfs_flow()` will
eventually stop generating `_deps` targets by default, keeping them as
an opt-in tool for ORFS/bazel-orfs developers.

## ORFS metadata

ORFS could grow a metadata file (beyond `variables.yaml`) that lists
substep names, their scripts, and dependencies. This would make
`STAGE_SUBSTEPS` truly derived from ORFS rather than maintained as a
copy in bazel-orfs. This has been discussed but not yet implemented in ORFS.

## Patch

See `ideas/substep.patch` — apply with `git apply ideas/substep.patch`.

Tested:
- `bazel build //... --nobuild` passes (311 targets)
- `bazel query '//test:all'` shows substep targets
- `bazel run //test:lb_32x128_mock_openroad_floorplan_2_4_floorplan_pdn`
  builds deps, deploys, and runs the PDN substep successfully
- `bazel build //test:lb_32x128_squashed_cts` runs floorplan+place+cts
  as a single Bazel action, producing only `4_cts.odb` as result
- Existing tests pass
