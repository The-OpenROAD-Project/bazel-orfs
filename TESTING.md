# Testing

All tests run via `bazelisk test ...`. No nested Bazel invocations, no
external scripts.

Full rebuild of `//test/...` takes ~340s. Critical path is ASAP7 global
placement. Use `bazelisk run //:monitor-test` for stage-level progress and
timing tables.

## Test targets

| Target | What it tests | Mock OpenROAD | Mock KLayout | PDK | Real OpenROAD |
|--------|--------------|:---:|:---:|-----|:---:|
| `//test:mock_openroad_test` | Mock openroad Python unit tests | — | — | — | — |
| `//test:mock_klayout_test` | Mock klayout Python unit tests | — | — | — | — |
| `//test/klayout:mock_klayout_test` | Mock klayout shell integration | — | yes | — | — |
| `//test:mock_openroad_floorplan_build_test` | `orfs_flow` through floorplan, `last_stage`, openroad override, substep targets | yes | — | asap7 | synth only |
| `//test:mock_openroad_squashed_cts_build_test` | `orfs_flow` squashed through cts, `squash=True`, `substeps=False` | yes | — | asap7 | synth only |
| `//test:lb_32x128_squashed_final_test` | `orfs_flow` squashed through final, substep targets for all stages | yes | — | asap7 | synth only |
| `//test:lb_32x128_sky130hd_macro_test` | `orfs_macro` + `orfs_gds`, full flow through GDS | — | yes | sky130hd | yes |
| `//test:mock_hierarchy_build_test` | Hierarchical design with macro: submacro abstract + parent flow | yes | — | asap7 | synth only |
| `//test:mock_sweep_build_test` | `orfs_sweep` with macros, openroad override, previous_stage | yes | — | asap7 | synth only |
| `//test:lint_build_test` | `lint=True` + `add_deps=False` builds successfully | yes | — | asap7 | synth only |
| `//test:lint_no_heavy_deps_test` | Lint flow runfiles exclude klayout, opensta, ruby, tcl, opengl, qt | yes | — | asap7 | synth only |
| `//test/smoketest:lb_32x128_asap7_build_test` | Full flow, all stages, all PDK-specific config | — | — | asap7 | yes |
| `//test/smoketest:lb_32x128_gf180_build_test` | Full flow, all stages | — | — | gf180 | yes |
| `//test/smoketest:lb_32x128_nangate45_build_test` | Full flow, all stages | — | — | nangate45 | yes |
| `//test/smoketest:lb_32x128_sky130hd_build_test` | Full flow, all stages | — | — | sky130hd | yes |
| `//test/smoketest:lb_32x128_sky130hs_build_test` | Full flow, all stages | — | — | sky130hs | yes |
| `//test/smoketest:lb_32x128_ihp-sg13g2_build_test` | Full flow, all stages | — | — | ihp-sg13g2 | yes |
| `//test/bump:bump_test` | `bump.sh` MODULE.bazel version update logic | — | — | — | — |

## User-facing binaries

Every `*_binary` target must have a functional test (not just `build_test`).
Tests mock the external environment so they run in the Bazel sandbox.

| Binary | Use-case | Test | How it's tested |
|--------|----------|------|-----------------|
| `//:deps` | Deploy stage inputs for interactive debugging | `deps.yml` CI workflow | Real end-to-end: deploy + make (4 cases) |
| `//:bump` | Upgrade ORFS/bazel-orfs/OpenROAD versions | `//test/bump:bump_test` | Mock fetch functions, fixture MODULE.bazel |
| `//:fix_lint` | Format changed Bazel/Python files | `//test:fix_lint_test` | Unit test core logic, mock git/buildifier |
| `//:klayout` | Launch KLayout viewer | `//test:klayout_wrapper_test` | Mock klayout on PATH |
| `//:openroad` | Launch OpenROAD CLI | `//test:openroad_wrapper_test` | Mock openroad on PATH |
| `//:plot_clock_period_tool` | Generate PPA plots from metrics | `//test:plot_clock_period_test` | Fixture YAML inputs, verify CSV/YAML output |
| `//:monitor-test` | Monitor build progress | `//test:monitor_test_test` | (existing) |
| `//pythonwrapper:python3` | Python wrapper for ORFS make | `//pythonwrapper:python3_test` | Run script, verify argv and yaml import |

