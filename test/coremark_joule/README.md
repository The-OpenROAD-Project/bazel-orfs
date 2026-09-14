# CoreMark per Joule, at global route

The shape of energy efficiency against performance for small RISC-V
cores: CoreMark/Joule plotted against CoreMark/MHz, screened at global
route so a point costs minutes rather than hours.

**Everything here is `manual`.** `test/` is never shipped (see
`public_surface.py`), and nothing in this directory is pulled in by a
wildcard build.

## Running it

```sh
bazelisk run //test/coremark_joule/sim:report
```

Builds every measurement it reports and prints the table. SERV's runs
are ~10^8 cycles each, so this is minutes, not seconds.

The gates, cheapest first:

```sh
# Does the core boot and get a load/store right?
bazelisk test //test/coremark_joule/sim:smoke_picorv32_rv32im_test

# Does CoreMark compute the right answer on it?
bazelisk test //test/coremark_joule/sim:picorv32_rv32im_crc_test
```

When something fails, follow the `debug-rtl-sim` skill rather than
reaching for a waveform.

## How a number is made

`CoreMark/MHz = 1e6 / (cycles_3 - cycles_2)`.

Two ELFs are built per configuration, at `ITERATIONS=2` and
`ITERATIONS=3`, and the difference is one CoreMark iteration. It cancels
reset, `.bss` zeroing, data init, the CRC checks and the whole printed
report -- everything that is not the benchmark. It is also what removes
CoreMark's ten-second run rule from the problem: no simulated core is
going to run for ten seconds of wall clock.

The two ELFs differ by one word of `.data`, and
`//test/coremark_joule/sw:iteration_delta_test` asserts exactly that, so
the subtraction's premise cannot rot.

Correctness is the three CRCs CoreMark prints, **not** its own error
count and not the exit status. The port stubs the timer to a constant so
the two runs print identical text, which makes CoreMark report "must
execute for at least 10 secs" every time. A correct run reports errors.

**These are not reportable CoreMark scores.** A three-iteration run does
not satisfy CoreMark's run rules. The numbers are comparable within this
study and not against published figures.

## Layout

| path | what |
|---|---|
| `sw/port/` | the CoreMark port layer: CoreMark's sources stay byte-unmodified |
| `sw/` | ELF builds, one per ISA and iteration count |
| `rtl/cmj_<core>.v` | each core's configuration, frozen, shared by the simulator and the flow |
| `rtl/cm_soc_<core>.v` | simulation wrapper: RAM, sim-control device, bus adapter |
| `sim/` | the Verilator harness and the measurement targets |
| `designs/asap7/<core>/` | `config.mk`, constraints and `units.json` for the flow |
| `scripts/` | parsers and checks, each with a unit test |

## The platform

Two memory-mapped words are the whole bare-metal contract, and all three
cores see the same two:

| address | write | effect |
|---|---|---|
| `0x1000_0000` | byte | one character of stdout |
| `0x1000_0008` | 1 | stop the simulation |

That is why one C runtime, one linker script and one CoreMark port serve
cores whose buses, privilege models and CSR support have nothing in
common. Cycles are counted in the harness rather than read from a CSR,
because ibex has `mcycle`, picorv32 has no machine-mode CSRs at all, and
SERV's CSR block is a build option.

The image carries entry points for both reset conventions in play --
`0x000` for a core that starts at its reset address, `0x180` for ibex,
which fetches from `boot_addr_i + 0x80`.

## The SAIF window: one hot iteration

Switching activity has to come from the part of the run that represents
the benchmark, and that is not the whole run. Startup, data init and the
first iteration all execute cold; the report at the end is `ee_printf`
and nothing else. Averaging activity over those would understate the
benchmark and overstate whatever the prologue happens to do.

So the window is exactly **one iteration, the last one** -- the same
quantity the cycle count uses, and the one running hot.

There is an exact, observable anchor for it. CoreMark prints nothing
until its report, so the cycle of the first character out is precisely
where the benchmark loop ended. With `D` the cycles per iteration
(`cycles_3 - cycles_2`), the last iteration spans

    [first_output - D, first_output]

and the harness records `first_output` alongside the cycle count.
Nothing in the benchmark is modified to mark it.

Cycle behaviour is identical between the RTL and gate-level simulations,
so the window is derived from the cheap RTL run and applied to the
expensive netlist one. On picorv32 that checks out two ways: the window
start computed from `first_output - D` equals `cycles_2 - report_cost`
exactly.

