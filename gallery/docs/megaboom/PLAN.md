# MegaBoom: BOOM from Chisel Source

## Context

Add Berkeley BOOM (riscv-boom) to the OpenROAD Demo Gallery, compiling from
original Chisel sources — not pre-generated Verilog. This follows the gemmini
pattern: `chisel_library` → `chisel_binary` → `fir_library` → `verilog_directory`
→ `demo_flow`. The existing megaboom repo uses Chipyard-generated Verilog and
barstools for memory compilation; we bypass all of that and compile Chisel
directly, mocking memories with `SYNTH_MOCK_LARGE_MEMORIES` and `demo_sram()`.

**Target**: BoomTile with MegaBoom (4-wide) configuration.

## Dependency Chain

BOOM is deeply integrated with rocket-chip — every file imports from it.
Unlike gemmini (where we excluded rocket-chip deps), here we compile the
full chain from source:

```
cde (pure Scala, ~1 file)
  ↓
diplomacy (Chisel, ~36 files) + sourcecode Maven dep
  ↓
hardfloat (Chisel, ~32 files)
  ↓
rocket-chip macros (scala-reflect, ~1 file)
  ↓
rocket-chip (Chisel, ~300+ files) + json4s, mainargs Maven deps
  ↓
riscv-boom v4 (Chisel, ~45 files)
  ↓
BoomGenerator.scala (our generator — elaborates BoomTile with MegaBoom params)
```

All libraries use Chisel 6.x; this repo uses Chisel 7.2.0. Each needs a
Chisel 7 compatibility patch.

## Files to Create

### `megaboom/` directory
- `BUILD.bazel` — Chisel pipeline + ORFS flow
- `external.BUILD.bazel` — `chisel_library` for BOOM (used by `@riscv_boom`)
- `rocket-chip.BUILD.bazel` — `chisel_library` for rocket-chip + macros
- `hardfloat.BUILD.bazel` — `chisel_library` for hardfloat
- `diplomacy.BUILD.bazel` — `chisel_library` for diplomacy
- `cde.BUILD.bazel` — `scala_library` for CDE (no Chisel dep)
- `src/BoomGenerator.scala` — elaborates BoomTile → FIRRTL
- `constraints.sdc` — 1200ps clock (833 MHz, matching upstream megaboom)
- `patches/boom-chisel7.patch`
- `patches/rocket-chip-chisel7.patch`
- `patches/hardfloat-chisel7.patch`
- `patches/diplomacy-chisel7.patch`
- `README.md`

### Files to modify
- `MODULE.bazel` — 5 `http_archive` entries + Maven artifacts
- `README.md` — add megaboom to Projects table

## Implementation Steps

### Step 0: Documentation
Create `docs/megaboom/PLAN.md` with this plan. Add megaboom row to
Upcoming table in `README.md` linking to it.

### Step 1: http_archive entries in MODULE.bazel

Pin each to a specific commit. Compute sha256 for each archive.

```starlark
http_archive(name = "cde", build_file = "//megaboom:cde.BUILD.bazel", ...)
http_archive(name = "diplomacy", build_file = "//megaboom:diplomacy.BUILD.bazel", ...)
http_archive(name = "hardfloat", build_file = "//megaboom:hardfloat.BUILD.bazel", ...)
http_archive(name = "rocket_chip", build_file = "//megaboom:rocket-chip.BUILD.bazel", ...)
http_archive(name = "riscv_boom", build_file = "//megaboom:external.BUILD.bazel",
             patches = ["//megaboom:patches/boom-chisel7.patch"], ...)
```

Add Maven artifacts to existing `maven.install`:
- `org.json4s:json4s-jackson_2.13:4.0.5`
- `com.lihaoyi:mainargs_2.13:0.5.0`
- `com.lihaoyi:sourcecode_2.13:0.3.1`

### Step 2: Build external.BUILD.bazel files bottom-up