### Contract

`--build_tests_only` in CI means only test dependencies get built.
Adding a binary without a test makes it invisible to CI. The rule:

> Every non-manual `*_binary` must be a transitive dependency of a `*_test`.

To check for gaps:

```bash
# Binaries not reachable from any test
comm -23 \
  <(bazelisk query 'kind(".*_binary", //...) except attr(tags, manual, //...)' 2>/dev/null | sort) \
  <(bazelisk query 'deps(kind(".*_test", //...), 3)' 2>/dev/null | sort)
```

### Manual tests (not run by `bazelisk test ...`)

| Target | What it tests |
|--------|--------------|
| `//test:lb_32x128_openroad_gui_*` | Source-built OpenROAD with GUI |
| `//chisel:*` | Chisel integration (separate MODULE.bazel) |
| `//sby:*` | Formal verification (separate MODULE.bazel) |

## Feature coverage

### Covered

| Feature | Test |
|---------|------|
| `abstract_stage` | tag_array (cts), lb_32x128 (place, cts) |
| `last_stage` | mock_openroad (floorplan), squashed_final (final) |
| `variant` | 10+ named variants |
| `mock_area` | lb_32x128 (0.7), sram (0.95) |
| `previous_stage` | Sweep with floorplan/place/cts entry points |
| `squash` | squashed (cts), squashed_final (final) |
| `substeps` | squashed_final with substeps=True |
| `add_deps=False` | lite variant (no `_deps` targets created) |
| `lint=True` | lint variant (heavy deps excluded from runfiles, synth skips do-yosys) |
| `openroad` override | mock-openroad variants |
| `yosys` override | (via sweep kwargs) |
| `stage_arguments` | tag_array (explicit regression test) |
| `extra_configs` | sram/BUILD (config injection) |
| `SYNTH_HIERARCHICAL` | L1MetadataArray |
| `SYNTH_HDL_FRONTEND=slang` | slang/BUILD |
| Cross-package refs | subpackage/BUILD |
| 6 PDKs | smoketest/BUILD |

### NOT covered

| Feature | Notes |
|---------|-------|
| `stage_data` | Parameter exists in `orfs_flow`, never exercised |
| `renamed_inputs` | Exists in flow.bzl/sweep.bzl, never tested |
| `settings` (BuildSettingInfo) | Parameter exists, not tested |
| `dissolve` in sweep | Feature exists (sweep.bzl), never used |
| `orfs_update` | Rule exported, no test |
| `save_odb=False` | Synthesis attribute, never tested |
| Error paths | No negative tests (invalid abstract_stage, etc.) |
| GDS in full flow | `orfs_gds` tested standalone, not via `orfs_flow` |
| Multi-clock designs | All test designs are single-clock |
| Performance regression | No automated timing check |

## Duplication in test flows

The lb_32x128 design has **7 independent placement runs** on ASAP7, each
taking ~90-100s. These dominate the critical path.

| Variant | Synth | Floorplan | Place | CTS+ | Purpose |
|---------|:-----:|:---------:|:-----:|:----:|---------|
| base | own | own | own | cts | Base flow + mock_area |
| test | own | own | own | cts | Variant naming |
| 1 (sweep) | shared | own | own | cts | Sweep: previous_stage=synth |
| 2 (sweep) | shared | shared | own | cts | Sweep: previous_stage=floorplan |
| mocked | shared | own | own | place | Mock area scaling |
| lite | shared | own | stops | — | Lite flow test |
| mock_openroad | shared | own | stops | — | Tool override |
| squashed | shared | own | squashed | cts | Squash mode |
| squashed_final | shared | own | squashed | final | Squash + substeps |
| mock_abstract | shared | own | own | cts | Mock-openroad hierarchy |

**Deduplication opportunities:**
- `test` variant only validates naming -- could share `previous_stage` with base
- Sweep variants 1/2/3 have nearly identical PLACE_DENSITY (0.65/0.66/0.67) --
  the sweep itself is the thing being tested, not the density values

## Pin placement (speeding up `gp_skip_io`)

The slowest step in each flow is `3_1_place_gp_skip_io` (90-120s) which runs
`global_placement -skip_io`. ORFS skips this entirely when all pins are
already placed (`global_place_skip_io.tcl` checks `all_pins_placed`).

### How it works

