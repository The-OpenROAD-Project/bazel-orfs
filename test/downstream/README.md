# The long road to ditch docker

This directory is a downstream consumer of `bazel-orfs` that builds and
tests a SystemVerilog counter entirely from source — no docker, no
oss-cad-suite. It patches OpenROAD and ORFS where needed.

## Strategy

1. **Patch openroad/orfs here** to demonstrate everything works end-to-end.
2. **Fix bazel-orfs issues** in bazel-orfs itself (separate commits).
3. **Create minimum-churn PRs for OpenROAD** once patches are proven here.
4. **OpenROAD adopts latest bazel-orfs**, getting rid of docker.

## How to use

```bash
cd test/downstream
bazelisk build ...    # synthesis via orfs_flow (slang frontend)
bazelisk test ...     # verilator simulation via cc_test + gtest
```

## Fixes in this PR

### bazel-orfs fixes (can merge independently)

- **mock-klayout leaks to downstream** — made `dev_dependency`, klayout
  now truly optional (`extension.bzl`, `config.bzl`, `environment.bzl`).

### Workarounds in `.bazelrc`

- **C++20** — OpenROAD STA uses `std::bit_cast`, `std::format`,
  `.contains()`. Until bazel-orfs sets this via transition rules,
  `--cxxopt=-std=c++20` is needed.

## Remaining issues

### Non-BCR deps require root-module overrides

`orfs`, `openroad`, and `qt-bazel` are not on BCR. Downstream consumers
must provide `git_override` entries (root-module-only). Ideally bazel-orfs
would deliver these through its extension.

### Python 3.13 toolchain must be registered by root module

bazel-orfs pip deps are locked to Python 3.13. The root module must
register it as the default toolchain via `python.toolchain(is_default = True)`.

### Hermetic C++ toolchain must be registered by root module

Building OpenROAD (and yosys) from source needs the zero-sysroot BCR `llvm`
toolchain: `bazel_dep(name = "llvm", …)` + `register_toolchains("@llvm//toolchain:all")`,
plus the small set of hermetic-llvm compatibility `single_version_override`s
(sed, bison, boost.icl, gawk, m4, tcl_lang) mirrored from bazel-orfs's root
MODULE.bazel. Without the toolchain the build falls back to the host compiler
and breaks on newer glibc (e.g. `@scip`/`tinycthread` on glibc 2.41). These
overrides are root-module-only, so every downstream repeats them.

### slang yosys plugin from BCR (sv-elab)

The slang yosys plugin comes from the `sv-elab` module on the Bazel
Central Registry (the project formerly known as `yosys-slang`), via
`@sv-elab//src/yosys_plugin:slang.so`. A `merge_yosys_share` rule combines
the BCR yosys share tree with the plugin.
