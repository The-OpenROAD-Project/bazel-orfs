# Per-Command OpenROAD Binaries

## Problem: Framework Inversion

OpenROAD TCL commands are framework-inverted. A monolithic binary boots a
custom TCL framework, loads all ~37 modules, each registers its commands
via SWIG. You cannot invoke `detailed_placement` without loading the
detailed router, clock tree synthesis, parasitic extraction, and 30+ other
modules you don't need.

This has three costs:

1. **Slow rebuilds**: editing one line in `dpl` relinks all 37 modules
   (~30-60s link time). The `cc_library` targets already exist in Bazel,
   but there is only one `cc_binary`.

2. **Indirect debugging**: you cannot `gdb --args` a single command. You
   must write a TCL script, invoke `openroad -exit script.tcl`, and debug
   through the TCL interpreter.

3. **Heavy bug reports**: reproducing a crash requires environment
   variables, TCL scripts, data files, and setup instructions. There is no
   `openroad detailed_placement --read_db crash.odb` you can paste into a
   debugger or a GitHub issue.

## Vision

Each OpenROAD command becomes a standalone binary, like git subcommands:

```bash
# Build only what you need (seconds, not minutes)
bazelisk build //test/orfs/openroad:detailed_placement

# Debug directly — no TCL, no framework
gdb --args bazel-bin/test/orfs/openroad/detailed_placement \
  --read_db crash.odb -max_displacement 10

# Bug report: files + one command, no env vars
bazelisk run //test/orfs/openroad:detailed_placement -- --read_db crash.odb
```

## TCL-to-CLI Impedance Match

TCL's `-flag value` syntax is already CLI syntax. Take it verbatim:

```
# TCL (today)
detailed_placement -max_displacement 10 -report_file_name rpt.txt

# CLI (proposed) — IDENTICAL command flags, just add I/O
openroad detailed_placement \
  --read_db in.odb -max_displacement 10 -report_file_name rpt.txt --write_db out.odb
```

