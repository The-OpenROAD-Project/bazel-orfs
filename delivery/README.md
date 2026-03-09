# Chisel to Verification-Friendly SystemVerilog: Roundtripping LEC Flow

## Motivation

Hardware design generators (Chisel, SpinalHDL, Amaranth) let small teams
explore large parameter spaces — pipeline widths, cache sizes, queue depths —
by synthesizing variants and comparing PPA, without hand-rewriting RTL for
each configuration. But the generated Verilog has drawbacks:

- **Unreadable by verification teams.** Machine-generated names, flat
  structure, and missing idioms make code review, debugging, and DV impractical.
- **Unfriendly to EDA tools.** Many formal verification and linting tools
  expect idiomatic SystemVerilog — `always_ff`/`always_comb`, named types,
  `unique case`, no packed arrays.
- **Fragile for timing closure.** After place-and-route, even a logically
  equivalent regeneration can shift placement enough to break timing. Locked-
  down, human-reviewed RTL under source control preserves known-good results.

The solution is a **roundtripping flow**: use the generator for exploration,
then produce an idiomatic SystemVerilog rewrite that is:

1. **LEC-verified** against the generator output (combinational equivalence)
2. **Simulation-tested** with the same testbench on both RTL variants
3. **Synthesis-proven** through the standard physical design flow
4. **Tool-compatible** (slang, Verilator, Yosys, commercial tools)

The rewrite is done by AI (Claude), making the translation fast and cheap.
The LEC step ensures correctness mechanically, so the human reviewer only
needs to check readability and style — not logical equivalence.

## What This Example Demonstrates

A mock RISC-V CPU that counts to 42, end-to-end:

| Step | What | Tool |
|------|------|------|
| Generate | Chisel → FIRRTL → Verilog (32-bit config) | firtool |
| Rewrite | Verilog → idiomatic SystemVerilog | Claude (AI) |
| Simulate (pre-synth) | C++ testbench on generated Verilog | Verilator |
| Simulate (pre-synth) | Same testbench on rewritten SystemVerilog | Verilator |
| LEC | generated ≡ rewritten | eqy (Yosys) |
| Synthesize | SystemVerilog → gate netlist | OpenROAD (ASAP7) |
| LEC (post-synth) | RTL ≡ gate netlist | eqy / kepler-formal |

### The CPU

The Chisel source defines a `CountTo42Cpu(DataWidth)` parameterized for 32 or
64 bits. It executes a hardcoded program:

```
li   x1, 0       # counter = 0
li   x2, 42      # target = 42
loop:
  addi x1, x1, 1 # counter++
  bne  x1, x2, loop
halt              # x1 == 42
```

The delivered SystemVerilog (`rtl/CountTo42Cpu.sv`) is fixed at 32 bits,
using idiomatic constructs: `always_ff`, `always_comb`, `unique case`,
`localparam`, named opcodes, and explicit synchronous reset.

## Quick Start

```bash
# Pre-synthesis simulation (generated Verilog)
bazelisk test //delivery:cpu_generated_test --test_output=streamed

# Pre-synthesis simulation (idiomatic SystemVerilog rewrite)
bazelisk test //delivery:cpu_rewrite_test --test_output=streamed

# LEC: generated ≡ rewrite
bazelisk test //delivery:cpu_rewrite_lec_test --test_output=streamed

# Synthesis (ASAP7)
bazelisk build //delivery:CountTo42Cpu_synth

# All verification targets
bazelisk test //delivery:all_tests --test_output=errors
```

### kepler-formal LEC (standalone)

If you have kepler-formal built locally:

```bash
# Generate the Verilog files first
bazelisk build //delivery:cpu_generated.sv

# Run kepler-formal directly
kepler-formal -verilog \
  bazel-bin/delivery/cpu_generated.sv \
  delivery/rtl/CountTo42Cpu.sv
```

## File Layout

```
delivery/
  BUILD.bazel                          # All Bazel targets
  README.md                            # This file
  constraints.sdc                      # Synthesis timing constraints
  LLM.md                               # LLM cribs for implementing this flow
  CpuTest.cpp                          # Verilator C++ testbench (shared)
  src/main/scala/cpu/
    CountTo42Cpu.scala                 # Chisel source (parameterized)
  src/test/scala/cpu/
    CountTo42CpuTestBench.scala        # Chisel testbench wrapper
  rtl/
    CountTo42Cpu.sv                    # Idiomatic SystemVerilog (deliverable)
```

## Design Decisions

**Why 32-bit fixed in the SystemVerilog?** The generator supports 32 and 64
bits, but the delivered RTL locks the parameter. This is intentional:
parameterized abstractions help during exploration but make formal verification
and sign-off harder. Concrete, flat code is easier to reason about.