Two mistakes worth not repeating, both of which produce a plausible SAIF
rather than an error:

- **Dump on a time base relative to the window.** Absolute time makes
  the SAIF's `DURATION` span the whole prologue, dividing every toggle
  rate by however far into the run the window starts.
- **Dump at both clock phases.** Sampling once per cycle always catches
  the clock at the same level, and the SAIF then records a clock that
  never toggles -- not a small error on the busiest net in the design.

A correct capture is checkable: `clk` should show `TC` equal to twice
the window's cycle count, and the duration should equal one iteration.

## Frequency, and why it is its own job

The frequency a core is scored at is `1 / (period - WNS)` with the
period pushed until WNS is slightly negative. Positive WNS means the
optimiser met its target and coasted, so the achieved period understates
the core; deeply negative means repair gave up and the netlist is in a
different regime.

Finding that period is a tuning job, not a build sweep: what is wanted
is a decision, pinned into the design, re-derived when the design
changes -- the same shape as the floorplan derivation, run rather than
built.

**It cannot ride on auto_floorplan, though**, and the reason is
structural rather than incidental. `auto_floorplan_candidate.tcl` seeds
each candidate from `1_synth.odb` and re-runs floorplan through finish:
every candidate shares one synthesis, which is what makes racing twenty
of them affordable. The clock period is a *synthesis* input -- change it
and synthesis and everything after it rebuild -- so a period candidate
cannot start where a floorplan candidate starts.

Floorplan tuning and period tuning therefore have different starting
points and different costs, and want to be separate jobs. They also
interact: the floorplan is derived at a period, and the period is
achieved on a floorplan. Two passes settle it -- period on the incumbent
floorplan, floorplan at that period, period again -- and how far the
second pass moves is worth reporting rather than assuming it converged.

## Functional units

Each design sets `SYNTH_HIERARCHICAL=1` with an explicit
`SYNTH_KEEP_MODULES`, so `report_power -saif -instances` can attribute
power to units from CPU architecture -- fetch, decode, execute,
load/store, register file, CSR. `units.json` maps each kept Verilog
module to its architectural unit.

`synth.tcl` errors on a kept-module name that is not in the elaborated
design, so the enumeration cannot rot silently: an upstream rename fails
the build instead of quietly moving a unit into "other".

**Parameterized modules do not survive into the ODB.** SERV's kept
modules are all parameterized, so yosys names them
`$paramod\serv_alu\W=s32'...`, and while all thirteen are present in
`1_2_yosys.v`, the grt ODB has zero module instances and the written
netlist is one flat module. picorv32's plainly named `picorv32_pcpi_mul`
and `picorv32_pcpi_div` survive intact. The per-unit breakdown therefore
works today only for designs whose kept modules are unparameterized --
which is the smaller half of the interesting ones, and is what makes
this the next thing to fix rather than a footnote.

The failure is silent, which is the part worth noting: the flow
completes, the netlist is valid, and the breakdown simply comes back
empty. `power_units_grt.tcl` prints the module-instance count for that
reason.

How well this works is a property of the RTL, and it differs sharply:

| core | attribution |
|---|---|
| SERV | excellent -- one module per architectural function |
| ibex | excellent -- the pipeline stages are modules |
| picorv32 | **poor** -- `picorv32.v` defines eight modules and the CPU is one of them; decode, execute, the ALU and control are all inline |

picorv32 therefore carries a written, reasoned waiver in its
`units.json` rather than a silent shortfall. "This core cannot be
attributed" is itself a result worth reporting about open-source RTL.

`AUTO_MEMORIES=1` maps inferred memories onto generated SRAM views. It
matters because a register file hardened as flops can dominate a small
core, and then the energy measured is mostly the wrong thing.

**It applies to fewer designs than it first appears.** ORFS converts
memories that are *modules* -- the detector looks for a module whose
ports follow the firtool convention. picorv32's register file is an
inline `reg [31:0] cpuregs [0:31]` array, and the yosys pass infers it,
marks it convertible and writes `cpuregs` into `blackboxes.txt` -- but
`blackbox cpuregs` matches no module, and the design synthesises to 1024
flip-flops regardless. The macro is generated and never used. Verified
identical on the partition and serial synthesis paths, so it is not a
consequence of `SYNTH_KEEP_MODULES` forcing partitioned synthesis.

