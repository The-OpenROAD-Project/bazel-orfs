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

## Functional units

Each design sets `SYNTH_HIERARCHICAL=1` with an explicit
`SYNTH_KEEP_MODULES`, so `report_power -saif -instances` can attribute
power to units from CPU architecture -- fetch, decode, execute,
load/store, register file, CSR. `units.json` maps each kept Verilog
module to its architectural unit.

`synth.tcl` errors on a kept-module name that is not in the elaborated
design, so the enumeration cannot rot silently: an upstream rename fails
the build instead of quietly moving a unit into "other".

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
