# Estimation Ladder Scaling Plan

The baseline Optuna campaign for extracting early Pareto-front estimates from the OpenROAD flow has been successfully demonstrated on a small testcase (`multiplier` / `asap7`). The ground-truth is now decoupled from the Python script, allowing exact path matching without compounding placement errors.

The next step is to scale this infrastructure to support large designs containing macros and cross-chip signals, such as the `megaboom` testcase.

## Phase 1: Parameterize the Python Harness
1. **Refactor `optuna_study.py` to use `argparse`**:
   Remove all hardcoded paths (e.g., `multiplier_asap7_grt_deps_tar.tar.gz`, `1_synth.odb`, `asap7` directories). Instead, it will accept these inputs purely via command-line arguments:
   * `--deps-tar`: Path to the OpenROAD environment dependencies.
   * `--synth-odb` and `--synth-sdc`: The starting database.
   * `--ground-truth-json`: The target endpoint timings.
   * `--design-name` and `--platform`: To construct the correct Make commands internally.
   * `--runfiles-dir`: To safely resolve the scratch directory relative to the Bazel execution root.

## Phase 2: Create a Reusable Bazel Macro (`estimation.bzl`)
1. **Create `test/estimation_ladder/estimation.bzl`**:
   Write a generalized Bazel macro named `orfs_estimation_campaign`. This macro will take a base `orfs_flow` target (like `//sram:top_megaboom`) and automatically generate:
   * The `extract_ground_truth` target using that flow's `_grt` output.
   * The fast estimator target that starts from that flow's `_synth` output.
   * The Python `py_binary` target that orchestrates the study, with all the `args` strictly mapped to the flow's artifacts.

## Phase 3: Instantiate Megaboom & Multiplier
1. **Refactor `test/estimation_ladder/BUILD.bazel`**:
   Remove the hardcoded multiplier targets. We will import `orfs_estimation_campaign` and call it twice:
   ```python
   orfs_estimation_campaign(
       name = "multiplier",
       flow_target = ":multiplier_asap7",
       design_name = "multiplier",
       platform = "asap7",
       # ...
   )

   orfs_estimation_campaign(
       name = "megaboom",
       flow_target = "//sram:top_megaboom",
       design_name = "top",
       platform = "asap7", # or sky130, whichever it is configured for
       # ...
   )
   ```
2. This means you will immediately be able to run `bazel run //test/estimation_ladder:megaboom_optuna_study` (or test on the mock megaboom to ensure the plumbing works) and all the wiring will be mathematically correct.
