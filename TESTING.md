# Testing

All tests run via `bazelisk test ...`. No nested Bazel invocations, no
external scripts.

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
| `//test/smoketest:lb_32x128_asap7_build_test` | Full flow, all stages, all PDK-specific config | — | — | asap7 | yes |
| `//test/smoketest:lb_32x128_nangate45_build_test` | Full flow, all stages, all PDK-specific config | — | — | nangate45 | yes |
| `//test/smoketest:lb_32x128_sky130hd_build_test` | Full flow, all stages, all PDK-specific config | — | — | sky130hd | yes |
| `//test/smoketest:lb_32x128_ihp-sg13g2_build_test` | Full flow, all stages, all PDK-specific config | — | — | ihp-sg13g2 | yes |
| `//test/bump:bump_test` | `bump.sh` MODULE.bazel version update logic | — | — | — | — |
| `//chisel:life_test` | Chisel → FIRRTL → Verilog generation | — | — | — | — |
| `//chisel:life_cc_test` | Verilator simulation of Chisel design | — | — | — | — |
| `//chisel:life2_test` | Verilator simulation (larger design) | — | — | — | — |
| `//chisel:helloworld_synth_test` | Chisel → synthesis with real OpenROAD | — | — | asap7 | yes |
| `//chisel:helloworld_dir_synth_test` | Chisel → synthesis (directory output) | — | — | asap7 | yes |
| `//delivery:cpu_generated_test` | Verilator simulation of generated Verilog | — | — | — | — |
| `//delivery:cpu_rewrite_test` | Verilator simulation of rewritten SystemVerilog | — | — | — | — |
| `//delivery:cpu_eqy_lec_test` | Equivalence checking (eqy) | — | — | — | — |
| `//delivery:cpu_kepler_lec_test` | Equivalence checking (kepler-formal, mocked in CI) | — | — | — | — |
| `//sby:counter_test` | Formal verification (SymbiYosys BMC) | — | — | — | — |
| `//:requirements.test` | pip requirements lock consistency | — | — | — | — |
| `//:requirements_examples.test` | pip requirements lock consistency | — | — | — | — |
| `//:requirements_features.test` | pip requirements lock consistency | — | — | — | — |

### Manual tests (not run by `bazelisk test ...`)

| Target | What it tests |
|--------|--------------|
| `//test/chisel:downstream_chisel_test` | Downstream project Chisel integration (needs full source tree) |
| `//chisel:life2_test_inner` | Inner test target (run by life2_test) |

## What must be tested locally

These cannot be tested via `bazelisk test ...`:

- **`_deps` workflow**: `bazel run //test:lb_32x128_mock_openroad_floorplan_deps` then
  `tmp/.../make do-floorplan`. Tests the local escape-hatch build workflow.
- **Docker container**: Testing with preinstalled ORFS in the Docker image.
- **Lockfile consistency**: `bazel mod tidy && git diff --exit-code` (run in CI as a pre-test step).
- **Buildifier lint**: `bazelisk run @buildifier_prebuilt//:buildifier -- -lint warn -r .` (run in CI as a pre-test step).

## Sub-modules (.bazelignore)

The following directories are excluded from `//...` via `.bazelignore`.
They contain code that doesn't belong in bazel-orfs long-term — bazel-orfs
is hosting it temporarily until the respective owners provide native Bazel
support. Each directory will get its own `MODULE.bazel` for independent
development (`cd chisel && bazelisk test ...`).

| Directory | Why it's here | Who should own it |
|-----------|--------------|-------------------|
| `chisel/` | Chisel integration examples/tests. Chisel rules already moved to BCR `rules_chisel`. | rules_chisel examples repo |
| `delivery/` | Chisel→SV roundtrip LEC demo using eqy + kepler-formal + verilator | downstream project example |
| `lec/` | Bazel rules wrapping kepler-formal for logic equivalence checking | kepler-formal repo |
| `sby/` | Bazel rules wrapping SymbiYosys for formal verification | oss-cad-suite or separate rules_sby repo |
| `naja/` | Naja EDA netlist cleaning example | naja repo |

These are tested post-merge to catch breakage, but don't block PRs.

## Profiling

To identify the slowest targets:

```sh
bazelisk test ... --build_tests_only --keep_going --profile=build.profile
bazelisk analyze-profile build.profile
```
