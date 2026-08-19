# RFC: Explicit Dependency & Sources Model for `orfs_run()`

## Context & Problem Statement
In Bazel's execution model, dependencies are strictly additive. It is straightforward to add dependencies and variables to an action, but nearly impossible to safely subtract or filter them out once inherited transitively.

Previously, `orfs_run()` attempted to provide a "convenient story" where pointing `src` to an upstream stage target (e.g. `_synth`) would cause `orfs_run` to automatically inherit all variables and configuration from the full `orfs_flow()`. An execution-time JSON filtering mechanism (`merge_arguments.py` with `ALL_STAGE_TO_VARIABLES`) attempted to prune irrelevant stage variables.

### Failure Mode: Circular Dependencies & Brittle DAGs
In realistic physical design flows, downstream stage inputs frequently feed back or depend on earlier stage artifacts:
- A custom floorplan generator or macro placer may depend on synthesis netlists/metrics.
- If `orfs_run()` automatically pulls in the full flow's variables, configs, and inputs for `synth`, any floorplan tool participating in that flow creates an unresolvable cycle in Bazel's dependency graph:
  `synth -> floorplan script -> orfs_run -> flow variables / floorplan deps`

## Proposed Strategy: Explicit `orfs_run()` with `sources`

1. **Explicit over Implicit**:
   - `orfs_run()` will no longer attempt to magically gather or filter full-flow variables from `src`.
   - `src` provides the primary input artifact, `PdkInfo`, and `TopInfo`.

2. **Add `sources` Attribute to `orfs_run()`**:
   - `orfs_run()` grows the `sources` dictionary attribute (matching `orfs_flow()`).
   - Maps variable names directly to input files/labels, expanding them into action inputs and config paths cleanly.

3. **DRY / Single Source of Truth (SSOT) at the Starlark Level**:
   - Instead of rule internals guessing dependencies, users define shared configuration dictionaries and sources in `BUILD.bazel` / `.bzl` files.
   - Multi-stage estimation ladders can be cleanly expressed as list comprehensions over `orfs_run()` targets without cyclic dependency risks.

4. **Example Usage**:
   See `test/estimation_ladder/BUILD.bazel` and `test/estimation_ladder/multiplier.sv`.