1. Run placement once to get pin locations
2. Export via `write_pin_placement` to a `.tcl` file of `place_pin` commands
3. Commit the file to the repo
4. Future flows source it via `IO_CONSTRAINTS` during floorplan
5. `all_pins_placed` returns true, `gp_skip_io` is skipped (0s instead of 90-120s)

### Generating pin placement

```sh
# One-time manual operation (~90s per design)
bazelisk build //test:lb_32x128_write_pin_placement
cp bazel-bin/test/lb_32x128_io-placement.tcl test/
```

Each design that uses pin placement needs its own `orfs_run` target:

```starlark
orfs_run(
    name = "lb_32x128_write_pin_placement",
    src = ":lb_32x128_floorplan",
    outs = ["lb_32x128_io-placement.tcl"],
    script = ":write_pin_placement.tcl",
    tags = ["manual"],
)
```

The script (`write_pin_placement.tcl`) runs `global_place_skip_io.tcl` +
`place_pins` + `write_pin_placement`, following the pattern from
`OpenROAD/test/orfs/mock-array/write_pin_placement.tcl`.

### Using pinned placement

Override `IO_CONSTRAINTS` and add the pin file to floorplan sources:

```starlark
orfs_flow(
    arguments = LB_ARGS | {
        "IO_CONSTRAINTS": "$(location :lb_32x128_io-placement.tcl)",
    },
    stage_sources = {
        "floorplan": [":lb_32x128_io-placement.tcl"],
        ...
    },
)
```

### Bumping pin placement

When the design changes (new ports, different floorplan), the committed pin
placement file becomes stale. Regenerate it:

```sh
bazelisk build //test:lb_32x128_write_pin_placement
cp bazel-bin/test/lb_32x128_io-placement.tcl test/
```

If ports were added or removed, the old pin placement will cause errors
(missing pins or extra pins). The fix is always to regenerate.

Pin placement should be bumped when:
- Verilog port list changes
- `CORE_UTILIZATION` or `CORE_AREA` changes (different die size = different pin slots)
- `CORE_ASPECT_RATIO` changes
- PDK changes (different metal layers for pin placement)

### Designs with pin placement

| Design | Pin file | Savings |
|--------|----------|---------|
| lb_32x128 | `test/lb_32x128_io-placement.tcl` | ~100s |
| tag_array_64x184 | `test/tag_array_64x184_io-placement.tcl` | ~120s |
| regfile_128x65 | `test/regfile_128x65_io-placement.tcl` | ~100s |

## What must be tested locally

These cannot be tested via `bazelisk test ...`:

- **`_deps` workflow**: `bazel run //test:lb_32x128_mock_openroad_floorplan_deps` then
  `tmp/.../make do-floorplan`. Tests the local escape-hatch build workflow.
- **ORFS image**: Testing with preinstalled ORFS from the OCI image.
- **Lockfile consistency**: `bazel mod tidy && git diff --exit-code` (run in CI as a pre-test step).
- **Buildifier lint**: `bazelisk run @buildifier_prebuilt//:buildifier -- -lint warn -r .` (run in CI as a pre-test step).

## Sub-modules (.bazelignore)

The following directories are excluded from `//...` via `.bazelignore`.
They contain code that doesn't belong in bazel-orfs long-term -- bazel-orfs
is hosting it temporarily until the respective owners provide native Bazel
support. Each has its own `MODULE.bazel` for independent development
(`cd chisel && bazelisk test ... --override_module=bazel-orfs=$(pwd)/..`).

| Directory | Why it's here | Who should own it |
|-----------|--------------|-------------------|
| `chisel/` | Chisel integration examples/tests. Chisel rules already moved to BCR `rules_chisel`. | rules_chisel examples repo |
| `lec/` | Bazel rules wrapping kepler-formal for logic equivalence checking | kepler-formal repo |
| `sby/` | Bazel rules wrapping SymbiYosys for formal verification | oss-cad-suite or separate rules_sby repo |
| `naja/` | Naja EDA netlist cleaning example | naja repo |

These are tested post-merge to catch breakage, but don't block PRs.

## Profiling

```sh
# Stage-level monitoring with timing table
bazelisk run //:monitor-test

# Bazel-level profiling
bazelisk test ... --build_tests_only --keep_going --profile=build.profile
bazelisk analyze-profile build.profile
```
