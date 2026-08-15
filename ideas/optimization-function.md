# Plan: `orfs_tuner` - First-Class Optimization Functions in Bazel-ORFS

## 1. Background & Motivation
In EDA, hyperparameter optimization (HPO) and Design Space Exploration (DSE) are critical for mapping the Pareto frontier of PPA (Power, Performance, Area). Existing literature (such as the OpenROAD AutoTuner) relies heavily on distributed frameworks like **Ray/Tune** or **Optuna** to run thousands of black-box flow evaluations in parallel.

Currently, driving ORFS flows through Bazel for hyperparameter search is high-overhead. Bazel is an incredible build system, but it is not designed to be an inner-loop evaluation function for an ML optimizer. Re-invoking `bazel run` for every trial adds server overhead, pollutes the action cache, and couples the optimization algorithm tightly to the Bazel workspace.

## 2. Objective
Extend `bazel-orfs` with a new rule `orfs_tuner` that takes a standard `orfs_run()` stage as input and builds a **standalone, Bazel-less Python executable**. 

Following the OpenROAD Design Space Exploration (DSE) concept of "rungs" (early stopping points or custom estimation steps in the flow), each rung would probably get its own `orfs_tuner()` target.

This executable acts as a pure function $f(x) = y$:
* **Contract**: The function is only allowed to read files, with the sole exception of writing the target value to the designated output file.
* **Input ($x$)**: Flow parameters (e.g., `PLACE_DENSITY`) and custom files (e.g., `1_synth.odb`) passed via standard CLI arguments.
* **Execution**: Runs the isolated OpenROAD stage locally without touching Bazel. The user writes the `.tcl` script and therefore knows the resource requirements; resourcing is handled entirely in their tuner framework (Optuna, Ray, etc.).
* **Output ($y$)**: The target value is written to an output file. Its format is defined by the user's script (it could be a single number in a file, a `.json` file, etc.).

## 3. Architecture

### A. The Bazel Provider & Extraction
To generate the sandbox, we need a Bazel provider that extracts the inner state of an `orfs_run()` target.
* **Provider**: `OrfsStageInfo` (or similar) will expose:
  * The toolchain binaries (OpenROAD, Yosys, KLayout).
  * The input files required for the stage (ODBs, SDCs, platform config, PDK LEFs).
  * The base dictionary of environment variables used by the TCL flow (e.g., `DESIGN_NAME`, `PLATFORM`).

### B. The Generated Python Executable
The `orfs_tuner` macro will output an executable Python script (`tuner.py`) that acts as the entrypoint for Optuna/Ray.

**Argparse Interface:**
The generated script will expose CLI arguments to support distributed execution and overriding parameters:
1. **Packaging**: An option (e.g., `--list-dependencies`) to list all files required to package the whole function for transfer to a different computer (for frameworks like Ray Distributed).
2. **Variable Overrides**: `--variable KEY=VALUE`
   * *Example*: `--variable PLACE_DENSITY=0.45 --variable CORE_UTILIZATION=35`
   * *Action*: Injects or overrides `KEY=VALUE` in the environment variables passed to the OpenROAD subprocess.
3. **Input Substitutions**: `--input-<file_type> PATH`
   * *Example*: `--input-sdc /tmp/ray_worker_9/custom.sdc`
   * *Action*: Allows the optimizer to swap out the baseline Bazel inputs with mutated inputs generated mid-flight by the optimizer.
4. **Output Destination**: `--output PATH`
   * *Action*: Specifies where the user's script should write the target value (the single allowed write operation).

### C. Execution Flow (Optuna / Ray Integration)
A typical Optuna script will interact with this generated executable as follows:
1. **Build Phase**: The user runs `bazel build //my/design:tuner` once. This extracts the stage dependencies and templates the `tuner.py` script.
2. **Packaging Phase (Distributed)**: The runner queries `tuner.py --list-dependencies` to package the isolated function for transfer to remote compute nodes.
3. **Optuna Search Phase**: The Optuna Python script imports or calls `tuner.py` directly.
4. **Trial Execution**: For each trial, Optuna samples a set of hyperparameters and invokes `tuner.py --variable PLACE_DENSITY=0.5 --output result.json`. 
5. **Sandboxing**: `tuner.py` creates a temporary isolated scratch directory, sets the overridden environment, ensures read-only access to runfiles, and executes the ORFS step.
6. **Metric Parsing**: The tuner reads the target value from the generated output file, returning it to Optuna.

## 4. Next Steps & Implementation
1. **Define the Provider**: Instrument `orfs_run.bzl` to return a provider containing `runfiles`, `env_vars`, and `inputs`.
2. **Create `orfs_tuner.bzl`**: Write the rule that takes this provider and templates the `tuner.py` executable.
3. **Template the Python Runner**: Write the `tuner.py.tpl` template with `argparse`, isolated temporary directory creation, logic to list dependencies for packaging, and subprocess execution.
4. **Integration Test**: Write a small `optuna` script that targets the output of this rule to verify it can successfully drive the flow to converge on an optimal `PLACE_DENSITY`.
