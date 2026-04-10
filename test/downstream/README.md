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

### Patches applied here (to be upstreamed)

- **OpenROAD `isolate = True`** — `npm` `use_extension` uses experimental
  `isolate` flag; patched out (`openroad-remove-isolate.patch`).

- **OpenROAD STA `Iterator.hh`** — GCC 15 / clang 20 enforce
  `-Wtemplate-body`; added `typename` and `this->` qualifiers
  (`openroad-fix-sta-iterator-templates.patch`).

- **ORFS slang plugin path** — `synth_preamble.tcl` hardcodes
  `plugin -i slang`; patched to respect `SLANG_PLUGIN_PATH` env var
  (`orfs-slang-plugin-path.patch`).

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

### yosys visibility and headers patches

BCR yosys has `package(default_visibility = ["//visibility:private"])`.
Downstream consumers must duplicate the `yosys-visibility.patch` and add
a `yosys-hdrs.patch` for plugin compilation (`single_version_override` is
root-only).

### yosys-slang not on BCR

The slang yosys plugin must be built from source. This test includes a
native Bazel build (`yosys_slang.BUILD.bazel`) that compiles slang, fmt,
and yosys-slang into `slang.so`. A `merge_yosys_share` rule combines the
BCR yosys share tree with the plugin.