**cde.BUILD.bazel** — `scala_library` (no Chisel):
```starlark
scala_library(name = "cde_lib", srcs = glob(["cde/src/chipsalliance/rocketchip/**/*.scala"]))
```

**diplomacy.BUILD.bazel** — `chisel_library`:
```starlark
chisel_library(name = "diplomacy_lib",
    srcs = glob(["diplomacy/src/**/*.scala"]),
    deps = ["@cde//:cde_lib", "@maven//:com_lihaoyi_sourcecode_2_13"])
```

**hardfloat.BUILD.bazel** — `chisel_library`:
```starlark
chisel_library(name = "hardfloat_lib", srcs = glob(["hardfloat/src/**/*.scala"]))
```

**rocket-chip.BUILD.bazel** — `chisel_library` with macros + main:
```starlark
chisel_library(name = "rocket_chip_macros",
    srcs = glob(["macros/src/main/scala/**/*.scala"]))

chisel_library(name = "rocket_chip_lib",
    srcs = glob(["src/main/scala/**/*.scala"],
        exclude = ["**/groundtest/**", "**/unittest/**", "**/formal/**"]),
    deps = [":rocket_chip_macros", "@hardfloat//:hardfloat_lib",
            "@cde//:cde_lib", "@diplomacy//:diplomacy_lib",
            "@maven//:org_json4s_json4s_jackson_2_13",
            "@maven//:com_lihaoyi_mainargs_2_13"])
```

**external.BUILD.bazel** (for BOOM):
```starlark
chisel_library(name = "boom_lib",
    srcs = glob(["src/main/scala/v4/**/*.scala"]),
    deps = ["@rocket_chip//:rocket_chip_lib"])
```

### Step 3: Chisel 7 patches (iterative, bottom-up)

Build each library in order. Each compile failure reveals Chisel 7
incompatibilities. Common migration patterns (from gemmini patch):

| Chisel 6 | Chisel 7 |
|-----------|----------|
| `.cloneType` | remove (automatic in Chisel 7) |
| `log2Up(x)` | `log2Ceil(x)` |
| `chisel3.experimental.X` | `chisel3.X` (many moved) |
| `val x = t.cloneType` | `val x = t` |
| `chisel3.util.experimental.BoringUtils` | API changes |

Build order:
```bash
bazelisk build @cde//:cde_lib           # likely no patch needed
bazelisk build @diplomacy//:diplomacy_lib
bazelisk build @hardfloat//:hardfloat_lib
bazelisk build @rocket_chip//:rocket_chip_lib   # largest patch
bazelisk build @riscv_boom//:boom_lib
```

Fix errors, regenerate patch, repeat until each compiles.

### Step 4: BoomGenerator.scala

Write a generator that elaborates BoomTile with hardcoded MegaBoom
parameters (4-wide fetch/decode, 128 ROB entries, etc.). BoomTile is a
Diplomacy LazyModule, so the generator needs a minimal wrapper that
instantiates BoomTile and terminates its TileLink nodes.

```scala
package megaboom.generator

import chisel3._
import circt.stage.ChiselStage
import org.chipsalliance.cde.config._
import boom.v4.common._
// ... rocket-chip imports for Diplomacy wrapper

class MegaBoomConfig extends Config(/* hardcoded MegaBoom params */)

class BoomTileWrapper(implicit p: Parameters) extends LazyModule {
  val tile = LazyModule(new BoomTile(...))
  // Terminate TileLink master/slave nodes
  // Tie off interrupts
  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) { ... }
}

object BoomGenerator extends App {
  implicit val p = new MegaBoomConfig
  ChiselStage.emitHWDialect(
    LazyModule(new BoomTileWrapper).module, Array(), args)
}
```

**Fallback**: If BoomTile Diplomacy elaboration proves too complex, start
with BoomCore (a plain Module, no Diplomacy required).

### Step 5: megaboom/BUILD.bazel

