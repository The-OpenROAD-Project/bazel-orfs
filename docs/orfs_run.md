# `orfs_run()` and `orfs_test()`

## Context & Execution Model
In Bazel's execution model, dependencies are strictly additive. It is straightforward to add dependencies and variables to an action, but nearly impossible to safely subtract or filter them out once inherited transitively.

Because realistic physical design flows often involve feedback loops—such as a custom floorplan generator or macro placer depending on synthesis netlists or metrics—`orfs_run()` and `orfs_test()` are designed to avoid implicit accumulation of all flow variables. Automatically inheriting the full flow's variables, configurations, and inputs from a previous stage could easily create unresolvable cycles in Bazel's dependency graph.

## Explicit Dependency & Sources Model

1. **Explicit over Implicit**:
   - `orfs_run()` and `orfs_test()` do not magically gather or filter full-flow variables from their `src` attribute.
   - The `src` attribute provides only the primary input artifact, `PdkInfo`, and `TopInfo`.

2. **The `sources` Attribute**:
   - Both macros accept a `sources` dictionary attribute (matching `orfs_flow()`).
   - This maps variable names directly to input files or labels, expanding them into action inputs and config paths cleanly.

3. **Sibling Macros**:
   - `orfs_run()` creates a build-time action (e.g., generating an output file).
   - `orfs_test()` creates an executable test target (e.g., verifying a condition).
   - Both share the same underlying mechanics for dependency injection via the `sources` attribute.

4. **Single Source of Truth (SSOT) at the Starlark Level**:
   - Users define shared configuration dictionaries and sources in their `BUILD.bazel` or `.bzl` files, rather than relying on rule internals to guess dependencies.
   - This approach allows multi-stage ladders (such as generic estimators) to be cleanly expressed via list comprehensions over `orfs_run()` targets without risking cyclic dependencies.

## Reading the flow's stage logs

`$LOG_DIR` names the log directory of the flow the `src` stage belongs to
— where the stage logs accumulate — whatever package and variant the
`orfs_run` itself has. The logs are staged into the action's inputs only
with `src_logs = True`:

```python
orfs_run(
    name = "extract_ground_truth",
    src = ":design_grt",
    outs = ["ground_truth.json"],
    arguments = {"OUTPUT_JSON": "$(location ground_truth.json)"},
    script = "extract.tcl",
    src_logs = True,
)
```

It is opt-in because every log carries Elapsed / CPU / Peak-memory lines
and so is never byte-identical between two runs: as an input it re-runs
the action whenever any upstream stage re-executes, byte-identical
artifacts or not, and misses the remote cache across machines. Take it
for what only the logs carry (stage wall-clock), not for anything an
artifact already states.

## Output directories

`outs` names individual output files known in advance. When the *set* of
output files is only known at runtime — a tree-walking study writing one
JSON per leaf, a report generator emitting one file per violation class —
declare a directory instead:

```python
orfs_run(
    name = "study",
    src = ":design_synth",
    out_dir = "study_results",
    script = ":study.tcl",
)
```

The rule declares `study_results` as a tree artifact and exports its path
to the script as `$RUN_OUTPUT_DIR`; the script decides what files land
there. `outs` and `out_dir` compose (at least one is required). The name is
deliberately not `RESULTS_DIR` — the ORFS Makefile owns that variable for
staged flow outputs.

For `orfs_run_executable` the same contract is by convention: the caller
passes an absolute scratch path per invocation (like `LOG_DIR`), e.g.
`RESULTS_OUT=/abs/scratch/trial42`, and concurrent invocations must not
share it.

## fork/join tree walks

Run scripts can walk a decision tree in one OpenROAD process, paying every
shared stage exactly once, with the `fork` idiom — see `docs/fork.md`.
Every `orfs_run`/`orfs_run_executable` script gets `$ORFS_FORK_TCL` and
`$ORFS_FORK_LIB` automatically; pair `fork` with `out_dir` so each leaf
writes an independent result file.

## Example Usage
See `test/estimation_ladder/BUILD.bazel` for a demonstration of composing multi-stage targets using explicit `sources`.
