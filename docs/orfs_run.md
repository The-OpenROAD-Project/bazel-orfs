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

## Example Usage
See `test/estimation_ladder/BUILD.bazel` for a demonstration of composing multi-stage targets using explicit `sources`.
