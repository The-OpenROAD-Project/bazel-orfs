---
name: check-setup
description: >-
  Find the registers a design's timing never sees and the setup problems behind them with
  OpenSTA's check_setup: what each of its warnings means (from search/CheckTiming.cc), why
  the bare count in ORFS's 2_1_floorplan.log is not enough, how to get the pins and the
  modules they sit in through odb-debug's check_setup tool, which warnings an SDC written
  with set_max_delay produces by design, and the blind spot carried patch 0109 closes (a
  register the clock reaches only on the edge it does not launch on). Use before quoting a
  period on a new or changed design, when a path you expect is "No paths found", when a
  clock gate or a tie cell sits in a clock path, or when someone says "check_setup is
  clean".
---

> **Repo**: Run from the bazel-orfs root, or any workspace that depends on bazel-orfs. Applies to every ORFS flow.

A register that no clock reaches is a register the timer never checks. Its paths are not slow, they are absent, and a period measured with them absent is a lower bound. `check_setup` is how OpenSTA says so, if you read it right.

ARGUMENTS: $ARGUMENTS

## What it reports

From `search/CheckTiming.cc`; a bare `check_setup` runs every check, each printing `Warning: There are N ...`, and `-verbose` adds the pins:

| warning | what it means |
|---|---|
| unclocked register/latch pin | a register clock pin with no clock. With patch 0109, also one no clock reaches on the edge it launches on |
| register/latch pin with multiple clocks | more than one clock reaches a register clock pin |
| unconstrained endpoint | an output port with neither a clocked output delay nor a `set_max_delay -to` it, or a setup check whose clock side is not a clock or whose data has no clocked arrival |
| combinational loop | a loop with its cut points under `-verbose` |
| input port missing set_input_delay, output port missing set_output_delay | a port with no port delay. With patch 0110 the warnings read unconstrained input port and unconstrained output port, and a port a `set_max_delay` names is not one |
| generated clock not connected to a clock source | as it says |

## The count in the floorplan log is not enough

ORFS's `floorplan.tcl` runs a bare `check_setup` right after reading the netlist and the SDC, so `logs/.../2_1_floorplan.log` has one line per warning and no pins. To learn which pins, and which modules they sit in, ask the floorplan's database (`.claude/skills/odb-debug/SKILL.md`): start the daemon on `2_1_floorplan.odb` with timing, then the `check_setup` tool (`od_check_setup`). It returns each warning with its count, example pins and the module paths the pins cluster in, and, for unconstrained endpoints, how many have only input ports in their fan-in. `out` writes every line to a file; never read a 100k-line list into context.

A `_deps` lane at floorplan (the `deps-lane` skill) gets the database for a design nobody has built: synthesis and the floorplan, minutes on a block.

## A set_max_delay is a constraint, not a missing one

`.claude/skills/macro-constraints` explains why this flow writes no `set_input_delay` or `set_output_delay`: the platform's `constraints.sdc` budgets every port with `set_max_delay`. Stock `check_setup` names **every** input port as missing `set_input_delay`, every output port as missing `set_output_delay`, and every register fed only from inputs as an unconstrained endpoint, though `report_checks` times each against its `set_max_delay`. On XSTile those are 687 + 952 + 520 lines of warnings that bury the 280 that matter.

Stock already counts an output port named by `set_max_delay -to` as constrained in the unconstrained-endpoint check (`hasMaxDelay`). Patch 0110 follows that precedent and extends it to `set_max_delay` generally: an input port named by `-from`, an output port named by `-to`, and a setup endpoint whose arrival a `set_max_delay` constrains are not reported. The port warnings follow the endpoint warning's pattern, `There are N unconstrained input ports.`, and say what was found, not which command to add: which one fits depends on the design.

`//test/check_setup:max_delay_test` checks it, and that a port and a register with no constraint at all are still named. On an OpenROAD carrying 0110, every warning under this SDC style is a finding: unclocked register pins, multiple clocks, loops, an unconstrained port, an unconstrained endpoint.

## check_setup was blind to the case that matters most

Stock OpenSTA calls a register unclocked only when its clock network misses it, and that network is found without regard to rise and fall. A register whose clock pin sees only the edge it does not launch on is in the network: `check_setup` says nothing while `report_checks -to` its D says `No paths found`. ASAP7's ICG with its enable tied high is one: its enabled `CLK->GCLK` arc set carries only the falling edge, and Sim disabled the rising default arc with it (parallaxsw/OpenSTA#532). The library is what is broken; OpenSTA tolerates it since parallaxsw/OpenSTA@fdb00f48.

Two carried patches, each with its own test in `test/check_setup`:

