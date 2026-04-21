# External API

This file documents the public API surface of bazel-orfs — the `.bzl` files
and rules that downstream consumers may load and use.

**Policy:** Every `bazel_dep` in `MODULE.bazel` that is not required by a
public API file listed below must be marked `dev_dependency = True`. This
prevents MVS from forcing unnecessary version constraints on downstream
consumers.

## Public .bzl files

| File | Exports | External deps |
|---|---|---|
| `openroad.bzl` | `orfs_flow`, `orfs_synth`, `orfs_update`, `orfs_run`, `orfs_test`, `orfs_macro`, `orfs_pdk`, `orfs_deps`, `orfs_floorplan`, `orfs_place`, `orfs_cts`, `orfs_grt`, `orfs_route`, `orfs_final`, `orfs_gds`, `orfs_abstract`, `orfs_generate_metadata`, `orfs_update_rules`, providers (`OrfsInfo`, `PdkInfo`, `TopInfo`, `OrfsDepInfo`, `LoggingInfo`) | `bazel_skylib` |
| `extension.bzl` | `orfs_repositories` module extension | built-in only |
| `ppa.bzl` | `orfs_ppa` | `rules_shell` |
| `verilog.bzl` | `verilog_directory`, `verilog_file`, `verilog_single_file_library` | `rules_verilog` |
| `generate.bzl` | `fir_library` | none (`@circt` http_archive) |
| `orfs_genrule.bzl` | `orfs_genrule` | none |
| `sweep.bzl` | `sweep` | none (via openroad.bzl) |

## Required non-dev bazel_dep entries

These are loaded by the public `.bzl` files above or by BUILD files that
downstream consumers may transitively evaluate:

- `bazel_skylib` — `BuildSettingInfo` in private/attrs.bzl, private/environment.bzl
- `rules_shell` — `sh_binary` in ppa.bzl, root BUILD
- `rules_verilog` — verilog providers in verilog.bzl
- `rules_verilator` — verilator toolchain, verilator_cc_library
- `verilator` — required by rules_verilator
- `rules_python` — `py_binary` in root BUILD, pythonwrapper/BUILD

## Dev-only files (not public API)

- `chisel/test.bzl` — `chisel_bench_test` (needs `rules_cc`, `rules_chisel`, `rules_verilator`)
- BUILD files under `chisel/`, `mock/` — internal test targets

## Dev-only bazel_dep entries

These are only used by dev-only extensions, toolchains, or BUILD files:

- `rules_jvm_external` — maven extension
- `rules_java` — transitive dep of rules_scala
- `rules_scala` — scala_config/scala_deps extensions
- `rules_chisel` — chisel/test.bzl, dev BUILD files
- `rules_cc` — chisel/test.bzl, dev BUILD files

## PDK extensibility

The PDKs in `docker.BUILD.bazel` (asap7, nangate45, sky130hd, ihp-sg13g2) are
the ORFS-bundled PDKs exposed for convenience. PDK support does not have to
live in bazel-orfs — users can implement private or proprietary PDK support in
their own repository using the `orfs_pdk` rule.
