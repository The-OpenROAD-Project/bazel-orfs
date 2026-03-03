# BCR Yosys Migration Plan for bazel-orfs

## Summary

This document describes the plan and findings for migrating bazel-orfs from
pre-built Yosys binaries (Docker image / oss-cad-suite) to building Yosys from
source via the [Bazel Central Registry (BCR)](https://registry.bazel.build/modules/yosys).

## What Works Already

**Step 1 is done.** Adding two lines to `MODULE.bazel` is all that's needed to
build Yosys from source:

```starlark
bazel_dep(name = "yosys", version = "0.57.bcr.2")
bazel_dep(name = "readline", version = "8.3")  # GCC 15 compat
```

- `bazel build @yosys//:yosys` completes successfully (~2 min, 3063 actions)
- Dependency graph resolves cleanly (no version conflicts)
- The `readline` 8.3 override is needed because GCC 15 (Ubuntu 25.x) rejects
  K&R-style `()` declarations in readline 8.2's `tcap.h`

## What Remains: The yosys-slang Challenge

The main complexity is building the **yosys-slang plugin** (`slang.so`), which
ORFS uses for SystemVerilog synthesis (`SYNTH_HDL_FRONTEND=slang`).

### Why it's complex

| Aspect | Detail |
|--------|--------|
| **yosys-slang** | 12 `.cc` files, C++20, no Bazel build, CMake only |
| **slang library** (MikePopoloski/slang) | ~120 `.cpp` files, ~123 headers, code generation scripts, CMake only, not on BCR |
| **fmt library** | Available on BCR (`fmt@11.2.0`), but yosys-slang pins a specific commit |
| **Plugin ABI** | `slang.so` must be built against `@yosys//:kernel` headers with matching defines |
| **No releases** | yosys-slang has no tagged releases; must pin a git commit |

### Recommended approach

**Build slang with `rules_foreign_cc` (CMake wrapper), build yosys-slang natively.**

1. **slang library**: Use `rules_foreign_cc`'s `cmake()` rule to build the slang
   library. This avoids hand-writing BUILD rules for 120+ source files and
   handles slang's code generation steps automatically.

2. **yosys-slang plugin**: Build natively as a Bazel `cc_shared_library` with
   only 12 source files. It deps on `@yosys//:kernel` (public `cc_library`
   from BCR yosys) and the cmake-built slang library.

3. **Runtime loading**: Set `YOSYS_DATDIR` env var in `yosys_environment()`
   (openroad.bzl) so `plugin -i slang` finds `slang.so` in the expected
   `plugins/` directory.

### Source archives needed

| Component | URL | SHA256 |
|-----------|-----|--------|
| yosys-slang | `github.com/povik/yosys-slang/archive/d82b0b1...tar.gz` | `d58752f6c97d8c6d4b42992f5dff5f3bcf4d6ad4aef6dde097a44f999f887a9b` |
| slang | `github.com/MikePopoloski/slang/archive/d7888c9...tar.gz` | `c257066f58b0608a8becdd1e639bcdd4e8ea599efad27a725f6176429e6f5a1d` |
| fmt | `github.com/fmtlib/fmt/archive/553ec11...tar.gz` | `c314292789d28c3c3b420e75a7b2d1706f685f7fb63289128d46aeaea2c6be71` |

### yosys-slang source files (for cc_shared_library)

```
src/abort_helpers.cc    src/initial_eval.cc
src/addressing.cc       src/naming.cc
src/async_pattern.cc    src/procedural.cc
src/blackboxes.cc       src/slang_frontend.cc
src/builder.cc          src/variables.cc
src/cases.cc
src/diag.cc
```

Headers: `src/*.h` (9 files) + generated `version.h`

## Configuration Plumbing Changes

Once the plugin builds, these files need updating to default to BCR yosys:

| File | Change |
|------|--------|
| `extension.bzl` | Default `yosys` attr: `@docker_orfs//:yosys` → `@yosys//:yosys` |
| `config.bzl` | `CONFIG_YOSYS` resolves to `@yosys//:yosys` |
| `yosys.bzl:51` | Default `_yosys`: `@docker_orfs//:yosys` → `@yosys//:yosys` |
| `openroad.bzl` | Add `YOSYS_DATDIR` to `yosys_environment()`, add slang.so to `yosys_inputs()` |

Docker yosys remains available as a fallback via `orfs.default(yosys = "@docker_orfs//:yosys")`.

## What Stays Unchanged

- **oss_cad_suite** — still needed for SBY/EQY formal verification (provides
  its own yosys with EQY plugins, plus bitwuzla, tabby, yosys-smtbmc)
- **docker.BUILD.bazel** — yosys filegroup kept as fallback option
- **sby.bzl, eqy.bzl** — use oss_cad_suite yosys, unaffected

## Version Management

The BCR yosys module has version-specific overlays (BUILD.bazel listing exact
source files). You **cannot** just swap the source URL for a newer yosys — each
version needs overlay updates. Options for using a version not yet on BCR:

| Approach | Pros | Cons |
|----------|------|------|
| Wait for BCR PR | Zero maintenance | Dependent on BCR merge timeline |
| `single_version_override` + BCR fork/local registry | Full overlay support | Must maintain fork |
| `archive_override` + patches | No registry needed | 1100+ line patch for BUILD overlay |

Current BCR: **0.57.bcr.2**. Version **0.62** is in [open PR #7719](https://github.com/bazelbuild/bazel-central-registry/pull/7719).

## ABC Binary Question

BCR yosys links ABC as a library internally — no separate `yosys-abc` binary.
The `ABC` env var is set in `yosys_environment()` and referenced in
`yosys_substitutions()`, but `make.tpl` does **not** contain a `${ABC}`
placeholder. Needs verification whether the ORFS Makefile (inside Docker image)
actually consumes this env var, or if yosys's built-in ABC is sufficient.

## Verification Plan

1. `bazel build @yosys//:yosys` — BCR yosys builds ✅ (done)
2. `bazel build @yosys_slang//:slang_plugin` — slang.so builds against kernel
3. `bazel build //:lb_32x128_synth` — synthesis smoke test
4. `bazel build //slang:...` — slang plugin integration test
5. Compare `1_2_yosys.v` output between Docker and BCR yosys
