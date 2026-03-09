# LLM Cribs — Chisel → SystemVerilog Roundtripping Flow

Quick-reference for Claude (or any LLM) implementing or extending this flow.
Saves you from searching through external rules to find the right incantations.

## Key API surfaces you need to know

### Chisel → Verilog pipeline (in bazel-orfs)

```
chisel_library()     # //toolchains/scala:chisel.bzl — scala_library + chisel deps
chisel_binary()      # //toolchains/scala:chisel.bzl — scala_binary + chisel deps
fir_library()        # //:generate.bzl — runs generator binary → .fir file
verilog_directory()  # //:verilog.bzl — firtool: .fir → split .sv directory
verilog_file()       # //:verilog.bzl — firtool: .fir → single .sv file
verilog_single_file_library()  # //:verilog.bzl — cat multiple .sv → one file
```

### Verilator simulation (from rules_verilator)

```
verilog_library()        # @rules_verilator//verilog:defs.bzl — wraps .sv files with VerilogInfo
verilator_cc_library()   # @rules_verilator//verilator:defs.bzl — .sv → C++ simulation library
```

**Critical**: `verilator_cc_library` requires `module` (a label with `VerilogInfo` provider), NOT `srcs`. To simulate a hand-written .sv file:

```python
# WRONG — verilator_cc_library has no srcs attr
verilator_cc_library(name = "sim", srcs = ["foo.sv"], ...)

# RIGHT — wrap in verilog_library first
verilog_library(name = "foo_verilog", srcs = ["foo.sv"])
verilator_cc_library(name = "sim", module = ":foo_verilog", ...)
```

For Chisel-generated Verilog, use `verilog_directory()` output directly — it already provides `VerilogInfo`.

### LEC (equivalence checking)

```
eqy_test()    # //:eqy.bzl — Yosys-based structural LEC (gold vs gate .sv files)
lec_test()    # //lec:lec.bzl — kepler-formal LEC (combinational equivalence)
```

### Synthesis

```
orfs_flow()   # //:openroad.bzl — full OpenROAD flow (synth → place → route)
orfs_synth()  # //:openroad.bzl — synthesis only
```

**Critical**: `orfs_flow(abstract_stage=...)` only accepts: `place`, `cts`, `grt`, `route`, `final`. NOT `synth`. For synthesis-only, use `orfs_synth()` or set `abstract_stage = "place"` and only build the `_synth` target.

## firtool flags you always need

```python
FIRTOOL_OPTS = [
    "--lowering-options=disallowPackedArrays,disallowLocalVariables,noAlwaysComb",
    "--disable-all-randomization",
    # These disable Chisel verification layers that create include references
    # to files that won't exist in the concatenated output:
    "-disable-layers=Verification",
    "-disable-layers=Verification.Assert",
    "-disable-layers=Verification.Assume",
    "-disable-layers=Verification.Cover",
]
```

**Without `-disable-layers`**: the generated Verilog will have `` `include "layers-*.sv" `` directives that break Yosys/eqy reads. The layer files exist in the split directory but not in the concatenated single-file output.

## Chisel code generation patterns

### Using the shared CodeGen (//chisel:codegenlib)

The shared `codegen.CodeGen` takes a class name as the first argument and instantiates it reflectively. Works for classes with a no-arg constructor:

```python
chisel_binary(
    name = "gen",
    main_class = "codegen.CodeGen",
    deps = [":mylib", "//chisel:codegenlib"],
)
fir_library(
    name = "fir",
    generator = ":gen",
    opts = ["mypackage.MyModule"] + FIRTOOL_OPTS,
)
```

### Standalone generator (for modules with constructor args)

If your module takes constructor arguments (e.g. `DataWidth`), write a standalone generator:

```scala
object MyGen extends App {
  ChiselStage.emitHWDialect(new MyModule(DataWidth = 32), Array(), args)
}
```

```python
chisel_binary(name = "gen", main_class = "mypackage.MyGen", deps = [":mylib"])
fir_library(name = "fir", generator = ":gen", opts = FIRTOOL_OPTS)
```

## Verilator C++ testbench patterns

### Signal naming between Chisel wrapper and standalone module

Chisel testbench wrappers strip the `io_` prefix:
- `CountTo42CpuTestBench` → `top.done`, `top.result`
- `CountTo42Cpu` (standalone) → `top.io_done`, `top.io_result`

Use `#ifdef` macros to share test code between both:

```cpp
#ifdef TESTBENCH_WRAPPER
  #define DONE(top) (top).done
#else
  #define DONE(top) (top).io_done
#endif
```

### Standard clock/reset protocol

Chisel modules use `clock` (posedge) and `reset` (synchronous, active-high):

```cpp
void step() {
    ctx.timeInc(1); top.clock = 1; top.eval(); trace->dump(ctx.time());
    ctx.timeInc(1); top.clock = 0; top.eval(); trace->dump(ctx.time());
}
void reset(int cycles = 10) {
    top.reset = 1;
    for (int i = 0; i < cycles; i++) step();
    top.reset = 0;
}
```

## LEC limitations

### eqy (structural matching)

eqy works well when gold and gate have similar structure (same register names, similar logic cones). It struggles when the rewrite changes structure:
- **Individual registers vs arrays**: generated `regFile_1..31` vs rewrite `reg_file[0..31]`
- **Inlined ROM vs stored ROM**: generated `casez` on PC vs rewrite `program_rom[]`
- **Priority mux vs case**: generated `casez` chains vs rewrite `unique case`

For deep structural rewrites, eqy may need `depth > 10` or may not converge. Use kepler-formal or simulation-based equivalence instead.

### kepler-formal (combinational LEC)

kepler-formal requires:
- No sequential boundary changes between gold and gate
- Same names for hierarchical instances, sequential elements, and top ports
- Liberty files for cell definitions (only for post-synthesis netlists)

## Where things live (reference paths)

| What | Path |
|------|------|
| Chisel rules | `toolchains/scala/chisel.bzl` |
| FIR generation | `generate.bzl` |
| Verilog rules | `verilog.bzl` |
| VerilogInfo provider | `@rules_verilator//verilog:providers.bzl` |
| Verilator rules | `@rules_verilator//verilator:defs.bzl` |
| eqy rules | `eqy.bzl` |
| eqy template | `eqy.tpl` |
| lec rules | `lec/lec.bzl` |
| lec template | `lec/lec.yaml.tpl` |
| OpenROAD rules | `openroad.bzl` |
| sby (formal) rules | `sby.bzl` |
| Chisel test macro | `chisel/test.bzl` |
| Shared CodeGen | `chisel/src/main/scala/codegen/CodeGen.scala` |
| Shared TestBench.cpp | `chisel/TestBench.cpp` |
| Existing Chisel example | `chisel/BUILD`, `chisel/src/` |
| Existing sby example | `sby/BUILD` |
| Existing slang example | `slang/BUILD` |
| Existing eqy-flow | `eqy-flow.bzl` |

## Common mistakes to avoid

1. **Don't use `srcs` with `verilator_cc_library`** — use `verilog_library` + `module`
2. **Don't use `abstract_stage = "synth"` with `orfs_flow`** — not a valid stage
3. **Don't forget `-disable-layers`** in firtool opts — breaks eqy gold reads
4. **Don't forget `tags = ["manual"]`** on intermediate targets — prevents `bazel build //...` from building everything
5. **Don't assume IO names match** between Chisel wrapper and standalone module — wrappers strip `io_` prefix
6. **Don't expect eqy to handle deep structural rewrites** — use simulation + kepler-formal