- `patches/0108-opensta-icg-cond-arc-sim.patch` (fdb00f48, which resolves #532): the flop behind the gate is clocked and timed (`icg_tied_enable_test`).
- `patches/0109-opensta-check-setup-launch-edge.patch`: `check_setup` counts a register no clock reaches on its launch edge as unclocked (`launch_edge_test`, a clock through a cell that carries only the falling edge).

Patch 0110 (above) is a third concern; it applies on top of 0109.

So "check_setup is clean" means something only on an OpenROAD carrying 0109. To find what an older tree silently left untimed, run the check with a binary that carries 0109 and not 0108 (`/byo-openroad`, `OPENROAD_EXE`): the unclocked pins it reports are the registers the older timer skipped.

## XiangShan's blocks, audited

`check_setup` on each block's floorplan, with a binary carrying 0109 only and one carrying both patches. The counts were the same with both binaries. `ICGs` counts the integrated clock gates in the netlist and how many have an enable tied to a constant:

| block | ICGs (tied) | unclocked | multiple clocks | loops | inputs / outputs missing a delay | unconstrained endpoints (input-only / classified) |
|---|---|---|---|---|---|---|
| FltRegionModule | 0 | 0 | 0 | 0 | 3729 / 2979 | 137 (137 / 137) |
| VecRegionModule | 0 | 0 | 0 | 0 | 4986 / 3211 | 636 (500 / 500) |
| CoupledL2 | 4 (0) | 0 | 0 | 0 | 1345 / 1183 | 48 (48 / 48) |
| Frontend | 214 (0) | 0 | 0 | 0 | 2085 / 1175 | 410 (410 / 410) |
| MemBlock | 43 (0) | 0 | 0 | 0 | 5151 / 4344 | 1089 (500 / 500) |

Every warning is one the SDC style produces by design. No block has a tied-enable ICG, so #532 leaves the blocks' periods alone.

The parent, `XSTile`, is where #532 bites. Its floorplan has 7 ICGs; the two in `core/backend/inner_intRegion/intExuBlock/exuALU0_AluCsrFenceLink` (`ClockGate`, `ClockGate_1`) have their enable tied high and gate 20,878 register clock pins:

| XSTile binary | unclocked | unconstrained inputs / outputs | unconstrained endpoints (input-only / with a register, of 500 classified) |
|---|---|---|---|
| stock (the floorplan log) | 0 | 687 / 952 | 4621 |
| 0109 only | 20878 | 687 / 952 | 4621 (0 / 500) |
| 0108 + 0109 | 0 | 687 / 952 | 800 (221 / 279) |
| 0108 + 0109 + 0110 | 0 | 0 / 0 | 280 (0 / 280, all classified) |

The two gates are XiangShan's own: `ExeUnit` gives every function unit a clock gate and sets the CSR and fence units' enable to `true.B` (`ckAlwaysEn`). Utility's `ClockGate` was a black box firtool could not fold, so `xs_icg.ys` mapped them onto the ICG. `test/coremark_joule/xiangshan/patches/0010` makes it CIRCT's clock gate, which firtool folds when an enable is constant: `xstile_clock_gates` counts 268 gates under XSTile, 2 always on, before it and 263, none always on, after (the other 3 are `GatedSplittedSRAM` gates with the same inputs, merged into one).

Stock `check_setup` says nothing about the 20,878 untimed flops; it shows them only as part of 4,621 unconstrained endpoints, a warning this SDC style always raises. With 0108 they are timed and the count drops to 800. With 0110 the port warnings and the input-only endpoints are gone: 280 endpoints are left, each with a register in its fan-in, 230 of them under `core/backend` (hardened-block input pins such as `inner_fpRegion/in_fromVecRegion_wbM3Wakeup_*`).

## Reading what is left in a parent

In a parent of hardened blocks, an unconstrained endpoint whose fan-in has a register is usually fed by a block output with no timing arc in the block's model. Nothing arrives there, so nothing downstream is timed. Read it one hop at a time:

1. `get_fanin -to <endpoint> -startpoints_only -flat` in the parent: the single startpoint is the block output pin.
2. Does that pin have a `timing()` group in the block's model? The parent's floorplan and place read the place-stage model (`<variant>_pre_layout/<block>_typ.lib`); from the parent's CTS on, the CTS one.
3. If not, open the block's own floorplan and follow the output's driver back to its source.

On XSTile's floorplan, all 280 traced:

| endpoints | the block output is driven by | fix |
|---|---|---|
| 128 | `FpRegFile`, an AUTO_MEMORIES macro whose `.lib` the place-stage model never read | bazel-orfs #1224 |
| 151 | a constant: `TIELO`/`TIEHI` through a buffer, or an `AND2` of a register with a `TIELO` | patch 0113 writes it into the model as that constant |
| 1 | the `reset` port, passed straight through Frontend and false-pathed by design | none needed |

After CTS a block's model loses arcs for another reason: a register CTS left off the clock in the hierarchical netlist (patches 0111, 0112). `check_setup` on a block's `4_cts.odb` read back shows it as unclocked register pins.