**Why `--disallowPackedArrays,disallowLocalVariables,noAlwaysComb`?** These
firtool lowering options produce Verilog that is maximally compatible with Yosys
(for eqy LEC) and Verilator. The idiomatic SystemVerilog rewrite is free to use
richer constructs because it targets slang/commercial tools.

**Why eqy AND kepler-formal?** eqy (Yosys-based) is open-source and integrated
into the Bazel flow. kepler-formal is a dedicated LEC tool with better
performance on larger designs. Both verify the same property: combinational
equivalence between gold and gate netlists.

## Tutorial: Bug Fix Workflows with Claude

This section walks through the two bug-fix flows that keep the generator source
and production SystemVerilog in sync. Both use LEC to verify the result.

### Flow 1: Bug found in Chisel, update SystemVerilog to match

**Scenario**: You discover that the BNE instruction has an off-by-one error
in the branch offset calculation.

**Steps:**

1. **Fix the bug in Chisel** (`CountTo42Cpu.scala`):
   ```scala
   // Before (wrong): pc := (pc.asSInt + immSext(...).asSInt).asUInt
   // After (fixed):  pc := (pc.asSInt + immSext(...).asSInt + 1.S).asUInt
   ```

2. **Verify the Chisel fix** — run the generated Verilog simulation:
   ```bash
   bazelisk test //delivery:cpu_generated_test --test_output=streamed
   ```

3. **Ask Claude to update the SystemVerilog** to match the new generated
   Verilog. Provide both the old and new generated Verilog as context:
   ```
   Claude, the BNE branch offset in CountTo42Cpu.scala was fixed (see diff).
   Update rtl/CountTo42Cpu.sv to match. Keep the fix minimal — only change
   the affected logic, preserve all naming and style.
   ```

4. **Verify the rewrite matches** — run LEC:
   ```bash
   bazelisk test //delivery:cpu_rewrite_lec_test --test_output=streamed
   ```

5. **Run simulation on the rewritten SystemVerilog** to double-check:
   ```bash
   bazelisk test //delivery:cpu_rewrite_test --test_output=streamed
   ```

6. **Commit both files** — Chisel source and SystemVerilog stay in sync.

### Flow 2: Bug found in SystemVerilog, upstream fix to Chisel

**Scenario**: During verification/sign-off, you find that the HALT opcode
doesn't properly gate register writes (a register write in the same cycle as
HALT could corrupt state).

**Steps:**

1. **Fix the bug directly in SystemVerilog** (`rtl/CountTo42Cpu.sv`) —
   minimally, to preserve timing closure:
   ```systemverilog
   // Add guard: only write reg_file when not halting
   OP_HALT: begin
     halted <= 1'b1;
     // No register writes in halt cycle
   end
   ```

2. **Verify the SystemVerilog fix** — run simulation:
   ```bash
   bazelisk test //delivery:cpu_rewrite_test --test_output=streamed
   ```

3. **Ask Claude to upstream the fix to Chisel**:
   ```
   Claude, I fixed a bug in rtl/CountTo42Cpu.sv (see diff). The HALT opcode
   now gates register writes. Upstream this fix to CountTo42Cpu.scala so the
   generator produces equivalent logic.
   ```

4. **Regenerate and run LEC** to confirm both sides match:
   ```bash
   bazelisk test //delivery:cpu_rewrite_lec_test --test_output=streamed
   ```

5. **Commit both files** — the generator source stays the source of design
   intent; the production SystemVerilog stays the verification baseline.

### Key Principles

- **Minimal patches protect timing closure.** Don't regenerate the entire
  SystemVerilog file for a one-line fix — patch only the affected logic.
- **LEC is the mechanical proof.** The human reviewer checks readability and
  style; LEC checks logical equivalence. Don't conflate the two.
- **Both directions work.** Bugs found early go Chisel → SV. Bugs found late
  go SV → Chisel. The flow is symmetric.
- **Claude does the translation.** The AI makes the rewrite fast and cheap.
  The LEC step makes it trustworthy.

## Extending This Example

- **64-bit variant**: Change `DataWidth = 64` in the testbench, regenerate,
  and create a parallel `rtl/CountTo42Cpu_64.sv`.
- **Post-synthesis simulation**: Extract the gate netlist from
  `//delivery:CountTo42Cpu_synth`, add liberty cell models, and run the same
  `CpuTest.cpp` through Verilator with the gate-level Verilog.
- **kepler-formal in Bazel**: Write a `kepler_formal_test` rule that wraps the
  `kepler-formal` binary, similar to the existing `eqy_test` rule.
- **Larger designs**: The same flow scales to real cores. The LEC step becomes
  more valuable as designs grow — manual equivalence review doesn't scale,
  but formal checking does.