The only additions are `--read_db` / `--write_db` (double-dash to
distinguish from TCL's single-dash flags). No flag renaming, no
translation layer, no new documentation to maintain. The principle of
least astonishment: if you know the TCL syntax, you know the CLI.

## Which Commands Can Be Broken Out Today

Dependency analysis of the Bazel BUILD files shows which modules are
leaf nodes with minimal cross-dependencies:

| Command | Module | Deps beyond odb+utl | Difficulty |
|---------|--------|---------------------|------------|
| `detailed_placement` | dpl | none (boost only) | **Trivial** |
| `filler_placement` | dpl | none | **Trivial** |
| `check_placement` | dpl | none | **Trivial** |
| `tapcell` | tap | none | **Trivial** |
| `extract_parasitics` | rcx | none | **Trivial** |
| `check_antennas` | ant | none | **Trivial** |
| `detailed_route` | drt | dst, stt | Easy |
| `global_route` | grt | ant, dpl, stt | Easy |
| `clock_tree_synthesis` | cts | est, rsz, stt | Medium |
| `global_placement` | gpl | grt, rsz | Medium |
| `repair_timing` | rsz | dpl, est, grt, stt | Hard |

The "trivial" commands need only `odb` + `utl` — the same deps every
OpenROAD module already has. Their C++ APIs (`Opendp`, `Tapcell`,
`OpenRCX`, `AntennaChecker`) take `(dbDatabase*, Logger*)` and nothing
else.

## Three Layers

All shipped together, each serving a different need:

### 1. `cc_binary` — the point

Standalone C++ binary per command. No TCL interpreter, no SWIG, no
framework. Links only the needed module(s). For `detailed_placement`:

```python
cc_binary(
    name = "detailed_placement",
    srcs = ["detailed_placement_main.cc"],
    deps = ["//src/dpl", "//src/odb", "//src/utl"],  # 3 libs, not 37
)
```

This is what you `gdb --args`. This is what rebuilds in seconds.

### 2. `py_binary` — the CLI definition

Defines the user interface for ALL commands. Routes to the native
`cc_binary` when one exists, falls back to the monolithic `openroad`
binary + generated TCL for commands not yet broken out.

```bash
# detailed_placement → native cc_binary (fast, debuggable)
bazelisk run //test/orfs/openroad:openroad_cmd -- \
  detailed_placement --read_db in.odb --write_db out.odb -max_displacement 10

# global_route → monolithic fallback (no cc_binary yet)
bazelisk run //test/orfs/openroad:openroad_cmd -- \
  global_route --read_db in.odb --write_db out.odb -congestion_iterations 50
```

The CLI is defined once. As more commands get native binaries, the
wrapper routes to them automatically. The user interface never changes.

### 3. Bash wrapper — ORFS integration

Thin shell script that ORFS Makefile can call directly:

```makefile
# Before: framework-inverted TCL, 8+ env vars
$(OPENROAD_CMD) $(SCRIPTS_DIR)/detail_place.tcl

# After: direct CLI, explicit args, no env vars
openroad-detailed-placement \
  --read_db $(RESULTS_DIR)/3_4_place_resized.odb \
  --write_db $(RESULTS_DIR)/3_5_place_dp.odb
```

One stage at a time. Each is a separate, small, non-breaking PR.

## Precedents

| Pattern | Examples | Lesson |
|---------|----------|--------|
| Git subcommands | git-foo in libexec → multicall | Naming convention IS the plugin API |
| LLVM tools | opt, llc, clang, lld share libs | Modular libraries enable composable tools |
| Terraform providers | Monolithic → gRPC plugin binaries | Release cycle independence was the driver |
| Docker CLI plugins | docker-compose/buildx as plugins | Extensions without forking core |
| Cargo plugins | cargo-foo in PATH | Zero-coordination extensibility |
| OpenLane2 Steps | State_out = Step(State_in, Config) | Atomic, deterministic, stateless invocations |
| Yosys + nextpnr | Separate binaries, JSON intermediate | Unix pipeline applied to EDA |
| Magic ScriptEDA | Tool becomes interpreter extension | Inverts the framework inversion |

Most projects moved *toward* consolidation for distribution and
performance (Git, LLVM multicall, BusyBox) but *toward* decomposition for
development velocity (Terraform, Docker). OpenROAD's case is development
velocity and reproducibility.

No existing EDA project has fully decomposed a monolithic tool into
per-command binaries. The closest approaches are OpenLane2's step
framework, the Yosys+nextpnr pipeline, and Magic's ScriptEDA model where
the tool becomes an interpreter extension rather than embedding one.

## Impact

- **Who benefits**: any developer iterating on OpenROAD C++ code
- **Rebuild time**: seconds instead of minutes (link 3 libs, not 37)
- **Debug workflow**: `gdb --args binary --read_db crash.odb` — direct
- **Bug reports**: files + one command, no env vars, paste into debugger
- **Dependency hygiene**: makes module coupling explicit and visible

## Effort

The prototype (`detailed_placement`) is achievable in a day:
- `detailed_placement_main.cc` is ~100 lines of C++ (no TCL, no framework)
- `dpl::Opendp` takes `(dbDatabase*, Logger*)` — no other modules needed
- `odb::dbDatabase::read()`, `read_lef()`, `read_def()` handle all I/O
- The BUILD target is 5 lines

Each subsequent command follows the same pattern. Leaf modules (`tap`,
`rcx`, `ant`) are copy-paste with different includes. Harder commands
(`rsz`, `gpl`) require linking more modules but the pattern is identical.

## Cross-References

- [Per-Stage OpenROAD Binaries](per-stage-openroad-binaries.md) — coarser
  granularity (per-stage vs per-command)
- [Fast Unit Test cc_library Extraction](fast-unit-test-cc-library-extraction.md) —
  prerequisite for maximum rebuild speed within modules
- GitHub PR #9842 — hzeller's analysis of coarse-grained libraries
- GitHub #9563 — core library extraction for independent test linking
