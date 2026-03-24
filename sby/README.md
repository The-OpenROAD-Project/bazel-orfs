# Formal verification with SymbiYosys

The `sby_test` macro runs bounded model checking (BMC) on Chisel-generated
designs using SymbiYosys with the bitwuzla SMT solver.

## Quick start

```python
load("@bazel-orfs-sby//:sby.bzl", "sby_test")

sby_test(
    name = "counter_formal",
    generator = ":generator",
    generator_opts = ["--top-module=MyCounter"],
    module_top = "FormalCounter",
    verilog_files = ["src/main/resources/FormalCounter.sv"],
    tags = ["manual"],
)
```

Run:

    bazelisk test :counter_formal_test

(Note: the actual test target has a `_test` suffix.)

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `depth` | 20 | BMC depth (clock cycles to unroll). Higher = deeper bugs but exponentially slower. |
| `firtool_options` | `DEFAULT_FIRTOOL_OPTIONS` | Firtool flags for both CHIRRTL lowering and Verilog generation. |
| `generator_opts` | `[]` | Options passed to the Chisel generator (e.g. `--top-module`, `--lowering-options`). |
| `verilog_files` | `[]` | Additional SystemVerilog files (formal wrappers with SVA properties). |

## Writing formal wrappers

The formal wrapper is a SystemVerilog module that instantiates the DUT and
adds `assume` / `assert` properties inside an `` `ifdef FORMAL`` block.
SymbiYosys reads these with `read -formal`.

```systemverilog
module FormalCounter(input clock, input reset, ...);

    MyCounter dut(.clock(clock), .reset(reset), ...);

`ifdef FORMAL
    initial assume(reset == 1'b1);

    // Properties go here
    always @(posedge clock)
        if (!reset) assert(dut_output <= MAX_VALUE);
`endif

endmodule
```

## Counterexample traces

When BMC fails, counterexample traces (VCD, Verilog testbench, Yosys
witness) are copied to `$TEST_UNDECLARED_OUTPUTS_DIR` so they survive
Bazel sandbox cleanup. Find them at:

    bazel-testlogs/<package>/<name>_test/test.outputs/

## Chisel assert() and the Verification layer caveat

Chisel `assert()` statements are compiled into CIRCT Verification layers
(`Verification.Assert`). These are **disabled by default** in the firtool
options because enabling them generates layer bind files with `` `include``
directives that yosys cannot resolve after file concatenation
(see [circt#9020](https://github.com/llvm/circt/issues/9020)).

This means **DUT-internal Chisel assertions are not checked by the formal
solver**. The solver can explore states that would violate internal
invariants, potentially producing spurious counterexamples.

To work around this, replicate critical DUT assertions as SVA properties
in the formal wrapper. For example, if the Chisel source has:

```scala
assert(!evicting || !hitLine.valid, "no access during eviction")
```

Add the equivalent in your `FormalXxx.sv`:

```systemverilog
always @(posedge clock)
    if (!reset) assert(!dut.evicting || !dut.hitLine_valid);
```

## firtool double invocation

The `sby_test` flow invokes firtool **twice**:

1. **fir_library** -- the Chisel generator calls firtool internally (via
   `CHISEL_FIRTOOL_PATH`) to lower CHIRRTL to FIRRTL.
2. **verilog_directory** -- firtool converts the `.fir` to split
   SystemVerilog files.

The `firtool_options` parameter is passed to both invocations. If you
override it, ensure both passes see the same flags, or the `.fir` and
`.sv` will disagree on layer handling and randomization.

## Debugging a failure

```bash
# Run with streamed output to see BMC progress
bazelisk test :my_formal_test --test_output=streamed --nocache_test_results

# Inspect the counterexample VCD
surfer bazel-testlogs/.../test.outputs/.../engine_0/trace.vcd
```

## Example with injected bug

Test example which should succeed:

    bazelisk test //sby:counter_test

Modify Counter.scala to have an error and re-run with:

    bazelisk test //sby:counter_test --sandbox_debug
