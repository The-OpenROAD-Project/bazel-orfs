# ORFS Integration (deprecated — use ORFS directly)

This directory was a staging area for testing bazel-orfs rules against
real ORFS designs. That role has moved to
[ORFS PR #4094](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/pull/4094),
which integrates bazel-orfs natively into OpenROAD-flow-scripts with 46
designs across 6 platforms passing real builds and QoR tests.

## What moved to ORFS PR #4094

- **Real design builds and tests** — 46 designs, 6 platforms, full flow
  through final with QoR regression checks.
- **Patch stack** — the 34 patches carried here are merged into the ORFS
  branch and upstreamed as focused PRs.
- **CI validation** — ORFS CI exercises the bazel-orfs rules directly.

## What remains here

- **Lint/FRC flow**: seconds-fast design validation using mock tools.
  This is the only unique capability not yet in ORFS. See the
  [FRC catalog](FRC.md) for the rules that catch common config errors
  before expensive real builds.
- **FRC development**: new FRC rules are prototyped here against the
  mock tool chain before being ported to ORFS.

## CI status

ORFS integration tests are **not run in bazel-orfs CI** — they are too
slow (git clone of OpenROAD with submodules, yosys compilation from
source, LLVM toolchain download) and duplicate coverage now provided by
ORFS PR #4094.

To run locally:

```bash
cd orfs/
bazelisk test //:asap7_lint_tests --keep_going --test_output=errors
```

## Flow Rules Check (FRC)

The lint flow validates design configuration in seconds using mock
tools. FRC rules catch common errors before expensive real builds.
See the [FRC catalog](FRC.md) for the full list.
