# Resuming the glitch measurement

Operational notes for the work [§5.2c](README.md#52c-a-second-core-and-where-that-stops) describes. The paper says what was
learned and why it stopped; this says what to type and what to expect.

Everything here is driven by hand from `tmp/`. Making it a bazel target
is the outstanding piece of work, and the reason it is worth doing is in
"What a sweep needs" below.

## The chain, for one unit

Inputs come from two bazel targets per design:

```sh
bazelisk build //test/coremark_joule/designs/asap7/ibex:cmj_ibex_grt_netlist
bazelisk build //test/coremark_joule/designs/asap7/ibex:cmj_ibex_grt_sdf
```

Then, with `$NET` and `$SDF` those two outputs:

```sh
# 1. Make them readable by iverilog: escaped dots, conditional arcs,
#    timing checks, and the header fields whose min::max has no typical.
python3 test/coremark_joule/scripts/iverilog_inputs.py \
  --verilog "$NET" tmp/x/design.v --sdf "$SDF" tmp/x/design.sdf

# 2. Cut one module and its delays out of the hardened design.
#    --module names the netlist module, --instance the SDF path: yosys
#    does not spell the two the same.
python3 test/coremark_joule/scripts/mult_extract.py \
  --netlist tmp/x/design.v --sdf tmp/x/design.sdf \
  --module ibex_multdiv_fast --instance multdiv_i \
  --out-verilog tmp/x/u.v --out-ports tmp/x/u_ports.txt \
  --out-name tmp/x/u_name.txt --out-sdf tmp/x/u.sdf \
  --out-state tmp/x/u_state.txt

# 3. Record the boundary. This is the expensive step -- see "Cost".
#    +cpu dumps the whole hardened design; +progress reports where the
#    core has got to while it fast-forwards.
vvp ... tmp/x/design.vvp +meminit=<hex> +cpu +cycles=2000 \
  +skip=<warm cycle> +progress=10000 +vcd=tmp/x/cpu.vcd

# 4. Generate the replay testbench and its stimulus.
python3 test/coremark_joule/scripts/mult_replay.py \
  --vcd tmp/x/cpu.vcd --ports tmp/x/u_ports.txt --clock <a clock leaf> \
  --scope <instance path substring> --state tmp/x/u_state.txt \
  --stim tmp/x/stim.hex --expect tmp/x/expect.hex \
  --tb tmp/x/tb.sv --module tmp/x/u_name.txt --period-ps <design period>

# 5. Two arms, then count. The annotated arm takes +sdf.
vvp ... tmp/x/u.vvp +stim=... +expect=... [+sdf=tmp/x/u.sdf] +vcd=...
python3 test/coremark_joule/scripts/glitch_count.py <vcd> \
  --subtree /dut/ --clock clk --out <json>
```

The compile needs `-g2012 -gspecify`, `IVL_BASE` pointing at
`@iverilog//:ivl_base`, and the ASAP7 cell models from
`//test/coremark_joule/rtl:asap7_stdcell` plus its `_empty` companion
for the physical-only cells. A whole-design compile also needs the SoC
wrapper and `cmj_sram_models.sv`, and `-DCPU_INST=rvtop` for VeeR.

## The oracle is the thing to watch

Every arm prints `N output mismatches`. **Anything but zero means the
numbers are not a measurement**, and every wrong number this work
produced was caught by it rather than by inspection:

- a multiplier held in reset for a whole window, because one port
  resolved to nothing and replayed as 0;
- an ALU replayed against a different instance's signals, because a
  bare name is unique only inside its scope.

Both produced a glitch figure in an entirely plausible range.

## Cost

Zero-delay whole-design recording, measured:

| design | instances | rate | 100k cycles |
|---|---|---|---|
| ibex | 25,851 | 76 cycles/s | ~35 min |
| VeeR EH1 | 164,858 | ~19 cycles/s | ~110 min |

The replay itself is seconds: each unit is a couple of thousand cells.
Annotation costs about 4.8x on ibex, and iverilog leaks memory under it
at roughly 53 KB/s of simulated events, so an annotated whole-design run
decays and does not finish ([§5.2](README.md#52-zero-delay-simulation-carries-no-glitch-power)). The replay avoids that entirely:
its annotated arm is small enough that the leak never matters.

## Where VeeR stops

`exu.i0_alu_e1` replays with every stateful cell seeded and no SDF
errors, and most of its outputs reproduce the recording digit for digit
-- `flush_path` and `pc_ff` match. Two do not: `out`, the 32-bit result,
is X, and `predict_p_ff` differs.

The hypothesis, untested: the seed is forced through one clock edge and
released, and VeeR's ALU flops are clocked by gated clocks generated
inside the module (`clkhdr`), so a flop whose gate is shut at that edge
never captures and reverts to X when the force is let go. What would
test it is holding the force until every stateful cell has seen an edge
on its own clock, or excluding a warm-up window from both the comparison
and the counts and saying so.

## What a sweep needs

The per-unit sweep is the reason the recording dumps a whole design
rather than one scope. `units.json` names the preserved modules per
design; each replays in seconds off one shared recording, so bazel can
fan them out and cache the expensive part. Two things to know before
building it:

- **Scope resolution is mandatory.** VeeR has four instances of
  `exu_alu_ctl`. Without `--scope` the sampler silently reads whichever
  the dump declared first.
- **Not every core is reachable.** SERV's kept modules are
  parameterized and do not survive into the ODB ([§5.7](README.md#57-attribution-does-not-survive-parameterized-modules)), so it has no
  module boundary to cut -- and SERV is the core [§5.2](README.md#52-zero-delay-simulation-carries-no-glitch-power) most wants,
  because its bit-serial datapath should glitch worst. picorv32 declares
  two units. VeeR has no multiplier module at all: `exu_mul_ctl` is not
  marked `keep_hierarchy`, so it is absorbed into `exu` and there is no
  like-for-like comparison against ibex's multiplier.

## Four-state simulation is the recurring cost

Three separate dead ends came from X out of uninitialised state: the
whole-core annotation driving X across ibex's netlist, a testbench
releasing reset on a clock edge, and VeeR's memories returning X from
locations never written. None of it is visible from Verilator, which is
two-state. When a gate-level run behaves oddly, suspect X first.