```starlark
chisel_binary(name = "generator",
    srcs = ["src/BoomGenerator.scala"],
    main_class = "megaboom.generator.BoomGenerator",
    deps = ["@riscv_boom//:boom_lib"])

fir_library(name = "boom_fir", generator = ":generator")

verilog_directory(name = "boom_sv_split", srcs = [":boom_fir"],
    opts = ["--disable-all-randomization",
            "--lowering-options=disallowPackedArrays,disallowLocalVariables,noAlwaysComb"])

verilog_single_file_library(name = "boom_concat_sv", srcs = [":boom_sv_split"])

genrule(name = "boom_sv", srcs = [":boom_concat_sv"],
    outs = ["BoomTile.sv"], cmd = "cp $< $@")

demo_flow(name = "BoomTile", verilog_files = [":boom_sv"],
    arguments = {
        "SYNTH_HIERARCHICAL": "1",
        "SYNTH_MINIMUM_KEEP_SIZE": "0",
        "CORE_UTILIZATION": "40",
        "PLACE_DENSITY": "0.65",
        "GPL_ROUTABILITY_DRIVEN": "0",
        "GPL_TIMING_DRIVEN": "0",
        "SKIP_CTS_REPAIR_TIMING": "1",
        "SKIP_INCREMENTAL_REPAIR": "1",
        "SKIP_LAST_GASP": "1",
        "FILL_CELLS": "",
        "TAPCELL_TCL": "",
    },
    sources = {"SDC_FILE": [":constraints.sdc"]})

demo_gallery_image(name = "BoomTile_gallery", src = ":BoomTile_place")
```

### Step 6: constraints.sdc

```tcl
# 1200ps = 833 MHz target (matching upstream megaboom)
set clk_name clock
set clk_port_name clock
set clk_period 1200

source $::env(PLATFORM_DIR)/constraints.sdc
```

### Step 7: Build incrementally with /demo-debug

```bash
bazelisk build //megaboom:BoomTile_synth    # synthesis first
# Analyze module sizes after synth
bazelisk run //scripts:module_sizes -- \
  $(pwd)/bazel-bin/megaboom/reports/asap7/BoomTile/base/synth_stat.txt
bazelisk build //megaboom:BoomTile_place    # placement
bazelisk build //megaboom:BoomTile_gallery  # screenshot
```

### Step 8: Hierarchical refinement (after synth works)

Based on module size analysis, extract large modules as `demo_sram()` targets.
Convert from `demo_flow` to `demo_hierarchical` + `demo_sram` macros.
Expected candidates (from existing megaboom): tag arrays, data arrays,
register files, BTB/BHT tables.

### Step 9: README and gallery

- Create `megaboom/README.md` with description, build commands, results
- Update top-level `README.md`: add to Projects table, remove from Upcoming
- Generate gallery screenshot

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Chisel 7 patches for rocket-chip (~300 files) | Very large patch, days of work | Exclude unnecessary packages (groundtest, unittest, formal, amba if unused). Use Chisel 7 compat shims if available. |
| BoomTile Diplomacy elaboration without full SoC | Generator may fail | Fallback to BoomCore. Or create minimal Diplomacy harness that terminates TileLink nodes. |
| rocket-chip non-Chisel deps (json4s, mainargs) | Build failures | Add to Maven artifacts — pure Scala, no native deps. |
| Build time (400+ Scala files) | Slow first build | Bazel caches aggressively. Subsequent builds fast. |
| Scala 2.13.14 vs 2.13.17 | Minor compat issues | Binary compatible within 2.13.x. Should work. |

## Verification

1. `bazelisk build //megaboom:boom_sv` — Chisel → Verilog succeeds
2. `bazelisk build //megaboom:BoomTile_synth` — synthesis completes
3. `bazelisk build //megaboom:BoomTile_place` — placement completes
4. `bazelisk build //megaboom:BoomTile_gallery` — screenshot generated
5. Cell count and area are reasonable (expect ~200K-400K cells for MegaBoom)