So AUTO_MEMORIES is off for picorv32, and its register file is reported
as flops -- which is what its RTL describes. Where a core's register
file *is* a module, `memories_applied_test` asserts the macro reaches
the netlist, because a generated-then-ignored macro is a silent wrong
answer rather than a failure.

The generated views come from a synthetic memory compiler, so a memory's
contribution to CoreMark/Joule is a model rather than silicon, wherever
it does apply.

**A converted memory needs its behavioural model to simulate at all.**
Synthesis blackboxes the module so the liberty view wins, and a blackbox
stores nothing. Run the gate-level netlist without a behavioural model
for it and the register file does not hold values: CoreMark does not
merely report low memory power, it fails its CRCs or never terminates.
The SAIF has to come from a full CoreMark run on the netlist, so the
memory has to work.

`memories.json` records `behavioral_model: {file, module}` for this. The
gate-level simulator reads the grt netlist plus that model in place of
the blackboxed macro -- the same substitution synthesis made, in the
opposite direction. Then the macro's pins toggle, the SAIF carries their
activity, and `report_power -saif` can attribute the memory's power.

This is a prerequisite for any core whose memory is converted, not a
refinement. The existing CRC gate is what catches getting it wrong,
which is the reason that gate runs against the gate-level netlist and
not only against RTL.

### Where each core's register file ends up

| core | register file in RTL | hardened as |
|---|---|---|
| picorv32 | inline `reg [31:0] cpuregs [0:31]` array | flip-flops |
| SERV | `serv_rf_ram`: array + read register + x0 gating | flip-flops |
| ibex | `ibex_register_file_ff`, flops by construction | flip-flops |

None of the three converts, and in each case for a reason in the RTL
rather than a flow defect. A memory is converted by blackboxing a module
so the liberty view replaces its body, which needs a module that is
nothing but the memory. picorv32's is an inline array; SERV's module
carries the read register and the x0 gating besides; ibex's is flops by
design.

SERV is the one that matters. Keeping the register file in SRAM is its
whole architectural trick, and measuring it as flip-flops understates
it. Getting the macro would mean splitting the array out into its own
module -- a patch on SERV's RTL, and so a change to the design being
measured. That is a decision to take deliberately rather than by
default, and it is recorded here rather than made quietly.

## Cores after the first three

The first three establish the low end. The interesting region is 5-15
CoreMark/MHz, and the structural fact that shapes the study is that it is
populated only by large out-of-order cores: the x-axis spans about three
decades and the cost of a point grows with it. So the shape is earned
cheaply at the bottom and *extended* deliberately upward, each core its
own budgeted run.

| # | core | CoreMark/MHz | HDL | practical pain |
|---|---|---|---|---|
| — | SERV / picorv32 / ibex | 0.02 / 0.55 / 2.45 | Verilog / Verilog / SV | done |
| 4 | CV32E40P | ~3.1 | SystemVerilog | low |
| 5 | VeeR EL2 | ~2.6 | SystemVerilog | low |
| 6 | CVA6 | ~2.5 | SystemVerilog | medium — RV64 contrast at similar CoreMark/MHz |
| 7 | **VeeR EH1** | **~4.9** | SystemVerilog | **low — already an ORFS design (`swerv`)** |
| 8 | OpenC910 | ~4.9-7 | Verilog/SV | medium — 3-issue OoO, silicon-proven |
| 9 | SonicBOOM | 6.2 | Chisel | high — pulls in the Scala generator |
| 10 | XiangShan | ~10-15 | Chisel | high — very large |

**VeeR EH1 is the next one to do.** It is the first rung genuinely inside
the 5 CoreMark/MHz band, it is SystemVerilog rather than Chisel, and ORFS
already carries it as `swerv` -- so it costs a config.mk and a bus
adapter rather than a new toolchain.

Rungs 4-8 need no generator toolchain. Rungs 9-10 pull in Chisel, which
is the natural place to stop if the study stops early.

## Licensing

CoreMark's sources are byte-unmodified. Everything platform-specific
lives in `sw/port/`, which is the porting surface CoreMark documents --
`core_portme.{c,h}` and `ee_printf.c` all ship upstream as templates
whose platform bodies are `#error` stubs. CoreMark's Acceptable Use
Agreement forbids using the trademark in connection with a modified copy
of the Software.
