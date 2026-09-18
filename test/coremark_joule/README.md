# CoreMark/MHz and CoreMark/Joule for Four RISC-V Cores on ASAP7, from an Open and Re-runnable Flow

*As of September 2026, this is the best we could do.* Four RISC-V cores --
SERV, picorv32, ibex and VeeR EH1 -- hardened on ASAP7 with OpenROAD and
measured for CoreMark/MHz and CoreMark/Joule at global route, with switching
activity from one hot CoreMark iteration. Every input is open and pinned, and
the chain re-runs with one command.

Done in a few days with Claude Code on bazel-orfs, OpenROAD and ORFS, for CPU
time in the days and a token spend that never mattered. It is offered as an
example of a question a reader can now put to bazel-orfs: state it, spend the
compute, get a measured answer with its limitations attached.

We found no other published comparison with all three of: more than one core
hardened to an ASIC netlist, activity from CoreMark itself, and open,
re-runnable inputs. ULPMark-CM [2] has dozens of MCUs on silicon, one core
each; a seven-core survey [15] reports 8.7 CoreMark iterations/mJ for ibex on
an "ASIC prototyping platform" we read as an FPGA; the closest modern-node
comparison [5] pairs CoreMark/MHz with power on a different benchmark; and
[12, 13] measured CoreMark energy at 65 nm with PrimeTime, citable but not
re-takeable. [§4.5](#45-what-else-could-be-plotted-and-why-almost-nothing-can) dates that check.

CoreMark only, on purpose. It is the one benchmark every core reports, so a
CoreMark energy figure has a comparator on every datasheet; and its working
set fits inside core + L1, the boundary this study draws and verifies ([§3.1](#31-the-measurement-boundary)).
Nothing here speaks to workloads that leave it.

**A measurement study in the bazel-orfs repository.** The flow targets are
not in CI; the parsers and number checks are. Table 1 and every ratio the
prose quotes are rendered from `results.json` and checked by a test. [§10](#10-running-it-and-adding-your-own-core) is
how to run it, and how a fifth core joins.

---

## Contents

- [Abstract](#abstract)
- [Limitations, ranked](#limitations-ranked)
- [1. Introduction](#1-introduction)
- [2. Background](#2-background)
- [3. Method](#3-method)
- [4. Results](#4-results)
- [5. Threats to validity](#5-threats-to-validity)
- [6. What the flow got wrong](#6-what-the-flow-got-wrong)
- [7. Related work](#7-related-work)
- [8. Further work](#8-further-work)
- [9. Conclusion](#9-conclusion)
- [10. Running it, and adding your own core](#10-running-it-and-adding-your-own-core)
- [11. Licensing](#11-licensing)
- [Appendix A. Commodity silicon on the same axes](#appendix-a-commodity-silicon-on-the-same-axes)
- [References](#references)

---

## Abstract

CoreMark/MHz is reported for almost every open-source RISC-V core;
CoreMark/Joule almost never is, because the energy half needs a hardened
netlist, an activity capture and a power engine, and each can produce a
plausible number that is not a measurement. We build the chain in a
reproducible flow -- CoreMark ELF, RTL simulation, CRC gate, synthesis, global
route, gate-level simulation, SAIF over one hot iteration, `report_power` --
and screen at global route, so a point costs minutes. Four cores on ASAP7:
SERV (0.0243 CoreMark/MHz), picorv32 (0.5531), ibex (2.4543) and VeeR EH1
(4.7979), nearly two hundred times apart in performance per clock.

**Every point is measured at one boundary -- core + L1 -- and the boundary is
verified, not asserted.** Cores with no cache are hardened with the
tightly-coupled memory they run from; each wrapper counts every transfer
leaving the hardened block, and for all four one hot iteration sends
**zero**. Closing that boundary is the study's largest result: it costs the
cacheless cores **between 3.3x and 5.1x** of their CoreMark/Joule at unchanged
CoreMark/MHz, and compresses the ordering -- ibex reads 13.45x better than
VeeR with its memory outside the measurement and 4.08x inside. A
CoreMark/Joule quoted for a small core without saying whether its memory was
measured is uninterpretable at roughly an order of magnitude.

**The methodological result is negative and checkable.** OpenSTA does not
fail on an unannotated pin; it estimates one, and the report cannot tell. We
enumerate every pin, classify every one the SAIF did not reach, and sweep the
default activity across its range. The SAIF annotates **100 % of pins** on the
three cacheless cores (28,264 / 53,694 / 81,165); for all four the SAIF-driven
total is bit-identical at ten significant figures across the sweep, while the
vectorless total moves 21--144 %. The estimator contributes nothing. That is
not the SAIF determining everything: a clock-network pin takes
$2/\mathrm{period}$ from the SDC whether or not the SAIF reached it ([§2.2](#22-what-opensta-does-with-an-unannotated-pin)),
and clock plus the clock-pin-driven share of sequential and macro internal
power is most of every point ([§4.7](#47-where-the-power-goes)) -- which is why a SAIF time base wrong by
2.14x moved one core's total by 2.9 % ([§6.1](#61-the-saifs-time-base-has-to-be-the-sdc-period)). Neither source is an estimate.

**The shape is reported with its diagnosis.** The three cacheless cores lie
near a line in log--log axes; extrapolating it to VeeR overpredicts its
efficiency by **7.88x** with every memory inside the boundary and by **15.2x**
with the cacheless memories outside ([§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model), [§4.2](#42-what-the-boundary-costs)). The boundary was most of the
disagreement, and the line that remains is the memory model's:
**CoreMark/Joule is not yet a discriminating axis among cores of this class.**

The limitations are ranked below and bounded in [§5](#5-threats-to-validity); the largest is that
every memory is a fitted view, not a characterised one. [§4.8](#48-cross-checks-against-the-nearest-published-studies) checks the
numbers against the three nearest published studies and reports the one
disagreement that stays unexplained.

## Limitations, ranked

In the order they move the numbers; each is bounded in [§5](#5-threats-to-validity).

1. The memory model is fitted, not characterised: every SRAM is
   `tools/memory_macro_scaler`'s view, whose energy and leakage follow the
   memory's shape but whose fit its own documentation calls a first-order
   anchor, and memory is 66 to 78 % of every point ([§5.1](#51-the-memory-model-and-the-memory-this-study-chose), [§8.7](#87-a-memory-model-that-knows-its-size)).
2. Every point has a five-seed error bar; the largest 2σ is 1.5 % of its point,
   and a gap inside that did not resolve ([§5.11](#511-five-placement-seeds-behind-every-point)).
3. The corner is the kit's best case: fast process, high voltage ([§5.6](#56-the-corner-is-asap7s-best-case-not-its-typical)).
4. The simulation is zero-delay and carries no glitch power ([§5.2](#52-zero-delay-simulation-carries-no-glitch-power)). [§2.4](#24-when-glitch-power-is-worth-measuring-and-when-it-is-premature)
   argues that is the right depth for a screen, [§5.3](#53-glitch-power-in-the-multiplier-measured) spot-checks the unit
   most exposed, and [§5.4](#54-a-second-core-and-where-that-stops) records the unfinished second core; the
   differential bias between cores is still an argument, not a number.
5. Parasitics are estimated at global route, not extracted ([§5.5](#55-estimated-not-extracted-parasitics--one-point-measured)).
6. Every frequency is a derived period from two tuner passes on one
   floorplan; the second pass moved ibex 14 ps and VeeR 2 ps, and the
   floorplans are not re-derived on the new memory views ([§5.7](#57-frequency-and-what-deriving-it-changed), [§8.4](#84-a-second-period-pass)).
7. The kit is predictive. No absolute Watt here is a silicon Watt ([§5.8](#58-a-predictive-kit-not-a-foundry-pdk)).

One cross-check comes back implausible and unexplained: ibex's
post-synthesis energy per iteration at 7 nm sits between two published 65 nm
figures for the same core at the same stage, where node scaling puts it well
below both ([§4.8](#48-cross-checks-against-the-nearest-published-studies)).

## 1. Introduction

![Figure 1](coremark_joule.png)

**Figure 1.** CoreMark/Joule against CoreMark/MHz, both axes logarithmic.
Blue: measured here on ASAP7 at global route, activity from one hot CoreMark
iteration; error bars are 2σ over five placement seeds ([§5.11](#511-five-placement-seeds-behind-every-point)). Red: a
published GF 22 FDX series, derived from another paper's numbers and drawn
apart because it is not like-for-like ([§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not)). Two shaded regions place the
cores against commodity silicon, as regions rather than markers: three parts
stand in for a class, and a marker would invite reading silicon on N7,
Intel 7 and N4 against a predictive 7 nm kit as one trend.

The purple region is where **one x86 or Arm core** sits, measured rather than
apportioned: Appendix A reads wall-plug power while CoreMark runs on *n* cores
and attributes energy by the slope of watts against active cores, which
cancels the platform's fixed draw and any meter offset. Its boundary -- a core
and its private caches -- is the one this study hardens, reached another way.
Three parts: a Threadripper 3970X (Zen 2), a Xeon 8558U (Emerald Rapids) and
an X Elite X1E78100 (Oryon), spanning 7.4 to 12.5 CoreMark/MHz and 4,700 to
11,520 CoreMark/Joule. Not corrected: those are shipping parts on real nodes,
and these four are a predictive kit at its best-case corner ([§5.8](#58-a-predictive-kit-not-a-foundry-pdk), [§5.6](#56-the-corner-is-asap7s-best-case-not-its-typical)) with
estimated parasitics ([§5.5](#55-estimated-not-extracted-parasitics--one-point-measured)) and no glitch power ([§5.2](#52-zero-delay-simulation-carries-no-glitch-power)). The screen is the
optimistic side of the comparison.

The green region is an observation, not a target: at that performance per
clock, nothing in this study, in Appendix A or in the literature reaches that
efficiency. Its floor is the top of the measured band and its edges that
class's range, so it marks the gap a design would have to cross to be an
advance rather than a better point on a known curve.

<!-- table1 -->
| core | ISA | CoreMark/MHz | cycles/iter | f (MHz) | P (SAIF) | dynamic | leakage | CoreMark/Joule | memory inside the boundary | 2σ over seeds |
|---|---|---|---|---|---|---|---|---|---|---|
| SERV | rv32i | 0.0243 | 41,202,900 | 2283.1 | 54.7 mW | 54.7 mW | 0.00 mW | 1,013 | 32 kB instruction memory and 8 kB data memory | ±2 (5) |
| picorv32 | rv32im | 0.5531 | 1,807,889 | 2141.3 | 56.6 mW | 56.6 mW | 0.00 mW | 20,926 | 32 kB instruction memory and 8 kB data memory | ±105 (5) |
| ibex | rv32imc | 2.4543 | 407,448 | 771.6 | 22.5 mW | 22.5 mW | 0.00 mW | 84,167 | 32 kB instruction memory and 8 kB data memory | ±333 (5) |
| VeeR EH1 | rv32imc | 4.7979 | 208,425 | 627.7 | 146.0 mW | 145.8 mW | 0.02 mW | 20,629 | 16 kB instruction cache and 64 kB DCCM | ±317 (5) |
<!-- /table1 -->

**Table 1.** The four measured points, all at [§3.1](#31-the-measurement-boundary)'s boundary -- core + L1,
or the tightly-coupled memory that stands in for one -- and each verified to
send zero transfers outside the hardened block during the iteration measured.
[§4.2](#42-what-the-boundary-costs) reports what closing that boundary cost: between 3.3x and 5.1x of
CoreMark/Joule on the three cores that had been measured without their
memories, at unchanged CoreMark/MHz. The last column is what each tile
hardens; for the cacheless cores it is this study's choice, not the core's
([§5.1](#51-the-memory-model-and-the-memory-this-study-chose)).

The question is the shape of the curve: does a wider machine buy back its own
energy? For large cores the literature answers with signoff tools [5, 6]; for
small cores it mostly does not, because the energy half is easy to get wrong
in ways that do not look like errors. A SAIF applied to a netlist it was not
captured against does not fail -- OpenSTA uses default activity for the nets
that did not match. A netlist whose memory macro has no behavioural model
does not report low memory power -- it computes the wrong answer, and only a
functional check notices. And a report whose pins are mostly unannotated is
not labelled an estimate; it is labelled "Total".

Every core, the benchmark, the toolchain, the PDK and the EDA flow are
fetched from their upstreams at pinned commits and built by one command: no
vendored RTL, no licensed tool, no number a reader cannot re-take. A core
joins as a `config.mk`, a bus adapter to the two-word platform of [§3.2](#32-the-chain) and a
`units.json` ([§10.3](#103-adding-your-own-core) has the list), and inherits the annotation audit of [§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator)
and every gate in [§10.1](#101-re-running-the-study) unchanged.

The contributions:

1. A reproducible CoreMark → CoreMark/Joule chain in an open flow, screened
   at global route ([§3.2](#32-the-chain)).
2. A performance metric that removes CoreMark's ten-second run rule from a
   problem no simulator can satisfy, with a test that its premise cannot
   rot ([§3.3](#33-performance-a-differential-iteration)).
3. An activity window anchored on an observable event in the benchmark, not
   an instrumented one ([§3.4](#34-activity-one-hot-iteration)).
4. **A complete, automated account that OpenSTA's probabilistic activity
   model does not enter the result** -- enumeration, classification, and a
   measured bound ([§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator), [§4.3](#43-annotation-completeness-and-the-estimator-bound)).
5. The boundary the study intends, the gap between it and these four points,
   and the direction of every remaining bias ([§5](#5-threats-to-validity)).

## 2. Background

### 2.1 Vectorless and vector-driven power estimation

Dynamic power is set by how often each node switches, and two families of
technique supply that [3]. *Vectorless* estimation propagates signal
probabilities and transition densities from the primary inputs through each
gate's Boolean function: cheap, stimulus-free, and blind to the correlation
reconvergent fanout creates. *Vector-driven* estimation reads the activity
from a simulation of the workload, and is the basis of signoff power [8]. A
report produced either way looks the same; the number is a Watt.

### 2.2 What OpenSTA does with an unannotated pin

Read from the pinned OpenSTA [9] (`power/Power.cc`, `power/SaifReader.cc` at
`65bd9df5`), because [§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator) rests on it:

- `read_saif` matches each SAIF `NET` name against a **pin** of the enclosing
  instance and records it with origin `saif`; hierarchical, internal and
  power/ground pins are skipped. It prints `Annotated N pin activities.`
- `seedActivities()` seeds the *levelization roots* -- top-level input ports
  and tie-cell outputs -- with their annotated activity if any, otherwise with
  `input_activity_`, default `0.1 / min_clock_period` at duty 0.5. This is the
  only path by which a density OpenSTA invented enters the design.
- `PropActivityVisitor::visit()` prefers an annotated activity over a
  propagated one, so a fully annotated design never propagates.
- Everything else is propagated: a BDD evaluation of the driving cell's
  function over its inputs' densities and duties -- Najm's transition density
  [3, 4], blind to reconvergent-fanout correlation.
- A clock-network pin bypasses both paths and takes $2/\mathrm{period}$ at the
  clock's duty from the SDC. Not an estimate -- but see the next item.
- **Every density, annotated or not, is then clamped to `1/slew`**
  (`PropActivityVisitor::setActivityCheck`) -- the delay calculator's slew,
  not the SDC's `set_clock_transition`. With a clock tree the clamp is far
  above $2/\mathrm{period}$ and does nothing, which [§4.8](#48-cross-checks-against-the-nearest-published-studies) measures at global
  route. On a synthesis netlist where one port drives two thousand flop clock
  pins unbuffered, the clock slew is nanoseconds and the flops are charged a
  third of the edges the SDC says they see.

`report_activity_annotation` enumerates annotated and unannotated pins; it
exists because this question was asked of it [10].

### 2.3 Why CoreMark/Joule falls as CoreMark/second rises

The two axes of Figure 1 are coupled. From

$$\mathrm{CoreMark/Joule} = \frac{\mathrm{CoreMark/MHz}\cdot f}{P}, \qquad P = P_\mathrm{dyn} + P_\mathrm{leak}$$

$$P_\mathrm{dyn} = \alpha\, C\, V^2 f, \qquad P_\mathrm{leak} = V\, I_\mathrm{leak}(V, T)$$

**at fixed voltage and microarchitecture, energy per unit of work does not
depend on frequency**: the $f$ cancels, and $\mathrm{CoreMark/Joule} =
\mathrm{CoreMark/MHz} / (\alpha C V^2)$. Twice the speed is twice the power for
half the time, which is why "run slower to save energy" is wrong as stated.
**Leakage pushes the same way**: leakage energy per operation is
$P_\mathrm{leak} / (\mathrm{CoreMark/MHz}\cdot f)$ and falls as $1/f$ -- the
race-to-idle argument, dominant for a small core at a low frequency. No point
here is in that regime: SERV is the smallest core and the fastest clock, and
its leakage rounds to zero on the scaler's anchor ([§5.1](#51-the-memory-model-and-the-memory-this-study-chose)).

So if frequency were free, higher would be better. What it costs is where the
efficiency goes.

**Bought with voltage:** $f_\mathrm{max}$ rises roughly linearly with $V$ while
$E_\mathrm{dyn}$ per operation rises as $V^2$, so energy per operation scales
as $f^2$ and CoreMark/Joule as $1/f^2$. Reaching 3 GHz this way from ibex's
772 MHz needs 3.9× the supply, which at 7 nm is a breakdown. ASAP7's whole
headroom is 0.70 V to 0.77 V -- about 10 %, worth perhaps 10–20 % of frequency
for 21 % more dynamic energy per operation.

**Bought with microarchitecture:** shorter logic between registers closes at a
higher clock, at the cost of more pipeline stages, flops, clock tree and
upsized cells -- every one raising $C$ per operation at constant $V$. That is
how 3–5 GHz parts are made, and why a datacentre core is not a small core
clocked up but a different design with structurally higher energy per
instruction.

So **the interesting cores are not reachable by turning a knob on the cores
here**: a 3 GHz point is a different microarchitecture, and [§8.1](#81-cores-after-the-first-four)'s roadmap is
the way to one. What these cores can show is their own knee -- [§8.5](#85-the-pareto-curve)'s Pareto
sweep, which pushes the period until the tools upsize wholesale and draws the
cost of speed as a curve. It also bears on [§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model): the three cacheless cores sit
span 3× in frequency at one voltage, so the term that would separate them --
voltage -- has not been exercised.

### 2.4 When glitch power is worth measuring, and when it is premature

A glitch is a transition the logic function did not ask for: a node settles
only after its inputs finish arriving, and every intermediate value charged a
real capacitance. It exists only where two signals arrive at different times,
which RTL does not express -- the quantity belongs to an implementation, not
to a description.

**It is large and not a constant.** Shum and Anderson measure it the way [§5.3](#53-glitch-power-in-the-multiplier-measured)
does, comparing "a functional (zero-delay) and timing simulation of each
circuit", and report glitch at **5.8 % to 45.4 % of dynamic power across
their circuits, averaging 26.0 %** [24]. That is FPGA, so the absolute numbers
do not transfer, but the spread does: a factor of eight between designs on one
fabric by one method.

**It moves when the implementation moves, RTL held fixed.** [§5.3](#53-glitch-power-in-the-multiplier-measured)'s window was
run twice on ibex's multiplier -- same RTL, stimulus and cycles -- across a
re-baseline that changed the clock period, the memory model and the placement
seed. Glitch over the window went from +27.2 % to +15.6 %, on the busy cycles
from +47.4 % to +5.3 %, back to back from +35.1 % to +0.2 %. A figure that
moves ninefold when the floorplan moves cannot choose between architectures.

**So the remedies belong to an implementation.** Quieting glitch means holding
inputs still when a unit idles, or balancing arrival times into a converging
cone; standard low-power methodology inserts operand isolation and clock
gating at synthesis [26]. Operand isolation has register-transfer content and
has been automated at RT level since [25], so a public core *can* carry it --
ibex's `RV32MFast` does not, which [§5.3](#53-glitch-power-in-the-multiplier-measured) measured: its operands change on every
idle cycle. What public RTL reliably lacks is the flow output -- the
balancing, buffering and isolation a tool inserted against one library at one
corner -- and there is nothing general to upstream in an answer to one
implementation's arrival times.

**Shift-left estimation does not contradict this.** Vendors market glitch
power estimation at RTL [27, 28], but the published descriptions take the
implemented design's timing as an input; what moves earlier is the cost of
measuring, not the need for an implementation -- "true glitch detection
required gate-level data" [28]. The parallel is the clock period, equally an
implementation property, which this study derives by running the flow ([§5.7](#57-frequency-and-what-deriving-it-changed))
-- and which caught one core published at a period it misses by 74 ps.

**For a screening study**, automated glitch discovery is worth what the
uncertainty about *where* the glitch is is worth, and for a CPU that is low:
the literature nominates arithmetic units [7, 8], so this study went at the
multiplier. Shift-left tooling earns its cost on a novel accelerator with no
such body of knowledge. Prior knowledge picked the right unit and the wrong
mechanism -- the expected imbalance in the partial-product tree during
multiplication, against a measured +0.2 % back to back and +20.8 % idle
([§5.3](#53-glitch-power-in-the-multiplier-measured)) -- so the remedy is operand gating, not tree balancing. Domain
knowledge says where to look, not what is there.

This study therefore reports vector-driven activity from a zero-delay
simulation, states the bias and its direction ([§5.2](#52-zero-delay-simulation-carries-no-glitch-power)), and spot-checks one unit
([§5.3](#53-glitch-power-in-the-multiplier-measured)). A full glitch campaign, like the extracted-parasitics flow of [§5.5](#55-estimated-not-extracted-parasitics--one-point-measured) and
[§8.6](#86-extract-the-parasitics-on-every-point-not-one), becomes worth its cost when the RTL is frozen and one implementation is
committed to.

## 3. Method

### 3.1 The measurement boundary

The designs span three decades of CoreMark/MHz and are not variants of one
another: a bit-serial state machine at 41 million cycles per iteration and a
superscalar tile at a few hundred thousand share no knob that turns one into
the other. A like-for-like comparison has to be *constructed* from the
definition of what is measured. **The measured object is the core + L1 -- and
not whatever surrounds it.** L2, interconnect, peripherals and debug are
outside the boundary on every point, however much of them a repository ships;
what is compared is the same *kind* of thing each time.

Above about 5 CoreMark/MHz the core + L1 cannot be told apart anyway: the
caches sit inside the tile on its clock and floorplan, and neither the
repositories nor the literature reports the core without them. The smallest
cores have no caches; they have a small memory the hot loop runs out of, and
**that memory is measured**, hardened with the core. Same rule, same object: a
cacheless core is not credited with a free, perfect memory because its memory
is small enough to overlook. One rule for every point: **the core, its L1 or
the tightly-coupled memory that stands in for one, and nothing beyond.**

None of picorv32, SERV or ibex ships such a memory -- their testbenches use
simulation arrays -- so this study supplies one: a 32 kB instruction memory
and an 8 kB data memory at separate addresses, hardened inside each tile
(`rtl/cmj_progmem.sv`, `sw/port/link.ld`). Two memories because that is what
VeeR already is (an ICCM and a DCCM), and because disjoint memories let a
fetch and a load proceed in one cycle with no arbiter of this study's
invention in the measured path. The image is copied in from external memory
by the C runtime before the first iteration and never read from outside again.

**The boundary is checked.** Each wrapper counts every transfer crossing it,
instruction side and data side, and takes the same two-minus-three-iteration
difference the cycle count uses ([§3.3](#33-performance-a-differential-iteration)). For all four cores that difference is
**zero**: the iteration the SAIF is captured over sends nothing outside the
hardened block. [§4.2](#42-what-the-boundary-costs) reports what enforcing that cost.

### 3.2 The chain

    ELF → RTL simulation → CRC gate → synthesis → global route
        → netlist → gate-level simulation → SAIF (one hot iteration)
        → report_power

| path | what |
|---|---|
| `sw/port/` | the CoreMark port layer; CoreMark's sources stay byte-unmodified ([§11](#11-licensing)) |
| `sw/` | ELF builds, one per ISA and iteration count |
| `rtl/cmj_<core>.v` | each core's configuration, frozen, shared by the simulator and the flow |
| `rtl/cmj_progmem.sv` | the two tightly-coupled memories hardened inside each cacheless tile |
| `rtl/cm_soc_<core>.v` | simulation wrapper: external memory, sim-control device, boundary traffic counters |
| `sim/` | the Verilator harness and the measurement targets |
| `designs/asap7/<core>/` | `config.mk`, constraints, `units.json`, `pin_policy.json` |
| `scripts/` | parsers and checks, each with a unit test |

Two memory-mapped words are the whole bare-metal contract, and all four cores
see the same two: a byte at `0x1000_0000` is one character of stdout, a 1 at
`0x1000_0008` stops the simulation. That is why one C runtime, one linker
script and one CoreMark port serve cores whose buses, privilege models and
CSRs have nothing in common. Cycles are counted in the harness, not read from
a CSR: ibex has `mcycle`, picorv32 has no machine-mode CSRs, SERV's are a
build option. The image carries both reset conventions, `0x000` for a core
that starts at its reset address and `0x180` for ibex, which fetches from
`boot_addr_i + 0x80`.

**The netlist the power is reported on is the netlist that was simulated**,
written from the stage's own ODB by `flow/write_netlist.tcl`. A SAIF applied
to another stage leaves nets unmatched, and [§2.2](#22-what-opensta-does-with-an-unannotated-pin) says what OpenSTA does with
those.

**Correctness is gated on the gate-level netlist.** The gate is CoreMark's
three printed CRCs -- not its error count or exit status, because the port
stubs the timer and CoreMark reports "must execute for at least 10 secs" on
every run. A converted memory is blackboxed at synthesis so the Liberty view
wins, and a blackbox stores nothing: run the netlist without a behavioural
model and the register file holds nothing, so CoreMark fails its CRCs rather
than quietly reporting low memory power. `memories.json` records
`behavioral_model: {file, module}` for that reason.

### 3.3 Performance: a differential iteration

$$\mathrm{CoreMark/MHz} = \frac{10^6}{\mathrm{cycles}_3 - \mathrm{cycles}_2}$$

Two ELFs per configuration, at `ITERATIONS=2` and `ITERATIONS=3`; the
difference is one CoreMark iteration, and it cancels reset, `.bss` zeroing,
data init, the CRC checks and the printed report. It also removes CoreMark's
ten-second run rule from a problem no simulated core can satisfy. The two ELFs
differ by one word of `.data`, and
`//test/coremark_joule/sw:iteration_delta_test` asserts exactly that.

**These are not reportable CoreMark scores** [1]: a three-iteration run does
not satisfy the run rules. The numbers compare within this study, not against
published figures.

### 3.4 Activity: one hot iteration

Activity has to come from the part of the run that is the benchmark: startup,
data init and the first iteration run cold, and the report is `ee_printf`. The
window is **one iteration, the last one** -- the quantity the cycle count
uses, running hot; the papers compared against also select a warm window [5].

The anchor is observable: CoreMark prints nothing until its report, so the
cycle of the first character out is where the loop ended. With `D` cycles per
iteration the last iteration is `[first_output - D, first_output]`, and the
harness records `first_output` beside the cycle count; nothing in the
benchmark is modified. Cycle behaviour is identical between RTL and gate-level
simulation, so the window comes from the cheap RTL run; on picorv32 the start
computed from `first_output - D` equals `cycles_2 - report_cost` exactly.

Two capture mistakes produce a plausible SAIF rather than an error. Dumping on
a time base relative to the window makes `DURATION` span the whole prologue
and divides every toggle rate by however far in the window starts. Dumping at
one clock phase catches the clock at the same level every cycle and records a
clock that never toggles. A correct capture shows `clk` with `TC` equal to
twice the window's cycle count and a duration of one iteration.

### 3.5 Annotation completeness, and the bound on the estimator

[§2.2](#22-what-opensta-does-with-an-unannotated-pin) establishes that OpenSTA silently estimates an unannotated pin, so the
claim the study needs is not "we read a SAIF" but "the estimator contributed
nothing", made two ways.

**The accounting.** `flow/activity_audit.tcl` loads the ODB the power is
reported on, reads the same SAIF, and emits OpenSTA's own annotated and
unannotated listings (`report_activity_annotation -report_annotated
-report_unannotated`) beside the ODB's view of every pin -- master type, port
direction, signal type, net. `scripts/classify_pins.py` puts each unannotated
pin in exactly one class with a declared policy:

| class | policy | why |
|---|---|---|
| `clock_network` | benign | OpenSTA takes $2/\mathrm{period}$ from the SDC exactly; unannotated is the correct state |
| `tied_constant` | benign | driven by a tie cell or wired to a rail: no switching |
| `unconnected` | benign | connected to no net |
| `power_ground` | benign | excluded from the power calculation by construction |
| `scan_test` | benign, with a written reason | tied off for functional operation |
| `top_port` (input) | **fatal** | a levelization root: where a default activity enters and spreads |
| `macro_pin` | **fatal** | an unannotated SRAM is memory energy invented rather than measured |
| `internal_cell_pin` | **fatal** above the design's declared budget | the catch-all, and the class the study exists to empty |
| `unmatched` | **fatal** | OpenSTA named a pin the ODB table does not have: a join failure hiding whatever the pin was |

Budgets and waivers live in `designs/asap7/<core>/pin_policy.json`, each with
a written reason. The `internal_cell_pin` budget is zero on every design. The
`unmatched` budget is a fraction, not a count, because the fraction is what is
worth reporting and driving down; three designs declare zero, and VeeR
declares 1.1 % against a measured **1.0073 %** for the reason [§4.3](#43-annotation-completeness-and-the-estimator-bound) gives.

That is tolerable rather than a loophole because the sweep does not care how a
root came to be unannotated: it varies the default seeded into *every*
unannotated root at once and measures whether the answer moves, and a non-root
pin is reached through the propagation that default feeds. The one class it
cannot reach is `clock_network`, which bypasses both paths for
$2/\mathrm{period}$ ([§2.2](#22-what-opensta-does-with-an-unannotated-pin)) -- the class whose unannotated state is already
correct. The classification says what was left out; the sweep says what it was
worth wherever the estimator could have spoken.

OpenSTA's summary line is deliberately not parsed.
`Power::reportActivityAnnotation` computes `unannotated` as `pinCount()` minus
the annotated map's size, over two pin sets that filter power/ground pins
differently, in unsigned arithmetic: it can undercount, and it underflows when
annotation reaches pins `pinCount()` does not count. The enumerations are the
ground truth, and `classify_pins_test.py` pins that.

**The bound.** `set_power_activity -input` sets the density seeded into every
unannotated root -- the only path by which an invented number enters ([§2.2](#22-what-opensta-does-with-an-unannotated-pin)).
`flow/activity_sweep.tcl` sweeps it from 0.0 (a root never toggles) through
OpenSTA's default 0.1 to 2.0 (as often as the clock) and reports power at each
point. `-global` is **not** used: it short-circuits `Power::findActivity` and
overrides annotated pins too, which would pass the test by destroying what it
measures. Two arms, because a flat line is evidence only if the knob works:
`vectorless` runs before the SAIF is read and is the positive control, `saif`
runs after. Power is reported with `-digits 10`, because at the default
resolution a flat arm and a small one look alike.

### 3.6 Corner, parasitics and stage

Power is reported at global route with parasitics from `estimate_parasitics
-global_routing`, not an extracted SPEF -- what makes a point cost minutes.
[§5.5](#55-estimated-not-extracted-parasitics--one-point-measured) measures the cost on one core: 10.9 % on the switching term, 2.05 % on
the total, with detailed route changing nothing else and congestion at zero.

The corner is ORFS's ASAP7 default, `CORNER = BC`: **RVT, FF process, 0.77 V,
25 °C**, NLDM -- the best case, not the typical one ([§5.6](#56-the-corner-is-asap7s-best-case-not-its-typical)). The Liberty files
actually read are recorded per design in `<name>_design.json` by the audit,
so the corner is machine-checked against the run.

**One flow setting is turned off for speed, and exactly one.** bazel-orfs's
`FAST_SETTINGS` dict (in `//test:BUILD`, copied in `examples/` and
`test/smoketest/`) disables the expensive parts of the flow for CI. Right for
a smoke test, wrong for a measurement, because most of its entries **change
the netlist**:

| setting | what it changes | usable here |
|---|---|---|
| `GPL_TIMING_DRIVEN=0`, `GPL_ROUTABILITY_DRIVEN=0` | placement stops optimising timing and congestion | no |
| `SKIP_CTS_REPAIR_TIMING=1` | no buffer insertion, sizing or VT swap after CTS | no |
| `SKIP_INCREMENTAL_REPAIR=1` | no repair at global route | no |
| `REMOVE_ABC_BUFFERS=1` | strips synthesis buffers instead of repairing | no |
| `FILL_CELLS=""`, `TAPCELL_TCL=""` | no fillers or taps — area, density and leakage | no |
| `PWR_NETS_VOLTAGES=""`, `GND_NETS_VOLTAGES=""` | skips IR-drop at `final` | moot, this study stops at global route |
| **`SKIP_REPORT_METRICS=1`** | **reporting only** | **yes** |

Every design takes the last line and refuses the rest. Nothing in the study
reads ORFS's metrics: power comes from `flow/power_grt.tcl`, the derived
period from `flow/period_probe.tcl`, and the floorplan derivation takes WNS
from `sta::worst_slack_cmd` directly. `FAST_SETTINGS`' own documentation does
not mark which entries touch the netlist, which is why it is spelled out here.

### 3.7 Functional-unit attribution

Each design sets `SYNTH_HIERARCHICAL=1` with an explicit `SYNTH_KEEP_MODULES`
and runs OpenROAD with `OPENROAD_HIERARCHICAL=1`, so module boundaries survive
to global route and `report_power -saif -instances` has something to attribute
to. `units.json` maps each kept module to an architectural unit -- fetch,
decode, execute, load/store, register file, CSR -- and `synth.tcl` errors on a
kept-module name absent from the elaborated design, so an upstream rename
fails the build instead of moving a unit into "other".

How well this works is a property of the RTL:

| core | RTL structure | attribution delivered |
|---|---|---|
| SERV | excellent — one module per architectural function | **none** — its kept modules are parameterized and do not reach the ODB ([§6.2](#62-attribution-does-not-survive-parameterized-modules)) |
| ibex | excellent — the pipeline stages are modules | yes |
| picorv32 | **poor** — `picorv32.v` defines eight modules and the CPU is one of them; decode, execute, the ALU and control are all inline | partial — `picorv32_pcpi_mul` and `picorv32_pcpi_div` survive intact, the rest is waived in `units.json` |

picorv32 carries a written waiver in its `units.json` rather than a silent
shortfall; "this core cannot be attributed" is itself a result about
open-source RTL. [§6.2](#62-attribution-does-not-survive-parameterized-modules) covers the mechanical gap.

### 3.8 What sets a CPU core's frequency, and what the SDC must therefore say

A CPU core is not a macro in a datapath, and constraining it as one produces a
netlist optimised for a situation that never arises. Every frequency and watt
in [§4](#4-results) depends on the model here.

**Only register-to-register paths can fail timing closure.** Input-to-register,
register-to-output and input-to-output are *optimisation targets* -- numbers
that tell the tools how hard to work, not conditions for correctness. That is
the argument ASAP7's own `$PLATFORM_DIR/constraints.sdc` makes, and for a CPU
it is stronger than for a macro: a core is attached to a clock-crossing
bridge, a bus register or a GPIO pad, each of which *terminates* the path.
There is no correct `set_input_delay` for a CPU's bus port, because the number
it wants is the time already spent upstream within the same cycle, and
upstream of a CPU's pin there is a flop.

So the model is **a register immediately outside every port**, and the
consequences follow:

- An input-to-register path shares its cycle with the outside register's
  clock-to-q and the far-end setup; the core's share is 0.8 of the period,
  ORFS's figure for this core on this PDK, and likewise register-to-output.
- A path straight through the core has a register at both ends outside, so
  it gets 0.6.
- Nothing else about the outside world is needed, in particular not the
  clock tree: `set_input_delay` is measured from the clock insertion point and
  cannot be written down before a clock tree exists, while
  `set_max_delay -ignore_clock_latency` has no such problem. The platform
  file uses it and this study follows.
- **No hold cells are inserted on IO paths**, because `set_input_delay` is
  what would have demanded them. On VeeR's six hundred ports that is area and
  leakage the core's real environment does not impose.

**The minimum clock period is therefore the reg2reg one, taken from the
platform's own path group.** `$PLATFORM_DIR/constraints.sdc` partitions the
design with four `group_path` commands -- `in2reg`, `reg2out`, `reg2reg`,
`in2out` -- and `flow/period_probe.tcl` asks for `reg2reg`'s worst slack by
name. The overall WNS is not used: it can be set by an in2reg or reg2out path
whose budget is the 0.8/0.8/0.6 fraction *this study chose* to stand in for
the outside register, so a frequency derived from it would be limited by our
own assumption. The group is asked for by name rather than re-derived with
`-from [all_registers] -to [all_registers]`, which would be a second
definition free to drift from the file that constrains the design; the probe
also reports the group's path count, because a group that matches nothing and
a group with zero slack both read zero. `auto_period` ([§5.7](#57-frequency-and-what-deriving-it-changed)) drives the same
thing: push the period until reg2reg slack goes slightly negative and ignore
the other three groups, which measure an environment this study does not
model. The model covers the small cores too: once [§3.1](#31-the-measurement-boundary)'s boundary is met, the
memory a small core runs out of is inside it, so its remaining ports are
GPIO-like -- fast enough to fit the budget or registered on the other side.

**Left unsaid, this costs.** The platform's `set_max_delay` default when a
design supplies no budget is **80 ps**, which its own comment calls right for
"a small macro on ASAP7". At a 1000 ps period that is a twelvefold
over-constraint on every path touching a port, and an optimiser given an
impossible target upsizes and buffers, and that power is reported as the
core's. Every design here sets the budget explicitly (see each
`constraints.sdc`); [§6.3](#63-the-io-budget-and-what-the-platform-default-cost) records what the default was worth.

## 4. Results

### 4.1 The four cores

Table 1. Across a factor of 198 in CoreMark/MHz, CoreMark/Joule spans a factor of 83:
SERV's serialism costs it 41 million cycles per iteration, and paying for a
40 kB memory over every one of them dominates its Joule. Every point meets the
boundary and is verified to send zero transfers outside it; [§4.2](#42-what-the-boundary-costs) is what that
cost.

Two cautions. Every memory is a fitted view, and 66 to 78 % of each point's
power comes from a model whose fit is a first-order anchor ([§5.1](#51-the-memory-model-and-the-memory-this-study-chose)). And
CoreMark/Joule is not a discriminating axis across these four: [§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model) shows it
within 1.22x of proportional to CoreMark/MHz over the three cacheless cores,
for reasons that belong to the memory model rather than to the designs.

### 4.2 What the boundary costs

A core measured without the memory it runs out of is credited with a free,
perfect memory: every fetch and load at zero area and energy. The error runs
one way, against the wide machines -- a design that spends area and energy on
an L1 is charged for it and credited with the speed; a design with none is
charged for neither. picorv32 and SERV have no caches and ibex is configured
`ICache=0`, so for all three the entire memory system is that memory, and
SERV's 41 million cycles per iteration are 41 million cycles of paying for it,
because the scaler's Liberty charges a macro on every clock edge whatever the
enable does ([§4.7](#47-where-the-power-goes)).

**The three cacheless cores harden the memory they run out of.** Each tile --
`cmj_serv`, `cmj_picorv32`, `cmj_ibex` -- holds the core plus a 32 kB
instruction memory and an 8 kB data memory, SRAMs of `rtl/cmj_sram_models.sv`
with LEF and Liberty from `tools/memory_macro_scaler` ([§8.7](#87-a-memory-model-that-knows-its-size);
`rtl/cmj_progmem.sv` wires them to the core's bus), placed and routed with the
core and inside what `report_power` totals.

<!-- table8 -->
| core | CoreMark/MHz | CoreMark/Joule, core-only | CoreMark/Joule, core + L1 | factor |
|---|---|---|---|---|
| ibex | 2.4543 | 277,510 | **84,167** | 3.30x |
| picorv32 | 0.5531 | 86,024 | **20,926** | 4.11x |
| SERV | 0.0243 | 5,190 | **1,013** | 5.12x |
| VeeR EH1 | 4.7979 | 20,629 | 20,629 | 1.00x (already met) |
<!-- /table8 -->

**Table 2.** Each core measured with its memory outside the boundary
(core-only) and inside it (core + L1). CoreMark/MHz is identical to every
digit -- the memory's position changes no cycle -- so the whole difference is
on the energy axis.

**The correction is large**: between 3.3x and 5.1x. The core-only column is
from the earlier builds at chosen periods, the core + L1 column at the derived
ones ([§5.7](#57-frequency-and-what-deriving-it-changed)), which moved it by at most 3.5 %. A CoreMark/Joule quoted for a
small core without saying whether its memory was measured is uninterpretable
at roughly an order of magnitude -- wider than the gap between most cores
anyone would compare.

**It shrinks as the core grows**: 5.12x, 4.11x, 3.30x in order of
CoreMark/MHz. The memory is the same in all three tiles, so a larger core
amortises a fixed overhead over more work per cycle -- the mechanism by which
the core-only boundary flattered small cores, and why the straight line of
[§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model) existed.

**The ordering compresses.** ibex looked 13.45x better than VeeR
core-only; at the same boundary it is 4.08x better at 0.51x the performance
per clock. The conclusion the old numbers invited -- that minimal cores
dominate the energy metric -- does not survive.

**Verified, not asserted.** Each wrapper counts every transfer crossing the
boundary, instruction side and data side, and `scripts/bus_probe.py` takes
the two-minus-three-iteration difference. All four cores send **zero
transfers per hot iteration** on every external counter: the boot copy is
51k--70k fetches and 7k--8.5k data accesses, and the hot iteration adds none.

    bazelisk build //test/coremark_joule/sim:serv_rv32i_bus_traffic \
                   //test/coremark_joule/sim:picorv32_rv32im_bus_traffic \
                   //test/coremark_joule/sim:ibex_rv32imc_bus_traffic \
                   //test/coremark_joule/sim:veer_rv32imc_bus_traffic

**Above about 5 CoreMark/MHz the boundary stops being a caveat and becomes the
measurement**, which is why it had to be settled first. Those cores arrive as
tiles or SoCs with L1s, an L2, an interconnect and peripherals. Harden what
the repository hands you and the uncore swamps the core; harden less than the
L1 and misses are served by a free memory. Core + L1, with everything past it
excluded, is the line that can be drawn on every one of them, and [§8.1](#81-cores-after-the-first-four)'s
roadmap starts from four points on it.

### 4.3 Annotation completeness and the estimator bound

| core | pins listed | annotated (SAIF) | unannotated | unmatched | verdict |
|---|---|---|---|---|---|
| SERV | 28,264 | 28,264 (100.0000 %) | 0 | 0 | pass |
| picorv32 | 53,694 | 53,694 (100.0000 %) | 0 | 0 | pass |
| ibex | 81,165 | 81,165 (100.0000 %) | 0 | 0 | pass |
| VeeR EH1 | 762,068 | 754,384 (98.9917 %) | 7,684 | **1.0073 %** | pass |

**Table 3.** Pin activity annotation at global route. "Pins listed" is
OpenSTA's pin set for power: leaf pins plus top-level ports, less internal and
power/ground pins. Every class in [§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator) is empty for the three cacheless cores.
The counts are on the tiles with their memories inside the boundary ([§4.2](#42-what-the-boundary-costs))
and on the shape-aware memory model's interface ([§8.7](#87-a-memory-model-that-knows-its-size)), which replaced every
macro pin in the design; complete annotation survived that.

**VeeR's 7,684 are itemised, not tolerated.** Eight are waived by name: the
four top-level input ports `cm_soc_veer.sv` ties to constants, which Verilator
never emits into the SAIF, and the four pins of the one clock-gate cell [§6.5](#65-two-carried-workarounds)'s
renamer touched -- two on clock nets, two (enable and scan enable) not. The
remaining 7,676 -- the 1.0073 % -- are pins OpenSTA's hierarchical network
carries that odb's instance enumeration does not reach: the clock cells whose
SAIF entries had to be dropped, their names containing the hierarchy
separator. They were never going to be annotated; what is conceded is
classifying them from the database rather than by name ([§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator)).

| core | SAIF arm spread | vectorless arm spread | vectorless at OpenSTA's default | measured |
|---|---|---|---|---|
| SERV | **0.0000 %** | 21.06 % | 59.38 mW | 54.737 mW |
| picorv32 | **0.0000 %** | 40.84 % | 69.74 mW | 56.561 mW |
| ibex | **0.0000 %** | 79.46 % | 38.83 mW | 22.519 mW |
| VeeR EH1 | **0.0000 %** | 144.41 % | 63.53 mW | 145.576 mW |

**Table 4.** Total power as the default activity seeded into unannotated roots
is swept over 0.0, 0.1, 1.0 and 2.0 toggles per clock period. The SAIF-driven
total is bit-identical at ten significant figures at every point -- for
picorv32, 5.6561295e-02 W four times. The vectorless total runs 52.78 →
65.57 mW (SERV), 53.62 → 82.86 mW (picorv32), 18.95 → 48.46 mW (ibex) and
21.71 → 145.41 mW (VeeR).

The control arm's spread -- 21 % on SERV, 41 % on picorv32, 79 % on ibex,
144 % on VeeR -- is what is not a constant here. Across the cacheless cores it
orders by how much of each design the estimator is free to invent: least
where a macro's internal power dominates a total that seeding an input cannot
move, most where the design is logic. SERV, 78 % macro, is the weakest
control; it still moves 12.8 mW against a SAIF arm that moves zero.

**VeeR breaks the ordering, and the reason is the clock gates.** At 75 %
macro it sits inside the others' range, yet its control arm runs to nearly
seven times its floor -- 21.71 mW at zero activity, 145.41 mW at two toggles
per cycle. It is the one core with a real clock-gating network ([§6.4](#64-veers-clock-gates-and-what-mapping-them-cost)), and a
gated clock's activity *is* the enable's: told the enables never toggle, the
estimator switches off a tree carrying 18.8 % of the design's power; told
they toggle every cycle, it runs the tree flat out. Clock gating is the
structure that gives a probabilistic estimator the most room, so the spread
measures how much a vectorless report would be guessing. The SAIF arm still
does not move.

Read together, Tables 3 and 4 are the central methodological claim, and it is
measured: **OpenSTA's probabilistic activity model contributes nothing to the
reported energy.** The knob is demonstrably live -- it moves unannotated power
by 21 to 144 % -- and it moves the annotated result by zero. VeeR shows why it
takes both halves: it is the one design with unmatched pins, its SAIF arm is
still bit-identical across the sweep, and the sweep bounds every path by which
the estimator could have invented a density -- so whatever those 7,684 pins
cost, it is not the estimator. What they are is clock cells, which take
$2/\mathrm{period}$ from the SDC ([§2.2](#22-what-opensta-does-with-an-unannotated-pin)), so their unannotated state is
correct. The first half is measured, the second classified.

A secondary observation: at OpenSTA's default activity a vectorless report
says 59.4 mW for SERV against a measured 54.7 (1.09x), 69.7 mW for picorv32
against 56.6 (1.23x), 38.8 mW for ibex against 22.5 (1.72x) -- and 63.5 mW for
VeeR against 146.0 (0.43x), the one core it *understates*, because told
nothing about the enables it runs the clock gates at a guess. The error
changes sign across the table: a vectorless CoreMark/Joule comparison would
put ibex 1.03x of VeeR where the measurement puts it 4.08x above -- blind to
the one difference between the two cores that [§4.7](#47-where-the-power-goes) shows is real.

### 4.4 A 22 nm literature series, and what it is and is not

The red open squares in Figure 1 are CVA6, CVA6S+ and the XuanTie C910 as
published in *Ramping Up Open-Source RISC-V Cores* [5]: GlobalFoundries
22 FDX, Synopsys PrimeTime 2022.03, post-layout netlist simulation, typical
corner (0.8 V, TT, 25 °C, RC typical), 64 kB two-way L1 instruction and data
caches. CoreMark/Joule is *derived* as CoreMark/MHz × frequency / power from
that paper's own numbers.

They are drawn apart because reading the two series as one trend would be
wrong four ways: **process** (ASAP7 is a predictive kit, not a foundry PDK);
**tools and stage** (PrimeTime on a post-layout netlist against
`report_power` at global route with estimated parasitics); **corner** (their
typical against our best case, [§5.6](#56-the-corner-is-asap7s-best-case-not-its-typical)); and **boundary -- theirs is not
stated**. Our points harden the memory each core runs out of ([§3.1](#31-the-measurement-boundary)); theirs
configure 64 kB L1s, but the paper does not say whether the reported power
includes them -- Figure 7's breakdown names Fetch, Decode, Issue, Integer
Execution, Load/Store Unit, Floating Point and Control Flow, with no cache
term. A fifth caveat is the derivation's: the power figures are for
`matmult-int` while CoreMark/MHz is CoreMark, so the derived CoreMark/Joule
is an estimate of that paper's efficiency, not a figure it reports.

What the series is good for is the shape: across a 2.2× range in CoreMark/MHz
the derived CoreMark/Joule is nearly flat (28.2k / 27.1k / 29.4k) -- this
study's question, answered independently at another node with other tools.

### 4.5 What else could be plotted, and why almost nothing can

To place a published core on these axes at [§3.1](#31-the-measurement-boundary)'s boundary, a source must
supply four things: **CoreMark/MHz** on a stated compiler and ISA; **a power
figure** in watts with its frequency; **a stated boundary** -- whether the L1
caches are inside the reported power; and **the same workload for both
halves**, since a CoreMark/Joule derived from a CoreMark score and a power
number from another benchmark is an estimate. The first is common; the rest
are not.

| source | CoreMark/MHz | power | boundary stated | same workload |
|---|---|---|---|---|
| *Ramping Up Open-Source RISC-V Cores* (CF'25) [5] | yes, 3 cores | yes, Fig. 7 | **no** — Fig. 7 names Fetch, Decode, Issue, Integer Execution, LSU, FP, Control Flow; no cache term, and no sentence says whether the 64 kB L1s are inside | **no** — power is for `matmult-int` |
| *From Swift to Mighty* (CARRV'21) [13] | yes, ibex and CV32E40P | yes, their Table 5, PrimeTime on a post-synthesis netlist, TSMC 65 nm | yes — core-only, no memory | yes — CoreMark |
| *Slow and steady wins the race?* (PATMOS'17) [12] | in the abstract, as ratios | yes, PrimeTime on post-layout activity, UMC 65 nm | core-only, from the cores' construction: no caches | yes — CoreMark; the table was not retrieved for this version |
| *Optimizing Energy Efficiency in Subthreshold RISC-V Cores* [14] | **no** — eight MachSuite kernels, an open but dormant accelerator suite from 2014 that no core reports a score on | yes, Table III, PrimeTime on gate-level activity from layout, commercial 130 nm at 300 mV | yes — core-only, ideal single-cycle memory assumed | **no** — CoreMark is not run |
| *RISC-V Resource-Constrained Cores: A Survey and Energy Comparison* [15] | yes, 7 cores | **reports CoreMark iterations/mJ directly** — 8.7 for ibex — but on an "ASIC prototyping platform" we read as an FPGA, so the Joules are the fabric's | n/a | yes, CoreMark |
| *The Cost of Application-Class Processing* [6] | not reported | yes, silicon | not established from the abstract; the full text was not surveyed here | n/a |
| *CoreMark Benchmarking for SweRV* [11] | **4.94**, and the exact generator configuration | no — FPGA prototype at 40 MHz, no ASIC power | n/a | n/a |
| SonicBOOM (CARRV 2020) [32] | 6.2 | no | n/a | n/a |

One source clears enough of the bar to be drawn at this study's boundary, and
clears items 3 and 4 only by our choosing to derive from it -- which is why
[§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not) draws it apart with the derivation stated. [13] clears all four for ibex
at the core-only boundary [§4.2](#42-what-the-boundary-costs) abandoned, and [§4.8](#48-cross-checks-against-the-nearest-published-studies) uses it as a cross-check.
The rest contribute an x-coordinate; `results.json` carries them under
`references`, and the plot shows them as grey ticks on the x-axis rather than
inventing a y. That is the argument for the study: a CoreMark/MHz is cheap to
publish and a CoreMark/Joule at a stated boundary is not, so the second is
largely missing, and a missing number cannot be argued with.

**The uniqueness claim is dated.** "No other published comparison" is a claim
about the literature on a day -- **September 2026**, recorded in
`results.json` under `provenance.uniqueness` and checked against this
document's dateline by `readme_numbers_test`. The check is the table above
read against three qualifiers, plus a search for the metric by name; it is
not a systematic survey, and a reader who names a study that clears all three
retires the claim. Each qualifier excludes something real:

| drop this qualifier | and this enters |
|---|---|
| more than one core, each hardened to an ASIC netlist (FPGA excluded) | ULPMark-CM [2]: one silicon MCU per score, dozens of them; and the seven-core survey [15], which reports CoreMark iterations/mJ but on a prototyping fabric whose Joules are not the cores’ |
| activity from CoreMark itself | any vectorless report; and [5], whose power is measured on `matmult-int` |
| every input open and pinned, re-runnable with one command | [12] and [13]: three and two cores on CoreMark energy, PrimeTime on post-layout or post-synthesis activity, in UMC 65 nm and TSMC 65 nm; and [14], seven cores on MachSuite in a commercial 130 nm |

Two further qualifiers would each exclude every near miss, and neither is
needed: a **sub-10 nm node** ([12], [13] and [14] are at 65 and 130 nm, [5]
at 22 nm; ASAP7 is predictive ([§5.8](#58-a-predictive-kit-not-a-foundry-pdk)), so this study is claimed for the shape
of the comparison, not its Watts), and **both sides of the out-of-order line**
(no comparison in the table has a point above 5 CoreMark/MHz *and* one below
0.1; this study already spans 198x in CoreMark/MHz, and with XiangShan ([§8.1](#81-cores-after-the-first-four))
will span bit-serial to out-of-order in one flow).

### 4.6 Is the shape real? The boundary and the memory model

**The degeneracy.** $\mathrm{CoreMark/Joule} = \mathrm{CoreMark/MHz}\cdot f/P$,
so if $f/P$ is constant across cores the energy axis carries no information
the performance axis did not. Across a 101x span in CoreMark/MHz, the three
cacheless cores' $f/P$ spans **1.22x**: the energy axis is close to the
performance axis in disguise.

**What the boundary is worth.** Extrapolating the three cacheless cores to
VeeR's performance overpredicts its CoreMark/Joule by an amount that depends
on whether their memories are inside the measurement and whether every core
runs at its derived period (`scripts/fit_results.py`, from `results.json`;
it also fits slopes, which are not quoted -- see below):

| | core-only | core + L1, derived periods ([§4.2](#42-what-the-boundary-costs), [§5.7](#57-frequency-and-what-deriving-it-changed)) |
|---|---|---|
| extrapolation to VeeR overpredicts by | 15.2x | **7.88x** |
| $f/P$ spread, three cacheless cores | 1.89x | **1.22x** |
| power spread, those three | 1.15x | **2.52x** |

Closing the boundary took 48 % out of the disagreement between the cacheless
cores and the one core that already met it, which is [§4.2](#42-what-the-boundary-costs)'s correction
measured. It did not loosen the line: $f/P$ spans 1.22x with the memories
inside against 1.89x outside. Deriving the periods widened the power spread
to 2.52x without widening $f/P$ -- two cores doubled their frequency and
their power followed, [§2.3](#23-why-coremarkjoule-falls-as-coremarksecond-rises)'s cancellation observed.

**The line is the memory model.** Every memory is on one shape-aware model
([§8.7](#87-a-memory-model-that-knows-its-size)) and the macros are 66 to 78 % of each point ([§4.7](#47-where-the-power-goes)). The three
cacheless cores run the same benchmark out of the same two memories, so what
separates them is access rate and the model's per-access energy for a memory
of that size. One model on all four points means the comparison is not
confounded by the memory being modelled differently for each -- and means
CoreMark/Joule does not discriminate among cores of this class, because the
term that dominates every point is the same memory on every cacheless core.
No slope or $R^2$ is reported for three or four points; with one degree of
freedom they would be numbers without evidence. Each frequency is derived
([§5.7](#57-frequency-and-what-deriving-it-changed)), so $f/P$ mixes no guessed frequency into a measured power, though
each is one flow's derived period on one floorplan, not a Pareto front
([§8.5](#85-the-pareto-curve)).

**What would make the axis mean something.** The shape-aware model was the
first requirement and is done ([§8.7](#87-a-memory-model-that-knows-its-size)); the axis above is already on it and
still this flat. What is left is a *characterised* model rather than a fitted
one, cores whose memory systems genuinely differ ([§8.1](#81-cores-after-the-first-four)), and a second period
pass on the derived floorplans ([§8.4](#84-a-second-period-pass)). The present data cannot separate a
real law from the memory model's flatness.

**Where the four points land.** VeeR delivers **1.95x** ibex's performance
per clock at **0.25x** its CoreMark/Joule, drawing 6.49x the power. With
ibex's memory outside the measurement the ratio reads 0.07x, and the
conclusion that would support -- that minimal cores dominate the energy
metric -- is an artefact of the boundary. VeeR lands at **0.70x to 0.76x** of
the GF 22 FDX series of [§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not) (27,108--29,412) and ibex 2.9x above it: a
consistency check between cores at a stated core + L1 boundary on different
nodes with different tools, not a validation. [§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not)'s caveats stand, and
[§4.8](#48-cross-checks-against-the-nearest-published-studies)'s cross-checks include one that does not come back clean.

### 4.7 Where the power goes

`report_power` groups by cell kind, and the grouping turns [§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model)'s statistics
into mechanics. Table 5 is the state after [§4.2](#42-what-the-boundary-costs) and [§8.7](#87-a-memory-model-that-knows-its-size): every memory inside
the boundary, on the shape-aware model.

<!-- table7 -->
| core | total | Clock | Sequential | Combinational | **Macro** | logic (all but macro) |
|---|---|---|---|---|---|---|
| ibex | **22.50 mW** | 2.73 (12.1 %) | 2.45 (10.9 %) | 2.44 (10.8 %) | **14.90 (66.2 %)** | 7.60 (33.8 %) |
| picorv32 | **56.60 mW** | 7.69 (13.6 %) | 6.20 (11.0 %) | 1.98 (3.5 %) | **40.70 (71.9 %)** | 15.90 (28.1 %) |
| SERV | **54.70 mW** | 5.63 (10.3 %) | 4.53 (8.3 %) | 1.88 (3.4 %) | **42.70 (78.1 %)** | 12.00 (21.9 %) |
| VeeR EH1 | **146.00 mW** | 27.40 (18.8 %) | 6.95 (4.8 %) | 2.36 (1.6 %) | **109.00 (74.7 %)** | 37.00 (25.3 %) |
<!-- /table7 -->

**Table 5.** Power by cell kind at the four reported points, in mW.

**The memory is the measurement.** 66 to 78 % of every point: 78.1 % of SERV down to 66.2 % of ibex.
For the three cacheless cores the macro column is between 2.0 and 3.6 times everything
else in the row, and [§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model)'s extrapolation error is this column.

**The logic tracks state, not work.** Clock plus sequential is 5.2 to 13.9 mW
on the three cacheless cores and follows how much state a design has and how
fast it is clocked: picorv32 and SERV at over 2 GHz spend more on clock and
flops than ibex at 772 MHz while retiring a fraction of its work per cycle.
The term that tracks the architecture is combinational power, 1.88--2.44 mW,
the smallest in every row -- [§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model)'s 1.22x $f/P$ spread as a mechanism.

**VeeR is the one different row.** Its macro share is 75 %, inside the
others' range, but its clock power is 27.4 mW -- 10.0x ibex's -- from an
order of magnitude more state and a real clock-gating network. Its logic is
37.0 mW against ibex's 7.6 mW: **4.9x the logic power for 1.95x the
performance per clock.** The memory stops being the whole story once a core
is big enough to have one worth having.

**A caveat on the macro column.** Every row's macro figure comes from one
fitted model ([§5.1](#51-the-memory-model-and-the-memory-this-study-chose), [§8.7](#87-a-memory-model-that-knows-its-size)) whose Liberty charges each memory's read-write
energy on every clock edge whatever the enable does, so the column scales
with memory shape and clock cycles, not with accesses. All four rows are
equally affected, which is the point of one generator, but the column
measures memory size times cycles. This is the SRAM-against-logic split [§8.2](#82-deep-physical-metrics)
asks for, arriving early because [§4.2](#42-what-the-boundary-costs) put something in the macro column for
every core.

### 4.8 Cross-checks against the nearest published studies

Three published comparisons come close enough to check against ([§4.5](#45-what-else-could-be-plotted-and-why-almost-nothing-can)). None
is like-for-like -- different nodes, corners, tools, boundaries, in one case a
different workload -- so these are plausibility checks, and one fails in a
way this study cannot yet explain.

**ibex against *From Swift to Mighty* [13].** Gallmann et al. measure the
default ibex -- RV32IMC, no instruction cache, the core this study measures
-- on a post-synthesis netlist in TSMC 65 nm at 1.2 V, typical corner, with
PrimeTime and post-synthesis activity. One difference is theirs: "a
latch-based register file implementation has been used for both the cores",
where this study's ibex is `ibex_register_file_ff` and hardens as flops
([§5.9](#59-where-each-cores-register-file-ends-up)). No memory is inside their boundary, so the comparable quantity is
core-only: the tile's total less its macro group. To compare at the same
stage, this study's ibex was taken to synthesis and no further, at its
first-pass 1282 ps ([§5.7](#57-frequency-and-what-deriving-it-changed)) and at the two periods the published netlists were synthesised for,
the same SAIF window on each, power reported with no wires and no clock tree
(`flow/power_synth.tcl`; arms `ibex_synth100` and `ibex_synth500`, table
`results/ibex_synth_crosscheck.md`).

| arm | f | core-only P | of which clock | core-only dynamic / iteration | CoreMark/MHz |
|---|---|---|---|---|---|
| this study, global route, 1282 ps | 780 MHz | 7.80 mW | 2.96 mW | 4.07 µJ | 2.45 |
| this study, synthesis, 1282 ps | 780 MHz | 2.50 mW | 0.14 mW | 1.30 µJ, clamped | 2.45 |
| this study, synthesis, 2000 ps | 500 MHz | 1.96 mW | 0.14 mW | 1.60 µJ, clamped | 2.45 |
| **this study, synthesis, 10000 ps** | 100 MHz | 0.59 mW | 0.06 mW | **2.40 µJ** | 2.45 |
| [13], synthesised for 100 MHz | 100 MHz | -- | none | **3.40 µJ** | 2.36 |
| [13], synthesised for 500 MHz | 500 MHz | -- | none | **0.92 µJ** | 2.36 |

**What the arms established first.** The three synthesis netlists are
byte-identical -- synthesis does not depend on the clock period -- so the
synthesis arms are one netlist, 22,471 cells and 1,979 flops, driven by one
SAIF at three durations. Combinational and macro power came out
period-independent to three digits. Sequential internal power did not, for
[§2.2](#22-what-opensta-does-with-an-unannotated-pin)'s last reason: the clock port drives all 1,979 flop clock pins
unbuffered, its slew is about 2.1 ns, and OpenSTA clamps the flops' clock
activity to 0.48 toggles per ns where the SDC says 1.56 (1282 ps) and 1.00
(2000 ps). A per-flop probe (`flop_power_probe`) shows 0.48/ns at both
periods, 0.20/ns -- unclamped, $2/\mathrm{period}$ -- at 10000 ps, and
1.56/ns at global route where the clock tree gives the pins a real slew.
`set_clock_transition` does not lift the clamp; arms with a 20 ps transition
moved nothing. So the unclamped 10000 ps arm *is* this netlist's
post-synthesis dynamic energy per iteration at any period, **2.40 µJ**, and
the clamped arms understate it by the clamp ratio, 3.25x on the flop term at
1282 ps.

**What the comparison says.** The performance halves agree to 4 %: 2.36
against 2.45 CoreMark/MHz, GCC 10 `-O3` with loop unrolling against GCC 13
with [§5.10](#510-the-compiler-flag-sweep-is-not-wired-up)'s flags. The stage costs a measured **1.70x** -- 4.07 µJ at global
route against 2.40 µJ at synthesis: the clock tree (2.96 of 7.80 mW), the
estimated wires and the sizing that closing at 780 MHz took. **At the same
stage, with no wires and no clock tree, ibex on ASAP7 costs 2.40 µJ per
iteration against 3.40 and 0.92 µJ published for the same RTL at 65 nm:
0.71x one row and 2.6x the other.** Two process generations and a $V^2$
ratio of 0.41 should put a 7 nm energy several times below a 65 nm one, and
it is not there. Ruled out by measurement: the stage, clock tree and wires
(1.70x), the SAIF (identical toggles in every arm), the estimator ([§4.3](#43-annotation-completeness-and-the-estimator-bound)). Not
ruled out: ASAP7's predictive Liberty energies (the flops alone cost 1.64 fJ
per flop-cycle, from the unclamped arm); the mapping (22,471 cells, 2,328 of
them buffers, for a core Design Compiler mapped in 23.7 kGE); and **the
register file**, latches there and flops here -- a 32x32 array clocked every
cycle, in the direction of the disagreement, unmeasured because measuring it
means hardening ibex with a latch-based file, a change to the design. On the
published side the two rows are one RTL synthesised twice and differ 3.7x in
energy per iteration for a 33 % change in area, which the source does not
explain either. **Reported as measured down to the netlist and unexplained
below it**; the next measurement is one of theirs re-taken with their tools,
or one of ours with a characterised library.

**Ordering against the subthreshold study [14].** Djupdal et al. implement
SERV, picorv32 and ibex with QERV, Rocket and two Vex variants through Genus
and Innovus to layout in a commercial 130 nm process at 300 mV, PrimeTime
Power on gate-level activity from the final netlist. Their boundary is the
one this study abandoned -- no memory, single-cycle ideal -- their workload is
eight MachSuite kernels, every core is RV32E, and four of the seven carry a
latch-based register file the upstream cores do not ship. They report energy
per instruction averaged over the kernels.

| core | [14] energy / instruction | [14] power | [14] clock period | [14] area | this study, core-only, energy / CoreMark iteration | this study, core-only power |
|---|---|---|---|---|---|---|
| SERV | 78.74 pJ | 2.85 µW | 478 ns | 0.096 mm² | 193 µJ | 6.68 mW |
| picorv32 | 19.74 pJ | 5.37 µW | 686 ns | 0.235 mm² | 11.6 µJ | 6.43 mW |
| ibex | 14.10 pJ | 6.13 µW | 1,450 ns | 0.384 mm² | 3.60 µJ | 7.37 mW |

The core-only column is the earlier build at 1200 ps; at the first-pass
1282 ps with the SAIF timed to it, ibex core-only is 7.80 mW and 4.07 µJ, and the
ratios move by less than 15 %. The ordering agrees -- ibex, picorv32, SERV --
and the ratios do not, for a reason each regime predicts. Per instruction
SERV costs 5.6x ibex there; per CoreMark iteration 53x here, but SERV runs
`rv32i` with multiplication in software, so its iteration is several times
more instructions than ibex's `rv32imc` one, and this harness does not yet
count retired instructions. The power ratios tell the rest: SERV draws 0.46x
ibex's power at 300 mV and 0.91x at 0.77 V. At subthreshold power is leakage
and leakage is area, so a quarter the size draws a quarter the power; here
power is clock tree and flops, and SERV's flops toggle every cycle for 41
million cycles. A retired-instruction count would make this a comparison,
and it is cheap to add.

**The three PULP cores of [12].** Schiavone et al. compare Riscy, Zero-riscy
and Micro-riscy on CoreMark energy in UMC 65 nm with PrimeTime on post-layout
activity; Zero-riscy is the core lowRISC renamed ibex. From the abstract,
Zero-riscy is more than 2x smaller than Riscy, consumes 2x less energy and
takes 1.3x longer on CoreMark. The table was not retrieved, so this
cross-check is owed rather than done; it would test ibex's absolute energy
per iteration at a third node against the [13] disagreement.

### 4.9 The literature, side by side, and the discrepancies worth chasing

Four numbers describe a core to the people who publish them: gate
equivalents, minimum clock period, CoreMark/MHz and CoreMark/Joule. This
study measures the last two and, with `<design>_physical`, the first two.
The literature gives some subset for each core, so the table is rendered
from `pin_results.py`, where each row carries a `source`, a `locator`, a
`confidence` (`stated`, `derived` here from the source's figures, or
`estimated` by the source) and, for a frequency, its kind: silicon,
signoff, synthesis, an announced target, or the SDC period this study
closed. A cell the source does not give is a dash, never a guess.

```sh
bazelisk run //test/coremark_joule:pin -- --table
```

Gate equivalents are standard-cell area over the library's smallest
two-input NAND, macros excluded, the convention every paper here uses. On
ASAP7 that NAND is `NAND2xp33_ASAP7_75t_R` at 0.05832 µm², written beside
the count so the division can be redone. Published kGE figures rarely
name their NAND, and ibex's come from yosys on another library with
another register file, so the column is comparable to within tens of
percent.

| core | source | node | kGE | f (MHz) | CoreMark/MHz | CoreMark/Joule |
|---|---|---|---|---|---|---|
| ibex (rv32imc) | this study, grt | asap7 | probe | 772 (SDC) | 2.45 | 84167 |
| picorv32 (rv32im) | this study, grt | asap7 | probe | 2141 (SDC) | 0.55 | 20926 |
| serv (rv32i) | this study, grt | asap7 | probe | 2283 (SDC) | 0.02 | 1013 |
| veer (rv32imc) | this study, grt | asap7 | probe | 628 (SDC) | 4.80 | 20629 |
| XiangShan Kunminghu V3 (rv64gc) | this study, floorplan | asap7 | ~19,900 | 833 (SDC, untimed) | 8.29 | pending |
| CVA6 | [5] | GF 22 FDX | 730 | 1083 (signoff) | 2.19 | 28205 |
| CVA6S+ | [5] | GF 22 FDX | 851 | 1081 (signoff) | 2.84 | 27108 |
| XuanTie C910 | [5] | GF 22 FDX | 2674 | 1543 (signoff) | 4.86 (7.1 in [32]) | 29412 |
| Ariane | [6] | GF 22 FDX | 210 | 1700 (silicon) | -- | -- |
| XiangShan Kunminghu V2 | [31] | 7 nm | -- (1.8–2.1 mm² with 1 MB L2) | 3000 (signoff) | -- | -- |
| XiangShan Nanhu V2 | [31] | 14 nm | -- | 2500 (silicon) | -- | -- |
| SonicBOOM | [32] | FinFET, unnamed | -- | 1000 (synthesis) | 6.20 | -- |
| ibex (small) | [33] | yosys kGE | 26.6 | -- | 2.47 | -- |
| SERV | [34] | "typical CMOS" | 2.1 | -- | -- | -- |
| picorv32 | [35] | FPGA only | -- | -- | -- | -- |
| VeeR EH1 | [11], [36] | 28 nm | -- | 1800 (target) | 4.94 | -- |
| VeeR EL2 | [37] | TSMC 16 nm | -- (0.023 mm²) | 600 (target) | 3.60 | -- |

The `probe` cells are `//test/coremark_joule/designs/asap7/<core>:*_physical`,
attached to each point by `//test/coremark_joule:pin` from the global-route
ODB the power came from, and filled in when the pinned file is next re-derived.
XiangShan's gate count is from its floorplan report (1.159 mm² of
standard cells) under the turnaround synthesis settings its `config.mk`
records, a ceiling until the measured run replaces them. [5]'s kGE is its
Figure 6 total less the Icache and Dcache bars, a core-without-caches
count like the others; its CoreMark/Joule is the [§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not) derivation.

The table is for the discrepancies. Five are worth chasing, each with the
same question: is the gap the core's, ASAP7's, or this flow's?

**1. XiangShan is 7.4× the gates of the C910 for 1.7× its CoreMark/MHz.**
The C910 is a 3-issue out-of-order core at 2,674 kGE; Kunminghu V3 is
6-wide rename, 13 stages, a 160-entry reorder buffer holding six
instructions per entry, 64 kB L1s with 8-way data and a vector unit, at
~19,900 kGE on ASAP7. Some of that ratio is real width, not all, and the
flow's share comes first: hierarchical synthesis with ~90 kept modules,
the turnaround list in its `config.mk`, blocks constant propagation and
logic sharing across every boundary, and the netlist shows it in 156,482
tie-high cells, one for every constant port a kept module cannot see
through; ABC ran its area script; and the asynchronous reset costs a
larger flop on 147,039 registers. The published cross-check is indirect:
Kunminghu V2 with 1 MB of L2 is 1.8–2.1 mm² in a foundry 7 nm [31], and
our 1.35 mm² of instance area without the L2 is the same order once the
L2's SRAM is taken out of theirs. So the gap to the C910 is more likely
real than the gap to XiangShan's own number; flattening the turnaround
modules and re-measuring says how much.

**2. VeeR EH1 closes at 628 MHz on ASAP7 against a 1.8 GHz target on
28 nm.** The largest frequency discrepancy in the table, and it points the
wrong way: a 7 nm-class kit should not be 2.9× slower than a 28 nm one.
Either the announcement number is a target never demonstrated in a paper
-- [11] reports only the FPGA -- or the flow leaves it on the table: the
derived 1593 ps is what one flow closed on one floorplan ([§5.7](#57-frequency-and-what-deriving-it-changed), [§8.4](#84-a-second-period-pass)), and
the ICCM/DCCM access path runs through a memory view whose access time is
a fitted model, not a characterised macro ([§8.7](#87-a-memory-model-that-knows-its-size)). `swerv_wrapper_period`
reports the worst reg2reg endpoint; on a macro pin, the discrepancy is
the memory model, and re-deriving the floorplan on the new views ([§8.4](#84-a-second-period-pass)) is
the pass not yet run.

**3. Kunminghu V2's 3 GHz against our untimed 1200 ps.** Kunminghu V2
signs off at 3.0 GHz [31], a 333 ps cycle on 13 stages. Our SDC asks for
1200 ps, and the floorplan closed it only after the asynchronous reset was
declared a false path in its `constraints.sdc` and ABC's buffering was
left out. Where the reg2reg critical path lies after placement and CTS
decides it: inside the core logic, OpenROAD without retiming or useful
skew on a predictive kit at 0.77 V is 3.6× off a commercial 7 nm flow, a
number worth knowing on its own; through one of the 303 SRAM banks, it is
the memory view's timing model again, as in 2.

**4. Two CoreMark/MHz for the C910, 1.5× apart.** [5] measured 4.86;
SonicBOOM's comparison chart carries the vendor's 7.1 [32]. Nothing in
the hardware changed: the gap is compiler, flags and run rules, and it
bounds how seriously two CoreMark/MHz figures from different hands can be
compared, about ±20 % around their mean. Our figures sit inside that band
of their publications, ibex 2.454 against 2.47 and VeeR 4.798 against
4.94, both low by the compiler this study fixes for all cores rather than
tunes per core. XiangShan's 8.29 has no published CoreMark to sit
against; Kunminghu V2's SPEC CPU2006 of 14.7/GHz [31] is the closest, and
a 6-wide core landing 1.3× above SonicBOOM's 6.2 says more about
CoreMark's loop bodies than about the core.

**5. CoreMark/Joule at 22 nm is flat where ASAP7's is not.** [5]'s three
cores span 2.2× in CoreMark/MHz and 3.7× in gates and land within 9 % of
each other in CoreMark/Joule ([§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not)). Our four span 198× and 83×, with
ibex at 84k against CVA6's 28k for a similar CoreMark/MHz and 30× fewer
gates. Part is the corner ([§5.6](#56-the-corner-is-asap7s-best-case-not-its-typical)), part the boundary [5] does not state.
But ibex against CVA6 is the cleanest pair in the table, same class of
core and CoreMark/MHz within 12 %, and a 3.0× energy gap for a 30× gate
gap says most of the energy in both is not in the gates that differ. [§4.7](#47-where-the-power-goes)
puts ours at 78–94 % in the macros and the clock; whether [5]'s is too is
the question its Figure 7 cannot answer, and why the two series stay
separate in Figure 1.

## 5. Threats to validity

### 5.1 The memory model, and the memory this study chose

The boundary of [§3.1](#31-the-measurement-boundary) is met and its cost is measured in [§4.2](#42-what-the-boundary-costs). What remains is
the memory itself: one fitted model carrying two thirds to four fifths of
every point, sizes this study chose rather than the cores', and one artefact
of how the tiles wire them.

**The memory model is fitted, and switching it moved every point.** Every
macro was first a FakeRAM2.0 view, from the tool that produced the platform's
own `fakeram7_*` views, and FakeRAM's ASAP7 backend emits **one** switching
energy and **one** leakage number for every shape:

| shipped shape | area | `cell_leakage_power` | `clk` `internal_power` |
|---|---|---|---|
| `fakeram7_64x21` | 56.4 µm² | 128.9 | 1.345 |
| `fakeram7_256x32` | 344.0 µm² | 128.9 | 1.345 |
| `fakeram7_256x256` | 2,751.9 µm² | 128.9 | 1.345 |
| `fakeram7_2048x39` | 3,353.9 µm² | 128.9 | 1.345 |

Area scaled; energy and leakage did not, so halving every memory would have
moved no number. [§8.7](#87-a-memory-model-that-knows-its-size) replaced it with `tools/memory_macro_scaler`, one model
for every memory on every point, whose read energy, write energy and leakage
follow rows and bits. The switch alone, at unchanged periods and floorplans:

<!-- switch -->
| core | power, FakeRAM | power, scaler | CoreMark/Joule, FakeRAM | CoreMark/Joule, scaler | change | macro share, scaler |
|---|---|---|---|---|---|---|
| SERV | 44.3 mW | 54.7 mW | 1,251 | 1,013 | -19 % | 78 % |
| picorv32 | 45.7 mW | 56.6 mW | 25,918 | 20,926 | -19 % | 72 % |
| ibex | 19.0 mW | 22.8 mW | 100,760 | 83,966 | -17 % | 66 % |
| VeeR EH1 | 86.9 mW | 144.0 mW | 34,702 | 20,942 | -40 % | 76 % |
<!-- /switch -->

**Table 6.** The memory model switched and nothing else.

The three cacheless cores fell together, by 17 to 19 %, because they share
the same two memories and the model charges the 32 kB instruction memory more
than FakeRAM's flat number. VeeR fell 40 %: its 28 macros -- eight DCCM banks
of 2048 x 39, sixteen cache data arrays of 256 x 34, four tag arrays -- each
cost more per clock than FakeRAM's one figure, and its macro column went from
59 % to 76 %. That is a ranking change: VeeR (20,942) sits level with
picorv32 (20,926) where it was 1.3x above, so the one conclusion the FakeRAM
numbers supported about the pair -- that the pipelined core with a real L1
beat the multi-cycle core on energy -- was a property of the memory model.
The scaler's documentation calls its fit a first-order anchor with published
residuals of about 25 % on SRAM area, and its Liberty charges the read-write
energy on every clock edge whatever the enable does ([§4.7](#47-where-the-power-goes)). Its leakage
anchor is 1 pW per bit at 45 nm scaled linearly with node, which puts a 32 kB
macro at 41 nW where FakeRAM charged 129 µW for every shape; at ASAP7's fast
corner the truth is likely one to two orders of magnitude above the scaler
and below FakeRAM, so Table 1's leakage term is a lower bound. A model wrong
by a bounded factor for every shape is a smaller caveat than one blind to
shape.

**ibex is measured with `ICache=0`, and that is a finding.** Turning the
cache on was built and measured and closes nothing. It cannot buy a cycle:
behind a tightly-coupled memory that answers in one, CoreMark/MHz is 2.4543
with the cache on and off, on both marches. And it cannot hold the benchmark:
ibex's cache is 4 kB (`IC_SIZE_BYTES` is a package parameter) against
24--30 kB of `.text`, so `.text` in external memory fetched through the cache
-- VeeR's arrangement -- would miss continuously and break [§4.2](#42-what-the-boundary-costs)'s residency
check; VeeR's cache is 16 kB and CoreMark fits. What the cache changes is
energy, mostly for a reason that belongs to the memory model:

| | CoreMark/MHz | CoreMark/Joule | power | macro |
|---|---|---|---|---|
| `ICache=0` (the configuration reported) | 2.4543 | 99,284 | 20.60 mW | 11.90 mW |
| `ICache=1` | 2.4543 | 64,316 | 31.80 mW | 21.40 mW |

Both rows are at 1200 ps rather than the derived 1296 ps ([§5.7](#57-frequency-and-what-deriving-it-changed)); the
comparison stands while neither is the reported point. A 1.54x energy penalty
for no performance, 9.5 mW of the 11.2 mW rise being macro power: a cache hit
reads both ways' tags and both ways' data, four macro accesses in place of
one to the instruction memory, and FakeRAM charged the same energy per access
whatever the size, so four small accesses cost four times one large one. In
silicon they cost a fraction, which is why caches exist. **Under that model a
cache could only lose**, so the 1.54x measured the model, not ibex's cache;
under the shape-aware model the four small accesses cost less, and that
re-measurement is not yet done. Both configurations are kept:
`//test/coremark_joule/designs/asap7/ibex_icache` builds the cache version to
global route, keeping the ASAP7 `prim_ram_1p` and the two cache-RAM macros
from rotting -- a configuration that silently reverted to flip-flops would be
44,032 of them, twenty times ibex's own flop count. Supplying `prim_ram_1p`
changes nothing in ibex: lowRISC ships the primitive as `prim_generic` and
`prim_xilinx` side by side, and `ibex_top`'s parameters are untouched.

**The memory is the study's, not the cores'.** None of the three repositories
ships one, so the sizes, port shape and address map are this study's choices
(`sw/port/link.ld`, `rtl/cmj_progmem.sv`), held constant across every core
and march so that the memory is not a variable. A different defensible
choice would move all three numbers together.

**A core can be charged for toggling it need not do.** Each tile presents the
core's address bus to the macro's address pins with no register between, so
a bus that moves between accesses pays in the macro's input-pin energy. SERV
does: its datapath is bit-serial, and it has the **highest** macro power of
the three (42.70 mW against picorv32's 40.70 and ibex's 14.90) despite by far
the lowest access rate. That is real for this netlist and would be in silicon
built this way, but it is a property of the tile, and registering the address
would change it. It is reported rather than fixed, because fixing it changes
a measured number.

### 5.2 Zero-delay simulation carries no glitch power

The gate-level simulator is Verilator: two-state and zero-delay, so it cannot
produce a glitch. Signoff practice is SDF-annotated event-driven simulation
precisely to capture glitch power, and the literature treats the difference
as a first-order term [7, 8]. This study therefore **under-reports dynamic
power**, and not uniformly: deep combinational logic between registers
glitches more than a short pipeline, so the bias distorts the comparison
between cores -- SERV's bit-serial datapath and ibex's two-stage pipeline are
at opposite ends. [§5.3](#53-glitch-power-in-the-multiplier-measured) puts a number on it for the unit most exposed; the
core-wide figure is unmeasured, for the reasons below. The direction is
opposite to [§4.2](#42-what-the-boundary-costs)'s: glitch would push every point down in CoreMark/Joule, and
most for the cores with the deepest logic.

**This is a stated depth, not a shortfall.** [§2.4](#24-when-glitch-power-is-worth-measuring-and-when-it-is-premature) is the argument: glitch is
a property of an implementation, moves by factors when the floorplan moves
under fixed RTL, and is remedied against one implementation's arrival times.
A screening study that has not committed to an implementation measures a
moving target if it optimises against glitch.

**What was built.** `flow/write_sdf.tcl` takes per-instance delays from the
same ODB the netlist and power report come from; `lib_to_verilog` declares
the `specify` paths those delays annotate, which ASAP7 supplies no Verilog
for; `scripts/iverilog_inputs.py` reconciles what OpenSTA writes with what
iverilog reads, taking annotation failures from 96.2 % of instances to 3 in
21,151; and `test/glitch_smoke` shows the point on two gates, where an
SDF-annotated run emits a pulse on an output whose function is constant zero.

**On ibex's full netlist it does not work.** One annotation runs and every
larger one stops the core; the oracle is the fetch address over 60 cycles
past reset.

| annotated | cells | fetch address over 60 cycles |
|---|---|---|
| nothing | 0 | 48 changes, 7 distinct, no X |
| the multiplier | 3,116 | 48 changes, 7 distinct, no X |
| the sequential cells | 1,979 | freezes after one change, no X |
| one clock delay buffer | 1 | X within a cycle |
| the combinational cells | 19,172 | X within a cycle |
| ditto, less every clock-named cell | 18,912 | X within a cycle |

**Table 7.** What each annotation does to ibex on the first-pass 1282 ps
netlist ([§5.7](#57-frequency-and-what-deriving-it-changed)), same testbench and window throughout.

The first two rows are [§5.3](#53-glitch-power-in-the-multiplier-measured)'s measurement: annotating the multiplier alone
leaves the core executing the identical instruction sequence. The rest fail
two distinguishable ways -- a frozen core with no X when the flops are
annotated, X across the netlist when anything on a clock or combinational
path is -- so this is not one mechanism. Eliminated by measurement: delay
magnitude (every delay rewritten to 1 ps fails identically); setup (a 5000 ps
simulated period against a 1282 ps design fails identically); clock skew
(removing all 260 clock-named cells changes nothing, Table 7's last row);
cell family (no one type is responsible). Six standalone reproductions -- a
buffer, a buffer chain, a chain inside a submodule, a partly annotated chain,
a delayed clock into an annotated flop, a flop with asynchronous reset -- all
behave. Bisection over the combinational set terminates at one cell,
`delaybuf_22_clk`, a `BUFx24` with 17 ps on a clock branch, and it is not the
answer: annotating one clock buffer while every data path is zero-delay is a
guaranteed hold violation, so that subset breaks for a reason the full set
does not have, and removing all clock-named cells does not fix the full set.
The predicate is not monotone in the annotated set, and binary search over a
non-monotone predicate converges on whatever it happens to touch. Finding the
cause means debugging `vvp`'s event scheduler against a 25,835-instance
design -- a simulator project, not a measurement. Three `(CELL` entries out
of 21,151 remain unannotated, `A2 -> Y` and `C -> Y` arcs in the prefetch
buffer, too few to be the cause. Two false leads were faults in the
apparatus: the testbench released reset on a clock edge, which zero-delay
ordering resolves silently and 17 ps of skew turns into X; and the first
detector treated any X bit in the fetch address as failure, so it converged
on the buffer driving `dbg_instr_addr[5]` -- the cell feeding the instrument.

**A second blocker, with a mechanism.** Event-driven gate-level ibex runs at
**76 cycles per second** unannotated. Annotated it starts at 42 and falls --
15.7 cycles/s between cycles 2,000 and 10,000, under 4.9 averaged over a
nine-hour run that had not reached cycle 155,111. Sampling RSS every 30 s,
the zero-delay arm is flat at 139,432 kB while the annotated arm climbs from
139,760 to 154,076 kB over 4.5 minutes and keeps climbing, about 53 kB/s,
proportional to events: **iverilog leaks memory under SDF annotation**, so
the slowdown compounds and estimates from short runs are wrong by hours. It
is recorded as a candidate for upstreaming. One CoreMark iteration is 407,448
cycles -- 1.5 hours per arm before annotation and far longer with it, where
Verilator covers it in minutes, which is why this study uses a cycle-based
simulator. It also rules out hunting for the interesting cycles inside a
whole-core run: 40,000 cycles from reset contain no multiply at all.

**So the measurement moves to the multiplier** ([§5.3](#53-glitch-power-in-the-multiplier-measured)), which needs none of
that. What it cannot give is the core-wide number.

### 5.3 Glitch power in the multiplier, measured

The multiplier is a preserved module boundary of 3,206 cells, 12.4 % of the
design, and the structure the literature names as the worst glitch offender:
unbalanced arrivals into a partial-product tree, spurious switching growing
row by row [7, 8]. It is also separable, which is what makes it measurable
when the whole core is not.

**The method is replay, not a second hardening.** Hardening the multiplier
alone would give a different netlist; the quantity wanted is a bound on the
multiplier this study reports power for. So the module is cut from the
hardened netlist as it stands, carries the per-instance delays `write_sdf`
wrote for the whole design, and is driven by its recorded boundary: all 88
input ports per cycle from the zero-delay whole-core dump. The 8 clock leaves
come from the testbench, because the buffers driving them are outside the
module and their delays are not in its SDF; the other 80 are replayed,
promoted nets included.

Three checks pass. Every one of the 3,123 cells with a timing arc annotates
without an SDF error (the other 83 are tie cells). The recorded outputs are
an oracle, and both arms reproduce them with **zero mismatches**. And the
arms reproduce the whole-core run's 530 multiplies and 1,589 busy cycles
exactly. The only unknowns are four bits -- `alu_adder_ext_i[0]`, `[33]` and
`imd_val_q_i[33:32]` -- X in every recorded change, so constants contributing
no transition.

**The oracle is why this is reportable.** The first run on the re-baselined
netlist came back with 549 mismatches in 5,001 cycles, all on one bit of 169:
`valid_o`, the one output that depends on internal state, since ibex keeps
the accumulator outside the multiplier. The cause was a port silently
replaying as 0 -- a VCD gives one identifier to every name of a net, and the
sampler kept whichever alias was declared first. The port was `rst_ni`, so
the multiplier sat in reset for the whole window. Without the oracle that run
gives a plausible glitch figure from a multiplier that never ran; a port the
dump does not name is an error. A replay runs in **4 seconds an arm**.

| arm | zero delay | annotated | glitch | of annotated |
|---|---|---|---|---|
| the window, 31.8 % duty | 2,717,041 | 3,140,149 | +15.6 % | 13.5 % |
| its busy cycles | 910,432 | 958,348 | +5.3 % | 5.0 % |
| its idle cycles | 1,806,609 | 2,181,801 | +20.8 % | 17.2 % |
| back to back, 100 % duty | 707,551 | 708,989 | +0.2 % | 0.2 % |

**Table 8.** Transitions in the multiplier over 5,001 cycles containing 530
multiplies, and over the same multiplies with the idle cycles removed.

Per multiply that is **90 extra transitions**, per idle cycle **110**.
Reweighted from the window's 31.8 % duty to the 6.92 % the unit has over a
hot iteration, the annotated run makes **19.6 % more transitions than the
zero-delay one**: 16.4 % of what the multiplier switches is switching the
logic did not ask for.

**What it is worth.** The multiplier is 264 µW of ibex's 22.5 mW, 1.17 % of
the core. Scaling its dynamic power by the transition ratio puts the glitch at
**52 µW, 0.23 % of the core's total** -- under a quarter of a percent of the
answer for this core on this workload. That assumes every transition in the
module costs the same energy; OpenSTA reads a VCD directly, so both arms could
be reported against extracted capacitances instead.

**Multiplying is not what makes this multiplier glitch.** Back to back it
glitches 0.2 %, against 20.8 % idle, and makes fewer transitions a cycle
saturated than over a real iteration -- 445 against 532. `RV32MFast` has no
operand isolation: during a multiply the operands hold for three cycles and
only the accumulator moves, while an idle cycle exposes the whole
partial-product array to whatever the ALU buses are doing. The worst case is
idling, the glitch is bounded by the idle figure, and the fix is to gate the
operands rather than speed up the multiplier -- the structure named as the
worst offender offends least when used.

**What this is not.** Inputs arrive at the cycle boundary as recorded, not
staggered as in the core, so what is bounded is the glitch the tree generates
from its own imbalance, not the glitch injected at its boundary, and
interconnect delays are absent throughout; the true figure is higher. It is
one unit, one window, one core, and the figures move with the hardening: on
the pre-re-baseline netlist the same window gave +27.2 % rather than +15.6 %
and +47.4 % rather than +5.3 % on busy cycles, on 3,199 cells rather than
3,206. The conclusion survived and the numbers did not.

### 5.4 A second core, and where that stops

[§5.2](#52-zero-delay-simulation-carries-no-glitch-power)'s threat is that this study under-reports power *differentially*:
deep combinational logic glitches more than a short pipeline, so the bias
distorts the comparison between cores. One unit on one core does not bound
that. This section records an attempt on a second core and why it is not
finished.

**VeeR offered a better experiment than expected.** It has four instances
of `exu_alu_ctl` in one hardening -- same RTL, same chip, same recording --
at 2,250, 2,250, 2,249 and 2,137 cells and 70, 68, 72 and 67 ports, treated
differently by synthesis for context alone. Glitch across those four would
be a *within-design* measurement of [§2.4](#24-when-glitch-power-is-worth-measuring-and-when-it-is-premature)'s claim, without the confounds the
across-re-baseline comparison carries.

**It is not finished.** `exu.i0_alu_e1` replays with no SDF errors and
every stateful cell seeded from the recording, and most outputs reproduce
it digit for digit -- `flush_path` and `pc_ff` match. `out` is X and
`predict_p_ff` differs, so the oracle fails and there is no number.
`GLITCH_RESUME.md` carries the untested hypothesis and what would settle it.

**What the attempt established.** Five defects, each producing a plausible
number rather than an error:

| | what it did |
|---|---|
| memories never initialised | VeeR read locations never written, X reached the fetch path, the core stopped by cycle 20,000 |
| escaped `/` treated as hierarchy | one module appeared to have twenty instances |
| a name matching nothing accepted | an ALU reported busy on 0 of 2,001 cycles |
| names resolved without scope | a unit replayed against a *different instance's* signals |
| flops start X mid-stream | state whose enable never asserts inside the window never resolves |

**Table 9.** Defects found extending the method to a second core.

The fourth is the one worth the detour. A whole-design recording holds four
instances of the same ALU, each with its own `out`, and the sampler took
whichever the dump declared first -- silently. That would have corrupted
the per-unit sweep [§8.9](#89-glitch-power-per-unit-and-per-core) describes, whose premise is recording once and
cutting units out of it, and ibex could not have revealed it because its
recording was scoped to one module. Three of the five are one thing: X out
of uninitialised state, invisible from a two-state simulator. With [§5.2](#52-zero-delay-simulation-carries-no-glitch-power)'s
whole-core annotation failure and the testbench that released reset on a
clock edge, four-state gate-level simulation accounts for every dead end in
this work that was not a tool limitation.

**Why it stopped here.** Each fix revealed another layer, five deep, and
the sixth is when a gated clock first ticks inside a module replayed from
mid-stream -- a simulation-methodology problem, while the study's remaining
uncertainty is [§8.1](#81-cores-after-the-first-four)'s larger cores. The machinery is committed and tested
and the failure characterised; resuming needs one hypothesis tested, not
the chain rebuilt.

**Still unmeasured**: the differential bias [§5.2](#52-zero-delay-simulation-carries-no-glitch-power) names. Glitch is measured
on one unit of one core ([§5.3](#53-glitch-power-in-the-multiplier-measured)), and the claim that it distorts comparison
*between* cores remains an argument. SERV would settle it best -- a
bit-serial datapath should glitch worst of the four -- and is structurally
out of reach: its kept modules are parameterized and do not survive into
the ODB ([§6.2](#62-attribution-does-not-survive-parameterized-modules)), so there is no module boundary to cut.

### 5.5 Estimated, not extracted, parasitics — one point, measured

`estimate_parasitics -global_routing` is a model of the wiring. Switching
power is $\alpha C V^2 f$ and the $C$ here is the estimate's. That is the
cost of screening at global route -- the tail to an extracted design is the
expensive part of a run -- and the received wisdom is that absent
congestion the estimate is close. This section is one measurement of it.

**The experiment is a pair.** Comparing ibex's `6_final` power against the
reported global-route number would move the parasitics model and whatever
detailed route did to the netlist at once. So both numbers are taken on the
*same* `6_final` ODB with the *same* SAIF, and only the parasitics source
differs: the extracted `6_final.spef`, or `estimate_parasitics
-global_routing` on the netlist that SPEF describes.

| ibex, one hot iteration | internal | switching | leakage | total |
|---|---|---|---|---|
| global route, estimated | 15.80 | 3.02 | 0.646 | **19.50 mW** |
| `6_final`, estimated | 15.80 | 3.02 | 0.646 | **19.50 mW** |
| `6_final`, extracted SPEF | 15.80 | **2.69** | 0.646 | **19.10 mW** |

**Table 10.** The parasitics estimate against extraction, on one design.
All three arms are the pre-scaler build of [§8.7](#87-a-memory-model-that-knows-its-size), so the totals are not
Table 1's 22.5 mW; the difference between the arms is unaffected.

**The estimate is wrong by 10.9 % on the term it models and by 2.05 % on
the answer.** It overstates switching -- 3.02 mW against an extracted
2.69 mW -- but switching is 15 % of ibex's total. The 81 % that is internal
is a function of the library's tables and the toggle counts, which the
estimate does not touch.

**Detailed route changed nothing measurable.** The estimated number at
`6_final` equals the estimated number at global route to every digit
reported, so for this design the end-to-end cost of screening early *is*
the parasitics delta.

**The precondition is congestion, and this design has none.** Global route
reports 50.5 % utilization, peak layer usage 16.2 % on M3 and zero
congestion in every direction; detailed route converged to zero violations.
The point confirms the received wisdom in the regime where it is asserted
to hold and says nothing about a congested design, where the estimate has
more to get wrong and is likelier to err the other way.

**What one point is not.** One core, one floorplan, one corner. A design
less internal-dominated would show more of the 10.9 % in its total; SERV
and picorv32 are 78 % and 72 % macro, where the macro's internal energy is
a lookup parasitics do not reach, so the direction is predictable and the
size is not. [§8.6](#86-extract-the-parasitics-on-every-point-not-one) is the sweep that would settle it.

Reproduce:

```sh
bazelisk build //test/coremark_joule/designs/asap7/ibex:cmj_ibex_final_power_extracted
bazelisk build //test/coremark_joule/designs/asap7/ibex:cmj_ibex_final_power_estimated
```

### 5.6 The corner is ASAP7's best case, not its typical

`CORNER = BC` is FF process, 0.77 V, 25 °C ([§3.6](#36-corner-parasitics-and-stage)). Dynamic power scales
with $V^2$, so at the nominal 0.70 V the same activity would give roughly
$(0.70/0.77)^2 \approx 0.83$ of it, about 17 % lower. **That applies to the
whole dynamic term, not only to switching**: on ibex switching is 15 % of
the total against 81 % internal ([§5.5](#55-estimated-not-extracted-parasitics--one-point-measured)), and a correction applied to
switching alone would understate the corner about six times. It is an
estimate either way, since the internal term comes from Liberty tables
characterised per corner; the number itself needs the TT Liberty read and
the power re-reported, which this study has not done. Leakage is higher
again at FF than at TT. The reported Watts are therefore an upper bound
among ASAP7's corners, and [§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not)'s comparison against a typical-corner 22 nm
series is biased against this study's points on that account. All four
cores share the corner, so the comparison between them is unaffected.

### 5.7 Frequency, and what deriving it changed

[§3.8](#38-what-sets-a-cpu-cores-frequency-and-what-the-sdc-must-therefore-say) says what a core's frequency *is*: the reciprocal of its longest
register-to-register path, read from the platform's `reg2reg` path group.
This section is which period is used. Each core's is derived from its own
reg2reg slack by `//test/coremark_joule/scripts:auto_period` -- build, read
the slack, ask for `period - WNS`, build again, and pin the tightest period
that closed. The period is a synthesis input, so every candidate re-runs
synthesis and everything after it.

**Derived against committed periods.** The committed column is the period
each design was scored at before the derivation.

| core | was | derived | error |
|---|---|---|---|
| SERV | 700 ps (1429 MHz) | **438 ps (2283 MHz)** | 60 % too slow |
| picorv32 | 1000 ps (1000 MHz) | **467 ps (2141 MHz)** | 114 % too slow |
| ibex | 1200 ps (833 MHz) | **1296 ps (772 MHz)** | 7.4 % **too fast** |
| VeeR EH1 | 1600 ps (625 MHz) | **1593 ps (627.7 MHz)** | 0.4 % too slow |

**Table 11.** Committed against derived periods. Each core's walk is in its
`auto_period.json`.

**ibex was the serious one.** Its committed 1200 ps was unmet: the netlist
missed it by 73.99 ps on all eight reg2reg paths, and the study reported
833.333 MHz anyway. By [§3.8](#38-what-sets-a-cpu-cores-frequency-and-what-the-sdc-must-therefore-say)'s own rule -- deeply negative means repair gave
up -- the best-scoring core was scored at a frequency it does not reach. It
closed at 1282 ps with 0.50 ps to spare on the first pass, on FakeRAM's
views; the second pass on the scaler's is [§8.4](#84-a-second-period-pass).

**How it was possible.** The reported frequency was a literal in
`sim/BUILD.bazel` and the built period a `set clk_period` in
`constraints.sdc`: one fact declared twice, and nothing compared them.
`cm_per_joule` reads the constraints file, so `auto_period` pins the
period and the reported frequency follows.

**The energy axis barely moved, and that is the result.**

| core | f | power | CoreMark/Joule |
|---|---|---|---|
| SERV | +60 % | +54 % | **+3.5 %** |
| picorv32 | +114 % | +107 % | **+3.2 %** |
| ibex | −6.4 % | −5.3 % | **−1.1 %** |
| VeeR EH1 | +0.6 % | +1.2 % | **−0.6 %** |

**Table 12.** What re-deriving the period did to each point.

picorv32's frequency was wrong by more than a factor of two and its
CoreMark/Joule moved 3.2 %. Dynamic energy per iteration is
frequency-independent -- power rises with $f$ and the iteration takes
proportionally less time -- so only the leakage term moves, and running
twice as fast halves leakage energy per iteration. The ranking is
unchanged. The energy conclusions are robust to the frequency choice, and
the robustness is a measurement rather than an argument.

**What a derived period is not.** It is the tightest period the flow
closed at, on one floorplan, at one corner, with this optimiser. The
floorplan is derived at a period and the period achieved on a floorplan,
so two passes are wanted and one has been run ([§8.4](#84-a-second-period-pass)). And `period - WNS`
from one reading is not the answer: on the first pass VeeR closed at
1591 ps with 10.65 ps of slack, which predicts 1580 ps, and 1581 ps fails.
A slack is what the optimiser had left when it stopped trying, not what it
could deliver if asked.

### 5.8 A predictive kit, not a foundry PDK

ASAP7 is a predictive 7 nm process design kit. Its absolute energy is not a
silicon number, and no claim here should be read as one. Relative
comparisons within the study stand.

### 5.9 Where each core's register file ends up

| core | register file in RTL | hardened as |
|---|---|---|
| picorv32 | inline `reg [31:0] cpuregs [0:31]` array | flip-flops |
| SERV | `serv_rf_ram`: array + read register + x0 gating | flip-flops |
| ibex | `ibex_register_file_ff`, flops by construction | flip-flops |

None of the three converts to an SRAM macro, each for a reason in the RTL.
A memory is converted by blackboxing a module so the Liberty view replaces
its body, which needs a module that is nothing but the memory: picorv32's
is an inline array, SERV's module carries the read register and the x0
gating besides, ibex's is flops by design.

SERV is the one that matters. Keeping the register file in SRAM is its
architectural trick, and measuring it as flip-flops understates it. Getting
the macro means splitting the array into its own module -- a patch on
SERV's RTL, so a change to the design being measured -- and that decision
is recorded here rather than made quietly.

Where a core's register file *is* a module, `AUTO_MEMORIES=1` maps it onto
a generated SRAM view and `memories_applied_test` asserts the macro reaches
the netlist, because a generated-then-ignored macro is a silent wrong
answer. The generated views come from a synthetic memory compiler, so
wherever conversion applies, a memory's contribution to CoreMark/Joule is a
model rather than silicon.

### 5.10 The compiler flag sweep is not wired up

Every point is built with the same flags: `-O3 -funroll-all-loops
-finline-functions -falign-functions=16 -falign-jumps=4`, plus `-march` per
core, `-mabi=ilp32`, `-mstrict-align` because picorv32 and SERV trap
misaligned access, and `-DTOTAL_DATA_SIZE=2000`, on GCC 13.2.0
(`sw/BUILD.bazel`, `sw/elf.bzl`). CoreMark scores are sensitive to compiler
flags -- [11] measured a 2 % swing between two GCC releases on identical
hardware -- and cores compared at different flags would not be a
comparison of cores. No sweep over flags is wired up.

### 5.11 Five placement seeds behind every point

Re-running a point reproduces its digits, because every input is pinned and
the flow is deterministic, but that is repeatability, not uncertainty. The
stage-variance study in this repository (bazel-orfs PR #866) found that
this flow's run-to-run noise is born at placement and propagates through
every later stage, so the quantity a reader needs is how far one design's
power moves when only the placement seed changes.

Each core is placed five times -- the design's own draw, which every audit
and sweep in this paper was run on and which stays the pinned point, plus
`GPL_RANDOM_SEED` 11 through 14 -- from the same synthesis and floorplan,
and each draw goes through the whole chain: global route, netlist,
gate-level CoreMark, SAIF over the same hot iteration, `report_power`. The
spread is reported as 2σ over the five, beside the point in Table 1 and as
error bars on Figure 1.

<!-- seeds -->
| Core | own draw | seed 11 | seed 12 | seed 13 | seed 14 | 2σ CoreMark/J | 2σ / point | 2σ power (mW) |
|---|---|---|---|---|---|---|---|---|
| SERV | 1,013 | 1,015 | 1,013 | 1,015 | 1,015 | ±2 | 0.2 % | ±0.11 |
| picorv32 | 20,926 | 21,038 | 21,001 | 20,926 | 20,926 | ±105 | 0.5 % | ±0.28 |
| ibex | 84,167 | 83,794 | 84,167 | 84,167 | 84,167 | ±333 | 0.4 % | ±0.09 |
| VeeR EH1 | 20,629 | 20,771 | 21,062 | 20,771 | 20,771 | ±317 | 1.5 % | ±2.19 |
<!-- /seeds -->

**Table 13.** Every draw of every core. The spread is small: SERV 0.2 %, picorv32 0.5 %, ibex 0.4 %, VeeR EH1 1.5 % of the point. `report_power` prints three significant figures, so a point near 20 mW is quantised at 0.1 mW; ibex's five draws span that last digit, so its 2σ is the report's resolution, and the other three resolve above it. The seeds change the placement, wires, buffering and clock tree, not the SAIF's activity, which is a property of the RTL, so wire and clock power move and the macro column stays put.

Two points whose gap is inside the larger of their 2σ are not different, and one of Table 1's gaps is. The smallest gap in the table, VeeR to picorv32, is 1.4 % of the smaller point, against a 2σ of 1.5 % on VeeR, so VeeR and picorv32 are not different at this resolution: the pipelined core with a real L1 and the multi-cycle core with a tightly-coupled memory tie on energy, on this memory model. Every other gap is at least 4x and no seed spread reaches it. At five runs per arm the resolvable difference between two points is $2\sigma\sqrt{2/5}$, and a difference inside it is *did not resolve*, never *no effect*.

---

## 6. What the flow got wrong

Five defects in the flow that this study happened to hit, each applying to
designs that have nothing to do with CoreMark. Four were silent -- a
plausible number, an empty report, a frequency that could not be measured.
The two in [§6.5](#65-two-carried-workarounds) were not, by luck rather than design: `write_verilog`
emitted a netlist Verilator refused, and `read_saif` stopped at a name its
lexer could not hold; a more tolerant reader would have reported a number
from a design that was never simulated. [§6.3](#63-the-io-budget-and-what-the-platform-default-cost) is the widest: every ORFS
design that does not override the platform's IO budget carries it.

### 6.1 The SAIF's time base has to be the SDC period

A SAIF records real time, and OpenSTA reads it as transitions divided by
duration. So the period the simulator times a capture with has to be the
period the design is built at, or every toggle rate -- and the dynamic
power with it -- is wrong by the ratio.

It was wrong, between two commits of this study. The simulator's period
was a literal in `sim/BUILD.bazel` carrying a comment that it must equal
the SDC's, and [§5.7](#57-frequency-and-what-deriving-it-changed)'s derivation re-pinned every SDC without touching it.
SERV's activity was measured against a 700 ps clock it no longer had (it
ran at 438) and picorv32's against 1000 ps (it ran at 467): rates low by
1.60x and 2.14x.

**It cost far less than those ratios.** Only combinational switching rides
on data-pin densities; a sequential cell's internal power is dominated by
its clock pin, a macro's by its own, and OpenSTA takes both from the SDC at
$2/\mathrm{period}$ ([§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator)). So the error reached 4 % of picorv32's total
and moved its reported power by 2.9 %. The same mechanism is why nothing
looked wrong: the macro column, 66 to 78 % of every point, scaled correctly
with the new periods while a smaller term underneath stayed at the old
clock.

The fix is [§5.7](#57-frequency-and-what-deriving-it-changed)'s: one reader of `set clk_period`, called by the SAIF's
time base, the reported frequency and the period tuner alike.

### 6.2 Attribution does not survive parameterized modules

The per-unit breakdown works only for designs whose kept modules are
unparameterized, and the failure is silent: the flow completes, the netlist
is valid, and the breakdown comes back empty. `power_units_grt.tcl` prints
the module-instance count for that reason, and `hier_probe` says at which
stage the hierarchy was lost.

SERV is the case that matters. Its kept modules are all parameterized, so
yosys names them `$paramod\serv_alu\W=s32'...`; all thirteen are present in
`1_2_yosys.v`, but the global-route ODB has zero module instances and the
written netlist is one flat module. picorv32's plainly named
`picorv32_pcpi_mul` and `picorv32_pcpi_div` survive with hierarchical
paths.

Renaming the kept modules during synthesis is warned against in
`synth_canonicalize_module.tcl`: OpenROAD's macro placement and the parent
netlist's instance references use the canonical names, and renaming in the
module partition alone would desync the two. De-uniquifying at the
reporting layer, the established pattern for mangled names, does not
rescue SERV, whose instances are absent rather than mangled. A consistent
rename across the whole merged netlist, definition and instantiation
together, is the candidate fix, untried.

This affects [§3.7](#37-functional-unit-attribution)'s breakdown only, not Table 1, Table 3 or Table 4, which
are whole-design numbers.

### 6.3 The IO budget, and what the platform default cost

What the platform's default IO budget was worth, measured on three designs
before [§4.2](#42-what-the-boundary-costs) at the core-only boundary.

`$PLATFORM_DIR/constraints.sdc` on ASAP7 constrains every
input-to-register, register-to-output and input-to-output path with
`set_max_delay`, and **defaults each to 80 ps** when the design does not
override it -- a figure its own comment calls right for "a small macro on
ASAP7". The study's `constraints.sdc` for picorv32, SERV and ibex set only
the clock period, so all three inherited it: at 1000 ps a twelve-fold
over-constraint on every path touching a port. An optimiser given an
impossible target upsizes cells and inserts buffers trying to reach it, and
those cells draw power that is attributed to the core.

**All four designs set the budget** -- `in2reg_max` and `reg2out_max`
at 0.8 of the period, `in2out_max` at 0.6, ORFS's own ratios -- and the
three measured cores were re-run:

| core | P at 80 ps | P budgeted | delta | CoreMark/Joule |
|---|---|---|---|---|
| SERV | 6.640 mW | 6.680 mW | **+0.6 %** | 5,222 → 5,190 |
| picorv32 | 6.580 mW | 6.430 mW | **−2.3 %** | 84,063 → 86,024 |
| ibex | 7.770 mW | 7.370 mW | **−5.1 %** | 263,224 → 277,510 |

**These columns are measured at the core-only boundary** and are left as
taken. The quantity the experiment isolates is the delta; re-running it
against tiles whose power is 66 to 78 % memory would measure a smaller
relative effect for a reason unrelated to the IO budget. The CoreMark/Joule
figures in the last column are superseded by Table 1. CoreMark/MHz is
unchanged in every case, as a cycle count must be.

**The error scales with the port count**, as the mechanism predicts. SERV's
interface is one bit wide and barely moved -- the wrong way, since removing
an over-constraint frees the optimiser to spend its effort elsewhere.
picorv32 has a 32-bit bus; ibex has the widest interface and lost the most.
That it is differential is what mattered: it was distorting the comparison
between cores. Its size on a design with many more ports -- VeeR has some
six hundred -- is not measured, and the trend does not suggest it is
smaller.

`check_sdc.py` makes this a checked property: every design SDC must state
all three budgets and use neither `set_input_delay` nor
`set_output_delay`. It is a non-manual test, because what it guards is
silent in every report downstream.

Two reasons the override matters, separate from its consequences:

- `set_max_delay` rather than `set_input_delay`/`set_output_delay` is the
  platform's deliberate choice, and the argument is good: `set_input_delay`
  is relative to the clock insertion point, so it cannot be written down
  without assuming a clock tree that does not exist yet.
- Because `set_input_delay` is not used, **no hold cells are inserted on IO
  paths**. On a design with VeeR's port count that is a large amount of
  area and leakage that would otherwise be charged to the core.

### 6.4 VeeR's clock gates, and what mapping them cost

VeeR builds its clock gating in RTL. `beh_lib.sv` defines `` `TEC_RV_ICG ``
as a transparent-low latch and an AND --

```systemverilog
always @(CP, enable) if (!CP) en_ff = enable;
assign Q = CP & en_ff;
```

-- and `rvclkhdr`/`rvoclkhdr` instantiate it. The macro names the
definition and the instantiation together, so the module cannot be
redirected from outside the sources. (`PHYSICAL` guards `rvdffe`'s generate
block, not the gate definition.)

Left alone, VeeR's global-route netlist contained **952 latch cells**
(`DLLx1` ×951, `DLLx2` ×1) and **zero ICG cells**, though ASAP7 ships ten.
**It showed up first as timing.** `flow/period_probe.tcl` returned eight
reg2reg paths with slack exactly 0.000000, every one ending at a latch D
pin inside a clock gate
(`...lsu_freeze_c2dc1_cgc.clkhdr.en_ff$_DLATCH_N_/D`): what a
latch-terminated path looks like when time borrowing is unconstrained.

**The substitution has to happen after elaboration and before flatten.**
yosys's `synth -extra-map` runs inside the techmap step, after every
instance has been inlined, so `patches/0068` adds
`SYNTH_POST_HIERARCHY_SCRIPTS`, a design-supplied yosys script run
immediately after `hierarchy`. It cannot be a plain techmap file either:
the slang frontend elaborates one module per instance and names each after
the instance path (`\clockhdr$swerv_wrapper.mem.free_cg.rvclkhdr` and ~100
siblings), so nothing has type `clockhdr` and a bare `techmap -map` matches
nothing while reporting success. `chtype` folds the uniquified names back
onto one first. `flow/cmj_veer_icg.ys` is four lines and
`flow/cmj_veer_icg_map.v` maps VeeR's port names (`TE`, `E`, `CP`, `Q`)
onto ASAP7's (`SE`, `ENA`, `CLK`, `GCLK`).

**What it moved.** 1,066 `ICGx1_ASAP7_75t_R` cells, zero latches, design
area 60,226 → 60,243 µm² (+0.03 %): a real clock gate costs what a latch
and an AND cost.

| | before | after |
|---|---|---|
| clock power | 26.80 mW (30.7 %) | 25.20 mW (29.5 %) |
| total power | 87.30 mW | 85.51 mW |
| CoreMark/Joule | 34,349 | 35,072 |
| reg2reg slacks | 8 × 0.000000 ps, latch D pins | 9.68 … 28.96 ps, flop D pin |
| derived $f_\mathrm{max}$ | not measurable | 628.8 MHz |

**Table 14.** VeeR before and after its clock gates were mapped onto the
library's ICG cell, both at 1600 ps rather than the derived period ([§5.7](#57-frequency-and-what-deriving-it-changed)):
a like-for-like comparison of the change, not the study's reported
numbers.

The energy effect is 2.1 %: [§4.7](#47-where-the-power-goes) puts 75 % of VeeR's power in the macros,
and the clock group is dominated by the tree driving thirty thousand flops
and twenty-eight SRAM macros rather than by a thousand gating cells. [§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model)'s
conclusion rests on the macro column and does not move. **The timing effect
is the one that mattered**: eight distinct slacks ending on a flop
(`swerv.ifu.bp/bht_dataoutf.genblock.dff.dout[5]` `$_DFF_PN0_/D`) replace
eight zeros ending in latches, so VeeR's reg2reg slack is a measurement the
period derivation ([§5.7](#57-frequency-and-what-deriving-it-changed)) can read.

**Three side effects, none intended.** A gated clock is a clock net the
tree is built on, so the clock network grew by about 160 pins of the kind
[§4.3](#43-annotation-completeness-and-the-estimator-bound)'s budget concedes, pushing VeeR's unmatched fraction on Table 14's
build from 0.986 % to 1.0128 % against a budget of 1.1 % (1.0073 % at the
reported point, Table 3), with that reason written into `pin_policy.json`.
On that build the SAIF filter dropped 9,223 clock-network names rather than
5,284 (9,320 on the pinned netlist, [§6.5](#65-two-carried-workarounds)). And [§6.5](#65-two-carried-workarounds)'s first workaround still has something to rename:
`write_verilog` emits the collision on the ICG netlist too, between two
`ICGx1` cells, and the four pins it costs are waived by name in
`pin_policy.json` ([§4.3](#43-annotation-completeness-and-the-estimator-bound)).

### 6.5 Two carried workarounds

VeeR is the first design in the study with hardened macros and a
hierarchical ODB, and getting a number out of it needed two workarounds,
carried here rather than reported upstream per the moratorium in
`CLAUDE.md`. Both cost the measurement something, and the cost is measured.

**A duplicate instance name in the written netlist.** OpenROAD's
`write_verilog` gives two different cells the same name inside one
hierarchical module, which is not valid Verilog. On the pinned VeeR netlist
it is one collision: the clock-header latch
`ifu_fetch_addr_f2_ff.genblock.clkhdr.clkhdr.latch` inside
`ifu_mem_ctl$swerv_wrapper.swerv.ifu.mem_ctl` appears twice, once for the
cell CTS placed and once for the resizer's clone. odb's instance namespace
is unique per block, so the collision is created on the way out: the name
mapping in `write_verilog` is not injective. Verilator rejecting it is the
good outcome; **a reader that accepted it would keep one of the two and
simulate a design the power was not reported on.**
`scripts/uniquify_netlist.py` renames rather than drops, and runs on every
core: the three cacheless cores carry a budget of zero, asserting no
collisions, and VeeR a budget of four, which its five placement draws
([§5.11](#511-five-placement-seeds-behind-every-point)) meet at zero or one rename each. Cost: a renamed instance's pins
carry a name the SAIF cannot match, so every pin of a renamed cell goes
unannotated -- four on the ICG netlist -- and [§4.3](#43-annotation-completeness-and-the-estimator-bound)'s audit counts them.

**Net names a SAIF cannot carry.** OpenSTA's SAIF lexer defines
`ID ([A-Za-z_])([A-Za-z0-9_$\[\]\\.])*` and `HCHAR "."|"/"`, so `/` is the
hierarchy separator and cannot appear inside a name, and an ID cannot begin
with a backslash, so no escaped spelling exists. Hierarchical CTS names
leaf clock nets after their sink's full path, which contains odb's own `/`:

    clknet_1_0__leaf_swerv.ifu.bp/BTB_FLOPS[39].btb_bank1_way1...clkhdr.Q

`read_saif` stops at the first such line with a parse error, having
annotated **nothing** -- and had it not errored, `report_power` would have
run on default activity and produced a number nothing downstream could
distinguish from a measured one (63.5 mW vectorless, for scale).
`scripts/filter_saif.py` drops only the entries the format cannot carry and
classifies every one. On the pinned VeeR netlist: **9,320 clock-network
names** (`clknet_*`, `clkbuf_*`) and **one** it cannot classify by name,
`clonenet_1_swerv.ifu.mem_ctl/ifu_fetch_addr_f2_ff.genblock.clkhdr.l1clk`,
the output of the cloned clock header the rename above is about. [§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator)
establishes this is the benign case: OpenSTA gives clock-network pins
$2/\mathrm{period}$ from the SDC exactly, so being unannotated is their
correct state and the pin audit classifies them `clock_network`. The budget
on non-clock drops is zero by default; VeeR declares four, with the reason
in its `BUILD`, and every draw uses one or none.

**Both are properties of the hierarchical flow**, which OpenROAD itself
warns about (`ORD-0012`, "in development"). The study keeps hierarchy
because [§3.7](#37-functional-unit-attribution)'s attribution needs it. Before either is reported upstream,
OpenROAD's history should be read: it has carried fixes in this area
before -- name escaping, the `-hier` flow -- so a bump may be cheaper than
a report.

## 7. Related work

*Ramping Up Open-Source RISC-V Cores* [5] evaluates CVA6, CVA6S+ and the
XuanTie C910 in GF 22 FDX with PrimeTime on post-layout netlists at a
stated typical corner. Its method is the standard [§5](#5-threats-to-validity) measures this study
against, and [§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not) says why its points are drawn as a separate series. *The
Cost of Application-Class Processing* [6] is the reference for
silicon-measured energy in the same technology family; [§4.5](#45-what-else-could-be-plotted-and-why-almost-nothing-can) records that
its full text was not surveyed, so what boundary it draws is not
established.

The studies nearest in method are [§4.5](#45-what-else-could-be-plotted-and-why-almost-nothing-can)'s near misses. [12] and [13] measure
CoreMark energy on three and two small cores with PrimeTime in 65 nm; [14]
measures seven cores, three of them this study's, on MachSuite kernels at
subthreshold in a commercial 130 nm process; [15] compares seven cores and
reports CoreMark iterations/mJ on an "ASIC prototyping platform" read here
as an FPGA, where the Joules belong to the fabric. [§4.8](#48-cross-checks-against-the-nearest-published-studies) checks this study's
numbers against the first three.

EEMBC defines both halves of the metric: CoreMark [1] the performance
benchmark and its run rules, ULPMark-CoreMark [2] the energy metric as
CoreMark iterations per milli-Joule, the quantity this study reports per
Joule. ULPMark-CM is measured on silicon at a stated supply voltage, which
no pre-silicon flow can claim; the naming follows it, the certification
does not.

The estimator theory [§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator) rules out is Najm's [3, 4]: signal probability
and transition density propagated forward through Boolean functions, cheap
and blind to reconvergent-fanout correlation. The practice [§5.2](#52-zero-delay-simulation-carries-no-glitch-power) is missing
is the SDF-annotated, event-driven capture signoff power flows use [7, 8].

---

## 8. Further work

Four points at one operating point on one node become a comparison an
architect or an EDA researcher could cite with more cores and more
measurement, set out below in the order the harness makes cheapest: [§8.1](#81-cores-after-the-first-four)
is the roadmap of cores, [§8.2](#82-deep-physical-metrics) onward everything else. [§8.4](#84-a-second-period-pass) has run once,
[§8.7](#87-a-memory-model-that-knows-its-size)'s generator exists, [§8.9](#89-glitch-power-per-unit-and-per-core)'s per-unit replay is built and tested with
its blocker characterised, and the rest is not started.

### 8.1 Cores after the first four

The first four establish the low end and the edge of the band. The
interesting region is 5–15 CoreMark/MHz, populated only by large
out-of-order cores: the x-axis spans about three decades and the cost of a
point grows with it, so the shape is earned cheaply at the bottom and
extended deliberately upward, each core its own budgeted run.

| # | core | CoreMark/MHz | HDL | practical pain |
|---|---|---|---|---|
| — | SERV / picorv32 / ibex | 0.02 / 0.55 / 2.45 | Verilog / Verilog / SV | done |
| 4 | CV32E40P | ~3.1 | SystemVerilog | low |
| 5 | VeeR EL2 | ~2.6 | SystemVerilog | low |
| 6 | CVA6 | ~2.5 | SystemVerilog | medium — RV64 contrast at similar CoreMark/MHz |
| 7 | **VeeR EH1** | **4.798 measured** (4.94 published [11]) | SystemVerilog | **done** |
| 8 | OpenC910 | ~4.9–7 | Verilog/SV | medium — 3-issue OoO, silicon-proven |
| 9 | SonicBOOM | 6.2 | Chisel | high — pulls in the Scala generator |
| 10 | **XiangShan (Kunminghu V3)** | **8.29 measured** | Chisel | **in flow — [§4.9](#49-the-literature-side-by-side-and-the-discrepancies-worth-chasing) has it against its publications** |

**Rungs 8–10 arrive with an L1 each**, as tiles or SoCs, and what gets
hardened stops being obvious. [§3.1](#31-the-measurement-boundary)'s boundary is what makes them
comparable with the four points here: without it the three cacheless
points overpredict VeeR by 15.2x, with it by 7.88x ([§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model)), and a rung
added alongside points measured without their memories inherits that
error.

**VeeR EH1 is wired from its own upstream** at a pinned commit through the
module graph, not from the sv2v-flattened copy ORFS vendors as
`swerv_wrapper`, whose configuration is baked in and unrecorded. The
configuration is generated once from upstream's generator and committed as
a defines header with its provenance, so the core simulated and the core
hardened cannot differ. Western Digital's published 4.94 CoreMark/MHz [11]
was taken with a 64 kB ICCM and the instruction cache off; this study
keeps their 512-entry BTB and 2048-entry BHT and swaps the ICCM for the
16 kB instruction cache, because the ICCM has no load path a gate-level
netlist can use and the cache is the L1 [§3.1](#31-the-measurement-boundary) measures. The configuration,
the two slang flags the RTL needs, and what was taken from ORFS's design
are in `designs/asap7/veer/README.md`.

**Measured here: 4.798 CoreMark/MHz** (208,425 cycles per iteration,
CoreMark's three CRCs correct on the gate of [§3.2](#32-the-chain)). Against Western
Digital's own numbers on the same core:

| source | CoreMark/MHz | compiler | instruction memory |
|---|---|---|---|
| Western Digital [11] | 4.94 | GCC 7.2.0 | 64 kB ICCM |
| Western Digital [11] | 4.84 | GCC 8.2.0 | 64 kB ICCM |
| **this study** | **4.798** | GCC 13.2.0 | **16 kB L1 instruction cache** |

Three per cent below their best figure, and below both, in the direction
each difference predicts: their own GCC 7.2 → 8.2 step cost 2 % on
identical hardware, this build is five major releases further on, and the
remaining gap is the cache paying for misses an ICCM does not have. Three
figures within 3 % across two memory systems and three compiler
generations is the strongest end-to-end evidence the harness has produced:
the chain measures this core the way its authors measured it. The
difference between 4.798 and 4.94 is a property of the memory
configuration and the compiler, not evidence about the core.

**CoreMark fits in the L1, measured.** The SoC wrapper counts transfers on
both external buses, taken like the cycle count as the difference between
a two-iteration and a three-iteration run, which cancels the boot, the
`.data` copy and the cold pass that fills the cache.

| counter | during boot | added by one hot iteration |
|---|---|---|
| instruction bus | 2,788 transfers (22.3 kB) | **0** |
| load/store bus | 934 transfers (7.5 kB) | **0** |

Zero on both buses over 208,425 cycles: every fetch is served by the 16 kB
instruction cache and every load and store by the 64 kB DCCM. The 2,788
boot transfers are the 24 kB of `.text` streamed in once as cold misses,
the 934 the `.rodata`/`.data` copy plus the report's characters, all
before the measured window. This was the first point where [§3.1](#31-the-measurement-boundary)'s boundary
was **verified**, and [§4.2](#42-what-the-boundary-costs) has since done the same for the other three.
The boot traffic is carried in the result, because zero steady-state
traffic and a bus that never worked look identical in a difference.

The same caution about vendored RTL applies to the other ORFS designs in
this family. `asap7/cva6` would be the direct counterpart to [§4.4](#44-a-22-nm-literature-series-and-what-it-is-and-is-not)'s 22 nm
series -- the same core at a different node on a different toolchain --
and `asap7/tinyRocket` a fourth; in each case the study can take the
platform-side work, not the vendored RTL. Rungs 4–8 need no generator
toolchain; rungs 9–10 pull in Chisel, the natural place to stop if the
study stops early.

### 8.2 Deep physical metrics

Area and $f_\mathrm{max}$ are the headline numbers; a physical designer
wants the architecture's physical health, which those two hide.

- **Congestion and wirelength.** A large out-of-order core often suffers
  around the reorder buffer and the renaming logic, and a core that routes
  cleanly there says something about how its RTL is structured. OpenROAD
  produces the congestion map; the work is to capture it per core at a
  comparable utilisation and put the images side by side.
- **Standard-cell utilisation limits.** The highest utilisation the router
  could still close at. A core that routes at 75 % against one that fails
  above 55 % is a physical difference no area number expresses; the
  harness's floorplan derivation already races candidates and is the place
  to find it.
- **SRAM against logic.** High-IPC cores demand large caches, so a figure
  that does not separate them cannot distinguish a bloated datapath from a
  provisioned memory. The breakdown wanted is logic/datapath, control and
  SRAM/macros. [§3.7](#37-functional-unit-attribution)'s kept-module machinery attributes power this way; the
  macros need adding, which [§4.2](#42-what-the-boundary-costs)'s boundary work supplies.
- **Dynamic against leakage**, reported at the target $f_\mathrm{max}$.
  [§5.7](#57-frequency-and-what-deriving-it-changed) says why this is not cosmetic: dynamic energy per iteration is
  roughly frequency-independent and leakage energy per iteration is not,
  so a single total hides a term that moves with the operating point.
  Table 1 carries the split; what it lacks is a leakage number worth
  reading, because the scaler's leakage anchor puts it near zero on every
  point ([§5.1](#51-the-memory-model-and-the-memory-this-study-chose)).

### 8.3 More than one node

A microarchitecture can look excellent on an older node, where delay is
logic-dominated, and come apart on a FinFET node where wire resistance
dominates timing. One node proves nothing about the other.

- **ASAP7**, the predictive 7 nm kit this study uses, makes a result
  relevant to a modern commercial architecture, with [§5.8](#58-a-predictive-kit-not-a-foundry-pdk)'s caveat.
- **A 130 nm open node**, sky130, alongside it, so the design stays
  accessible to academic researchers and open multi-project-wafer
  shuttles, and so the node sensitivity is visible rather than assumed.

**The 130 nm series stops at 5 CoreMark/MHz, by decision.** Above that a
130 nm implementation costs far more area, wirelength and run time than
the comparison returns. Both nodes up to and including 5 CoreMark/MHz,
ASAP7 alone above it; where the two series overlap is where a
node-sensitivity claim can be made.

### 8.4 A second period pass

Each core's period is derived on its committed floorplan ([§5.7](#57-frequency-and-what-deriving-it-changed)). The
floorplan is derived at a period and the period achieved on a floorplan,
so both halves want a second pass.

**The period half has been run**, as part of the re-baseline that switched
the memory model ([§8.7](#87-a-memory-model-that-knows-its-size)): on the scaler's views, at unchanged floorplans,
the tuner re-probed every core from its first-pass period and pinned what
closed. Every probe is a full flow to global route and a `report_checks`
over the register-to-register paths.

| core | first pass | probes | second pass | moved |
|---|---|---|---|---|
| SERV | 438 ps | 438 closes (+11.05 ps); 427 fails (−0.29 ps) | **438 ps** | 0 |
| picorv32 | 467 ps | 467 closes (+13.89 ps); 454 fails (−21.77 ps) | **467 ps** | 0 |
| ibex | 1282 ps | 1282 fails (−1.54 ps); 1284 fails; 1294 fails (−1.67 ps); 1296 closes (+2.84 ps) | **1296 ps** | +14 ps (1.1 %) |
| VeeR EH1 | 1591 ps | 1591 fails (−1.82 ps); 1593 closes (+0.21 ps) | **1593 ps** | +2 ps (0.1 %) |

**Table 15.** The second period pass. ibex and VeeR no longer closed at
their first-pass periods on the scaler's views and paid 14 and 2 ps; SERV
and picorv32 kept theirs to the picosecond. The likely cause is the views
themselves -- the scaler's Liberty carries each shape's own timing arcs
where FakeRAM's carried one figure for every shape -- but the critical
paths were not inspected. The evidence is each design's
`auto_period.json`.

The walk is not monotone, which is why the loop pins a period it measured
rather than one it computed: ibex closes at 1296 ps with 2.84 ps of slack
after failing 1294 by 1.67 ps, and picorv32 fails 454 by 21.77 ps after
closing 467 with 13.89 ps to spare, because an optimiser stops trying when
it meets a target and tries harder when it does not.

**The floorplan half has not.** Re-deriving each floorplan at its derived
period on the new views found no DRC-clean candidate at any utilization,
because the scaler's LEF drew its pins at one track pitch on a layer whose
width is half that. The LEF is fixed (`tools/memory_macro_scaler`
draws fakeram7's geometry, and every tile routes clean through detailed
routing), and the incumbent floorplans stand until the derivation is
re-run on it.

A derived period is one number from one flow, not a Pareto front ([§8.5](#85-the-pareto-curve)).

### 8.5 The Pareto curve

The most useful graphic this study does not yet have, and the one that
follows most directly from what it builds. Sweep the target clock period
from comfortable to the point of timing failure and plot frequency against
area and against power, every core on the same axes. `orfs_sweep` already
races period candidates, and [§5.7](#57-frequency-and-what-deriving-it-changed)'s tuning is the same machinery seen from
the other side: what tuning treats as a search, this treats as the result.

What the curve shows that a point cannot is **the cost of speed**: where
each core enters diminishing returns, the wall at which the tools upsize
cells wholesale and burn disproportionate power to buy another ten
megahertz. Two cores with the same headline $f_\mathrm{max}$ can sit on
very different curves, and which is on the better one is the
architectural question. Plotting this study's cores with a large
out-of-order core such as XiangShan is what would make the comparison
definitive.

### 8.6 Extract the parasitics on every point, not one

[§5.5](#55-estimated-not-extracted-parasitics--one-point-measured) measures the parasitics estimate against extraction on ibex:
switching overstated by 10.9 %, the total by 2.05 %, on a design with no
congestion. The two things one point cannot tell are the two worth
knowing.

**How it scales with the macro fraction.** The delta lands on switching
power, 15 % of ibex's total and a smaller share of SERV's and picorv32's at
78 % and 72 % macro. A macro's internal energy is a Liberty lookup no
wiring model reaches, so the total delta should *shrink* as the macro
fraction rises: predictable in direction, unmeasured in size.

**What congestion does to it.** The received wisdom is conditional on the
absence of congestion, and ibex has none. A design that routes hard is
where an estimate has the most to get wrong, and this study has no such
point.

The work is a `stage_power(spef = ...)` target per core against its
existing one: four flow tails, hours rather than minutes, which is why it
is here and not in [§5.5](#55-estimated-not-extracted-parasitics--one-point-measured). Worth pairing with a deliberately congested
variant of one core, since four uncongested designs would re-measure the
same regime four times.

### 8.7 A memory model that knows its size

Applied. `tools/memory_macro_scaler` emits Liberty views whose read
energy, write energy and leakage are fitted to the memory's rows and bits
after CACTI's access-path decomposition, where FakeRAM2.0 emitted one
number for every shape. Every memory in the study -- the instruction and
data memories of the cacheless tiles, VeeR's DCCM banks and cache arrays,
and the `ibex_icache` variant's tag and data arrays -- is one behavioural
module in `rtl/cmj_sram_models.sv`, which the simulators read for the
gate-level runs and the scaler reads for the views, so the two cannot
disagree about a shape. [§5.1](#51-the-memory-model-and-the-memory-this-study-chose) reports what the switch moved. It was done as
one re-baseline with [§8.4](#84-a-second-period-pass)'s second pass and [§5.11](#511-five-placement-seeds-behind-every-point)'s repeats, so every
number in the paper moved once.

What it did not do: the scaler's Liberty charges the read-write energy on
every clock edge regardless of the enable ([§4.7](#47-where-the-power-goes)), and its fit is a
first-order anchor with about 25 % residuals on SRAM area. A characterised
memory compiler for ASAP7 would retire both; none is open.

### 8.8 Reproducing a published CoreMark/MHz to the instruction

The study trusts a published CoreMark/MHz and then verifies it: VeeR's
4.798 against Western Digital's 4.94 ([§8.1](#81-cores-after-the-first-four)) is the chain measuring the
core the way its authors did, to 3 %. A failure to reproduce is not
automatically the core's fault or the publisher's; it can be the
compiler's: [11] measured a 2 % swing between two GCC releases on identical
hardware, and the remaining VeeR gap is GCC 13 against GCC 7 plus a cache
in place of an ICCM.

The sensitivity grows with the score. CoreMark/MHz is $1/T$ for the cycles
$T$ one iteration takes, and at ten CoreMark/MHz an iteration is about a
hundred thousand cycles, so a handful of instructions the compiler did or
did not remove from the hot loop is a visible fraction. A core in the
10–15 range reproduced to within 3 % needs the same code its publisher
ran, not merely the same source.

When a reproduction misses, the compiler can be taken out of the
comparison. Published figures are taken with compilers this study rarely
has -- a vendor GCC 7 in VeeR's case -- and the workaround is to replicate that compiler's output:
vendor the assembly it produced where the publisher provides it, or take
this study's compiler's assembly and apply the decisions the published
build made -- the unrolling, inlining and scheduling `objdump` of a
published binary shows -- until the published cycle count is reproduced,
with every difference listed. It is valid because the quantity under test
is the core's cycle count on a given instruction stream, not the
compiler's skill at producing it, and it is the way to take any published
figure before trusting a measured one. Two rules go with
it: the build from this study's own toolchain stays in the table as the
number the flow produces unaided, and the replicated stream is checked
against CoreMark's Acceptable Use Agreement ([§11](#11-licensing)), which forbids the
trademark on a modified copy of the Software, before it is committed.

### 8.9 Glitch power per unit, and per core

[§5.3](#53-glitch-power-in-the-multiplier-measured) measures one unit of one core and [§5.4](#54-a-second-core-and-where-that-stops) says why there is not yet a
second. The shape that would finish it is a sweep: `units.json` names the
preserved modules per design, each replays in seconds off one shared
recording, and the expensive half -- the zero-delay whole-design run, 35
minutes for ibex and nearly two hours for VeeR -- is paid once per design
and cached. A bazel target would fan the units out in parallel and re-run
only the ones whose inputs moved.

It would give the first core-wide figure, reported as a lower bound: a sum
over units cannot see the glitch injected *between* them by staggered
arrival at their boundaries, where a good deal of real glitch lives. It
would not give the differential bias across cores [§5.2](#52-zero-delay-simulation-carries-no-glitch-power) names, because SERV
-- the core whose bit-serial datapath should glitch worst -- has no module
boundary to cut ([§6.2](#62-attribution-does-not-survive-parameterized-modules)).

The obstacle is [§5.4](#54-a-second-core-and-where-that-stops)'s open question about when a gated clock first ticks
in a module replayed from mid-stream, which every unit with un-reset state
will meet. `GLITCH_RESUME.md` carries the chain, the measured costs and
the hypothesis to test.

## 9. Conclusion

Four RISC-V cores, hardened on ASAP7 and measured for CoreMark/MHz and
CoreMark/Joule at global route with activity from one hot CoreMark
iteration, spanning 198x in performance per clock and 83x in energy
efficiency. Three things to take from it, one a warning about the metric.

**The boundary is most of the answer, and it is checkable.** Measuring
core + L1 -- or the memory a cacheless core runs out of -- rather than the
core alone costs the small cores between 3.3x and 5.1x of their
CoreMark/Joule at unchanged CoreMark/MHz, and compresses ibex's lead over
VeeR from 13.45x to 4.08x ([§4.2](#42-what-the-boundary-costs)). The boundary is verified: every tile
counts the transfers that cross it, and for all four cores one hot
iteration sends zero. **A CoreMark/Joule quoted for a small core without
saying whether its memory was measured is uninterpretable at roughly an
order of magnitude**, wider than the difference between most cores anyone
would want to compare.

**A power report does not tell you whether it measured anything.** OpenSTA
estimates an unannotated pin rather than failing, and labels the result
"Total". Enumerating every pin, classifying every one the SAIF did not
reach, and sweeping the default activity across its whole range shows the
estimator contributing nothing: the SAIF-driven total is bit-identical at
ten significant figures while the same sweep moves the vectorless total by
21 to 144 % ([§4.3](#43-annotation-completeness-and-the-estimator-bound)). That check, not the number, is the part of this study
most worth copying.

**CoreMark/Joule is not yet a discriminating axis among cores of this
class.** Across a 101x span in performance per clock the three cacheless
cores' $f/P$ spans 1.22x, so the energy axis is close to the performance
axis in disguise ([§4.6](#46-is-the-shape-real-the-boundary-and-the-memory-model)). The reason is mechanical: the macros are 66 to
78 % of every point, and every core runs the same benchmark out of the
same fitted memory model. What would make the axis mean something is a
characterised memory compiler, cores whose memory systems genuinely
differ, and [§8.5](#85-the-pareto-curve)'s Pareto sweep that measures the cost of speed as a
curve. The flow to do all three is here and re-runs with one command.

## 10. Running it, and adding your own core

Everything in this directory is `tags = ["manual"]`, so nothing here is
pulled in by a wildcard build. The parsers, the number checks and the SDC
model test are not manual and run in CI; the flow targets last ran against
the commit that last touched this directory.

### 10.1 Re-running the study

```sh
# the cheap gates: every parser and every check, over fixtures (seconds)
bazelisk test //test/coremark_joule/scripts/...

# the prose against the pinned numbers: Table 1 and every quoted ratio
bazelisk test //test/coremark_joule/scripts:readme_numbers_test

# does the core boot and get a load/store right?
bazelisk test //test/coremark_joule/sim:smoke_picorv32_rv32im_test
# does CoreMark compute the right answer on it?
bazelisk test //test/coremark_joule/sim:picorv32_rv32im_crc_test

# the whole table, building every measurement it reports
bazelisk run //test/coremark_joule/sim:report

# annotation completeness, per core
bazelisk build //test/coremark_joule/designs/asap7/picorv32:cmj_picorv32_grt_activity_audit
# the estimator bound, per core
bazelisk build //test/coremark_joule/designs/asap7/picorv32:cmj_picorv32_grt_activity_sweep_check
# the boundary, per core: zero transfers per hot iteration
bazelisk build //test/coremark_joule/sim:picorv32_rv32im_bus_traffic

# §4.8's cross-check: ibex at synthesis, three periods, beside the published rows
bazelisk build //test/coremark_joule/designs/asap7/ibex:ibex_synth_crosscheck

# re-measure and rewrite the pinned results; then the plot, with no flow in the loop
bazelisk run   //test/coremark_joule:pin
bazelisk build //test/coremark_joule:plot

# A.1's commodity table against the exports it was built from. The four
# exports are Phoronix's data and are not committed: fetch them first from
# openbenchmarking.org/result/<id> for the ids in Appendix A's reference.
bazelisk run //test/coremark_joule/scripts:fetch_commodity -- \
    --exports $PWD/exports --check $PWD/test/coremark_joule/results/commodity_coremark.csv
```

`results.json` is committed, so iterating on the presentation never
re-runs a flow, and a number that changes shows up as a line in a pull
request. Table 1 and every ratio the prose quotes are rendered from it by
`scripts/readme_numbers.py`; `readme_numbers_test` fails when the README
and the file disagree, and `bazelisk run
//test/coremark_joule/scripts:readme_numbers -- test/coremark_joule/results.json`
prints what the README must contain. SERV's runs are ~10^8 cycles each, so
the report is minutes. When something fails, follow the `debug-rtl-sim`
skill rather than reaching for a waveform.

### 10.2 Reproducing the silicon appendix

```sh
python3 test/coremark_joule/scripts/extract_silicon.py \
    --xlsx <measurement workbook> --out test/coremark_joule/silicon.json
python3 test/coremark_joule/scripts/plot_silicon.py \
    --silicon test/coremark_joule/silicon.json \
    --out test/coremark_joule/silicon_throttling.png
```

`silicon.json` carries every swept point, both estimators, the fit range
and its maximum residual. The source workbook is not committed.

---

### 10.3 Adding your own core

A fifth core is a directory rather than a project. What a core has to
supply, and nothing else:

1. **A tile.** `rtl/cmj_<core>.v` freezes the core's configuration -- one
   file read by both the simulator and the flow, so the core simulated and
   the core hardened cannot differ. A cacheless core is wrapped with
   `rtl/cmj_progmem.sv` to put the instruction and data memories inside
   the boundary ([§3.1](#31-the-measurement-boundary)).
2. **A bus adapter** to the two-word platform of [§3.2](#32-the-chain): a byte written to
   `0x1000_0000` is one character of stdout, a 1 written to `0x1000_0008`
   stops the simulation. One C runtime, one linker script and one CoreMark
   port then serve cores whose buses, privilege models and CSR support
   have nothing in common.
3. **A simulation wrapper**, `rtl/cm_soc_<core>.v`, carrying the external
   memory, the sim-control device and the boundary traffic counters that
   make [§4.2](#42-what-the-boundary-costs)'s zero-transfer check a measurement.
4. **A design directory**, `designs/asap7/<core>/`, with a `BUILD`, a
   `config.mk`, a `constraints.sdc` stating all three IO budgets ([§6.3](#63-the-io-budget-and-what-the-platform-default-cost);
   `check_sdc.py` enforces it), a `units.json` mapping kept modules to
   architectural units, and a `pin_policy.json` declaring what the
   annotation audit may waive and why.

A core then inherits, unchanged: the differential cycle count ([§3.3](#33-performance-a-differential-iteration)), the
activity window anchored on the first character out ([§3.4](#34-activity-one-hot-iteration)), the annotation
audit and the estimator sweep ([§3.5](#35-annotation-completeness-and-the-bound-on-the-estimator)), the period derivation ([§5.7](#57-frequency-and-what-deriving-it-changed)), the
five-seed error bar ([§5.11](#511-five-placement-seeds-behind-every-point)) and every gate in [§10.1](#101-re-running-the-study). A core that cannot
clear the CRC gate on its own gate-level netlist produces no number at
all, by design. The rungs that need more are the ones arriving as a tile
or an SoC with an L1 attached; [§8.1](#81-cores-after-the-first-four) says what changes there.

## 11. Licensing

CoreMark's sources are byte-unmodified. Everything platform-specific lives
in `sw/port/`, the porting surface CoreMark documents: `core_portme.{c,h}`
and `ee_printf.c` ship upstream as templates whose platform bodies are
`#error` stubs. CoreMark's Acceptable Use Agreement forbids using the
trademark in connection with a modified copy of the Software.

Appendix A's commodity rows are not ours. The measured figures are
extracted from four public OpenBenchmarking.org result exports (Phoronix
Media), cited by result id in the reference list and not redistributed
here; `scripts/fetch_commodity.py` re-derives
`results/commodity_coremark.csv` from them so the extraction is checkable
without copying the source. The four rows PTS did not measure carry a
vendor rating or a figure quoted from a published review, attributed where
used, except Graviton4, which has no published power and is not in the
table.

---

## Appendix A. Commodity silicon on the same axes

Nobody publishes CoreMark/Joule for a commodity CPU, so this appendix
derives it twice by independent methods. **A.1** reads CPU package power
logged while CoreMark ran, from public result exports, for twenty-six
parts. **A.2** to **A.7** read total power at the mains plug on three
parts in the room, swept by active core count. The package method has the
parts and the stated boundary; the wall-plug method has the sweep, the
only way to see a part throttle, and an independent check on the first,
at a cost in accuracy that most of its length is spent on.

The short answer: **the throttling behaviour publishes, the two methods
agree on energy to within what their boundaries predict, and none of it
belongs on Figure 1**, which plots points whose boundary is verified by
counting every transfer that leaves the hardened block.

### A.1 Package power, logged during the run

Phoronix runs CoreMark 1.0 in its CPU reviews, multi-threaded, `gcc -O2`,
and its test suite logs the CPU package power the kernel reports while
each test runs. The public result exports carry both numbers, so
CoreMark/Joule at the **package** boundary -- cores, caches, memory
controllers, IO die, everything on the socket -- is one division.
`results/commodity_coremark.csv` holds every row below with its result
identifier [16]; the two Apple rows and the Ampere row have no logged
power and are marked with what stands in for it.

| CPU | class | cores | reported clock | CoreMark/s | CPU power during CoreMark | CoreMark/Joule |
|---|---|---|---|---|---|---|
| AMD EPYC 9654, Zen 4 | server | 96 | 3.71 GHz | 3,753,920 | 312 W measured | **12,028** |
| AMD EPYC 9554, Zen 4 | server | 64 | 3.76 GHz | 2,950,220 | 287 W measured | 10,290 |
| AMD EPYC 9374F, Zen 4 | server | 32 | 4.31 GHz | 1,679,742 | 201 W measured | 8,374 |
| AMD EPYC 7763, Zen 3 | server | 64 | 2.45 GHz | 1,876,249 | 206 W measured | 9,089 |
| AMD EPYC 7713, Zen 3 | server | 64 | 2.00 GHz | 1,824,524 | 206 W measured | 8,860 |
| Intel Xeon Platinum 8490H, Sapphire Rapids | server | 60 | 3.50 GHz | 2,162,644 | 307 W measured | 7,055 |
| Intel Xeon Platinum 8380, Ice Lake | server | 40 | 3.40 GHz | 1,177,693 | 244 W measured | 4,827 |
| Ampere Altra Max M128-30, Neoverse N1 | server | 128 | 3.00 GHz | 2,823,599 | 250 W *rated* | 11,294 |
| AMD Ryzen 9 7950X, Zen 4 | desktop | 16 | 5.57 GHz | 1,012,072 | 137 W measured | 7,363 |
| AMD Ryzen 9 7900, Zen 4, 65 W part | desktop | 12 | 5.48 GHz | 648,202 | 79 W measured | 8,215 |
| AMD Ryzen 9 7900X, Zen 4 | desktop | 12 | 5.73 GHz | 737,516 | 143 W measured | 5,144 |
| AMD Ryzen 7 7700, Zen 4, 65 W part | desktop | 8 | 5.39 GHz | 493,775 | 80 W measured | 6,154 |
| AMD Ryzen 7 7700X, Zen 4 | desktop | 8 | 5.57 GHz | 514,276 | 112 W measured | 4,575 |
| AMD Ryzen 5 7600, Zen 4, 65 W part | desktop | 6 | 5.17 GHz | 369,594 | 82 W measured | 4,504 |
| AMD Ryzen 5 7600X, Zen 4 | desktop | 6 | 5.45 GHz | 387,173 | 99 W measured | 3,931 |
| AMD Ryzen 9 9950X, Zen 5 | desktop | 16 | 5.75 GHz | 793,794 | 158 W measured | 5,036 |
| AMD Ryzen 9 9900X, Zen 5 | desktop | 12 | 5.66 GHz | 633,447 | 130 W measured | 4,884 |
| AMD Ryzen 7 9700X, Zen 5, 65 W | desktop | 8 | 5.50 GHz | 545,799 | 77 W measured | 7,075 |
| AMD Ryzen 7 9700X, Zen 5, 105 W cTDP | desktop | 8 | 5.50 GHz | 582,558 | 112 W measured | 5,214 |
| AMD Ryzen 5 9600X, Zen 5, 65 W | desktop | 6 | 5.48 GHz | 427,217 | 79 W measured | 5,418 |
| AMD Ryzen 5 9600X, Zen 5, 105 W cTDP | desktop | 6 | 5.48 GHz | 434,740 | 98 W measured | 4,417 |
| Intel Core i9-13900K, Raptor Lake | desktop | 8P + 16E | 5.50 GHz | 831,717 | 149 W measured | 5,580 |
| Intel Core i9-14900K, Raptor Lake | desktop | 8P + 16E | 5.70 GHz | 872,643 | 170 W measured | 5,147 |
| Intel Core Ultra 9 285K, Arrow Lake | desktop | 8P + 16E | 5.70 GHz | 1,048,146 | 150 W measured | 6,978 |
| Apple M1, Mac mini | laptop-class | 4P + 4E | 3.20 GHz | 175,072 | 26.5 W *at the wall* [17] | 6,606 |
| Apple M2, MacBook Air | laptop-class | 4P + 4E | 3.49 GHz | 204,531 | ~20 W *package, estimated* [18] | ~10,200 |

**Table 16.** Multi-threaded CoreMark and CPU package power, from public
OpenBenchmarking.org result exports [16]. Rows share a compiler and kernel
within an export and not across: the x86 server rows are one export
(January 2023), the desktop rows another (October 2024), the Ampere and
Apple rows two more. CoreMark/MHz for a whole package is not shown because
SMT and mixed core types make it a different quantity from Table 1's
single-thread figure. The Apple rows use power from reviews, the Ampere
row a rating; Graviton4 (2,746,152 CoreMark/s) has no published power and
is left off.

**A server part beats a gaming desktop on CoreMark/Joule despite the lower
clock**, within a generation and a vendor, and the same Zen 4 core is in
both columns. EPYC 9654 at 3.71 GHz delivers **1.63x** the CoreMark/Joule
of Ryzen 9 7950X at 5.57 GHz, on the same microarchitecture, with power
measured during the same benchmark. Intel within a generation reads the
same way: Xeon 8490H against Core i9-13900K is **1.26x**. It does not hold
across generations: Ice Lake's Xeon 8380 sits *below* Arrow Lake's 285K,
so node and core count weigh more than the clock once the generation
changes.

**Two server rows sharpen that within one generation and one socket.**
Zen 4 walks 12,028, 10,290 and 8,374 CoreMark/Joule as the part goes 96
cores at 3.71 GHz, 64 at 3.76 and 32 at 4.31: the frequency-optimised
9374F is the worst of the three. The Zen 3 pair says the opposite is *not*
true below the voltage wall: 7763 and 7713 draw the same 206 W, and the
2.45 GHz bin returns more work for it than the 2.00 GHz bin (9,089
against 8,860). Clocking down only buys efficiency where the clock was
bought with voltage.

**The desktop rows add the controlled experiment the servers cannot
give.** The Ryzen 9 7900 and 7900X are the same twelve-core die at 65 W
and 170 W ratings: the 65 W part scores **1.60x** the CoreMark/Joule of
the 170 W part for 12 % less CoreMark. The Ryzen 7 9700X at its 65 W
default and its 105 W option is one chip run twice: 6.7 % more CoreMark
for 45 % more power, CoreMark/Joule down **26 %**. The Ryzen 5 9600X is
the same experiment a third time and the steepest: 1.8 % more CoreMark for
25 % more power, down **18 %**. That is [§2.3](#23-why-coremarkjoule-falls-as-coremarksecond-rises)'s voltage route observed on
silicon: the last few hundred megahertz are bought with $V^2$, and a
server binned for 3.5 GHz at 1 W per core is on the cheap part of the
curve a 5.7 GHz desktop has left behind.

**The Zen 5 desktop parts split on die count.** The 9950X returns
**21.6 % less** CoreMark than the Zen 4 7950X it succeeds -- same sixteen
cores, higher clock, same export, kernel and compiler -- while drawing
14.7 % more power, and the 9900X regresses 14.1 % against the 7900X on the
same twelve cores. The Zen 5 parts that do *not* regress are the
single-die ones: the 9600X and 9700X improve on the 7600X and 7700X by
10.3 % and 6.1 %. Two dual-die parts behaving alike is a property of the
published data, and what splits them is not established here.

**How big the effect should be, and how big it is.** [§2.3](#23-why-coremarkjoule-falls-as-coremarksecond-rises) predicts energy
per operation $\propto f^2$ on the voltage route. The reported clocks give
$(5.57/3.71)^2 = 2.25\times$ for EPYC 9654 against 7950X; measured, 1.63x.
Two knowable things pull it down: all-core clocks under a 192-thread load
sit below the reported maxima, so the true frequency ratio is nearer 1.4,
and the server package carries an IO die, twelve memory channels and
384 MB of L3 the desktop does not, power that scales with neither
frequency nor voltage. The prediction overshoots in the direction the
boundary says it should.

**Arm and Apple land where the physics says.** Ampere's 128 Neoverse N1
cores at 3.0 GHz reach 11,294 CoreMark/Joule on their 250 W rating, level
with EPYC 9654 despite a core two generations older, because the clock is
low and there is no SMT to pay for. Apple's M2 at ~20 W package is at
about 10,200, beside the best servers, from eight cores that never see
5 GHz. CoreMark/Joule is bought by running many cores slowly, not one core
fast.

**Where this study's cores sit, with the boundary said first.** Table 1 is
core + L1 on a predictive 7 nm kit at its best-case corner; Table 16 is a
whole package, IO die and memory controllers included, on a real 4 nm or
5 nm process at a typical corner. Neither is convertible into the other,
and the comparison is a ladder, not a Figure. On it, ibex sits **7.0x**
above the best commodity package and VeeR **1.7x** above it, while SERV
sits **11.9x below** it, under every commodity part in the table. The
direction and the decades are what [§2.3](#23-why-coremarkjoule-falls-as-coremarksecond-rises) predicts: a small in-order core at
0.77 V with nothing outside its L1 charged to it is where energy per
CoreMark bottoms out, and a bit-serial core that takes 41 million cycles
per iteration pays leakage and clock on every one and ends up below a
350 W Xeon.

---

### A.2 The wall-plug measurement

Total system power was read at the mains plug while CoreMark ran on `n`
active cores, sweeping `n`. Energy was attributed two ways:

* **delta**: `(P_at_n − P_idle) / (n × CoreMark/s)`;
* **slope**: watts per *additional* core, least-squares fitted over the
  region where the part is not yet throttling, divided by CoreMark/s.

No on-die counters, no instrumented board, no per-rail shunt.

**Why this is admissible.** CoreMark's working set fits in L1 [5], so the
benchmark generates no DRAM traffic and almost no uncore traffic.
Everything outside the cores is held constant across a sweep, and the
difference brackets core + L1 activity: the boundary [§3.1](#31-the-measurement-boundary) defines for the
ASAP7 points, reached by subtraction instead of by construction. It is
also the method's ceiling: **nothing measured this way generalises to a
workload that misses L1.**

| part | µarch | node | cores/threads | clock | idle |
| --- | --- | --- | --- | --- | --- |
| AMD Ryzen Threadripper 3970X | Zen 2 | TSMC N7 [19] | 32 / 64 | 3.9 GHz | 167.0 W |
| Intel Xeon Platinum 8558U | Emerald Rapids | Intel 7 [20] | 48 / 96 | 2.9 GHz | 70.0 W |
| Qualcomm Snapdragon X Elite X1E78100 | Oryon | TSMC N4P [21] | 12 / 12 | 3.417 GHz | 9.2 W |

Only the core die's process is named: it is the only part of the package
inside the boundary. The Threadripper's IO die is GlobalFoundries 12/14 nm
and sits outside it.

### A.3 What the sweeps show: three parts, three behaviours

![Per-core throughput and total system power against active cores, for
three shipping parts. The X Elite holds 100 % throughput to 9 cores
and 98.6 % at 12. The Threadripper holds 97.2 % until past its 32nd
physical core and only then falls, which is SMT sharing rather than
frequency reduction. The Xeon falls from 25 of its 48 cores — too early
for SMT — and then pins at 412 W while throughput keeps
falling.](silicon_throttling.png)

Read on the assumption that IPC is fixed, so CoreMark/s tracks clock:

**X Elite: no throttling in range.** Flat at 100 % through 9 cores and
98.6 % at all 12, per-core power between 3.60 and 3.77 W across the sweep,
43 W over idle at full load. One operating point from 1 to 12 cores; this
workload never provokes DVFS.

**Threadripper: no frequency throttling; the fall is SMT.** Throughput
holds 97.2 % from 2 threads to **35**, past its 32 physical cores, and
only then falls: 88.5 % at 40, 76.4 % at 60. Pure SMT sharing predicts
about 85 % at 40 threads against 88.5 % measured, so no frequency
reduction is needed to explain the shape. Power over idle peaks at 153 W
against a 280 W TDP. **Reading this curve as throttling would be wrong**,
and the distinction is visible only because the x axis is normalised to
physical cores.

**Xeon: real throttling, twice, by two mechanisms.** Throughput starts
falling at **25 threads, about half its 48 physical cores**, far too early
for SMT: all-core turbo stepping down as active-core count rises. Then
wall power **saturates at exactly 412 W from 85 threads** (85, 90 and 96
all read 412 W) while throughput keeps falling from 21 520 to 20 280
CoreMark/s: power pinned, performance given up to hold it.

### A.4 The energy numbers, and why there are two of them

| part | slope | µJ/iteration | CoreMark/Joule | CoreMark/MHz |
| --- | --- | --- | --- | --- |
| AMD Ryzen Threadripper 3970X | 2.89 W/core | 100.3 | 9,970 | 7.38 |
| Intel Xeon Platinum 8558U | 7.68 W/core | 212.9 | 4,700 | 12.44 |
| Qualcomm Snapdragon X Elite X1E78100 | 3.72 W/core | 86.8 | 11,520 | 12.53 |

The `delta` estimator disagrees, and where it disagrees it is wrong:

* On the **Xeon** it reads 1 381 µJ/iteration at one thread, against 213
  from the slope. The one-thread delta is 50 W -- 120 W against a 70 W
  idle -- which is the platform waking its uncore, mesh and fans, all
  charged to one core.
* On the **Threadripper** the one-core signal is **3.0 W read as 170.0
  minus 167.0**, a 1.8 % difference of two large numbers. A plug meter
  specified at ±1–2 % of reading gives ±1.7–3.4 W, the entire signal. The
  slope is fitted over many points and a systematic offset cancels in it.
* On the **X Elite** the source did not use its measured idle. Real idle
  was 6 W; the value used is 9.2 W, back-computed as one-core power minus
  the mean per-core step. That is a sound correction for a platform that
  power-gates deeply, and it is what a slope fit does without being told.

The slope reproduces the corrected numbers on the two parts where a
correction was attempted (9.97 against 9.6, 11.52 against 11.89) while
needing neither an idle reading nor a modelling assumption, and rescues
the third from an implausible figure. **Where the two estimators
disagree, quote the slope.**

### A.5 Corroboration

**Supporting, and only half of it.** A published review puts X Elite
sustained clocks at 3.4 GHz against 3.417 measured here [22]. Its 47.6 W
is a *peak* reading during Geekbench 6, so setting it beside 52.5 W at the
wall for 12 cores under CoreMark compares two benchmarks at two
boundaries; the clock is the part that corroborates. The Threadripper's
153 W full-load delta against a 280 W TDP is consistent with CoreMark
being a small integer benchmark that never becomes a power virus.

**Not supporting: the performance numbers are above the certified
ceiling.** EEMBC's database has a single-thread maximum near 5.1
CoreMark/MHz [23]; these parts read 7.38 to 12.53. That database is
dominated by older and embedded entries, and modern wide cores with
aggressive compilers plausibly exceed it, but **these are not
EEMBC-comparable numbers and are not claimed to be.** The two x86 parts
were also built with one configuration named for one vendor's
microarchitecture, which on its own explains AMD's 7.38 against Intel's
12.44 and disqualifies the pair as an IPC comparison.

**Not supporting: the energy ratio is too small.** N7 → N5 → N4P is
roughly 0.55× energy at iso-performance (N4P is 22 % more power efficient
than N5 [21]; N5 roughly 30 % over N7), and Oryon is five years newer and
far wider than Zen 2, so a 2–3× CoreMark/Joule advantage would be
unsurprising. Measured: **1.16×**, with the better estimator. §A.1
suggests why, and it is not the node: its controlled rows show the same
twelve-core die at 65 W and 170 W differing by **1.60×** in
CoreMark/Joule, and one chip at two power limits losing 26 % for 6.7 %
more CoreMark. Operating point moves this metric by more than a node
generation does, and these three parts were measured wherever their
governors put them -- §A.3 shows the X Elite holding one operating point
and the Xeon stepping down through several -- so a cross-part energy ratio
here compares operating points at least as much as silicon. That is a
limitation of the experiment, not a finding about the parts.

### A.6 What the two methods say together

**The energy numbers agree with the package measurements.** The slope
gives 9,970 CoreMark/Joule for the Threadripper, 11,520 for the X Elite
and 4,700 for the Xeon; §A.1's twenty-six parts, measured at the package,
span **3,931 to 12,028**. Three wall-plug numbers from a different method,
boundary and decade of silicon land inside that band. That corroborates
the *method*, not the ladder, and the residual's direction is the
interesting part: a slope excludes the platform's fixed cost by
construction, so it measures the *marginal* core and should read
**higher** than a package figure for a comparable part. The
Threadripper's Zen 2 at 9,970 against §A.1's Zen 3 and Zen 4 servers at
9,089–12,028 is about what that predicts.

The CoreMark/MHz axis, which *is* boundary-independent, is disqualified
separately: both x86 parts here were built with one configuration named
for one vendor's microarchitecture.

The throttling half is **viable on its own terms**: three parts, three
distinguishable and corroborated behaviours, from a measurement anyone
can repeat with a plug meter, and the one thing §A.1's data cannot show.

### A.7 What a repeat must do

1. **One CoreMark build for every part**, flags recorded, and never a
   configuration named for one vendor's microarchitecture used on
   another's. This alone may account for the whole AMD–Intel gap.
2. **Report the CoreMark validation output and run configuration**, so
   the numbers can be placed against EEMBC's database [23] instead of
   floating above it.
3. **Measure the clock at every point** rather than assuming one.
   Frequency throttling and SMT contention are confounded in both x86
   sweeps, and only a measured clock separates them.
4. **Read on-die energy counters alongside the plug meter**, so platform
   overhead is subtracted rather than modelled.
5. **Pin to physical cores and disable SMT** for the sweep, so "core"
   means the same thing on all three parts.
6. **Estimate from the slope**, and treat idle identically across parts
   or not at all.
7. **Repeat every point and report the spread.** Every number here is a
   single reading.
8. **Record thermal state for all parts**, not only the one that had a
   temperature column.

## References

1. EEMBC. *CoreMark — an EEMBC Benchmark.* https://www.eembc.org/coremark/
2. EEMBC. *ULPMark-CoreMark (ULPMark-CM): CoreMark iterations per milli-Joule.* https://www.eembc.org/ulpmark/ulp-cm/
3. F. N. Najm. "A survey of power estimation techniques in VLSI circuits." *IEEE Transactions on VLSI Systems* 2(4):446–455, 1994. doi:10.1109/92.335013
4. F. N. Najm. "Transition density: a new measure of activity in digital circuits." *IEEE Transactions on Computer-Aided Design* 12(2):310–323, 1993.
5. Z. Fu et al. "Ramping Up Open-Source RISC-V Cores: Assessing the Energy Efficiency of Superscalar, Out-of-Order Execution." *ACM International Conference on Computing Frontiers (CF'25)*. arXiv:2505.24363
6. F. Zaruba, L. Benini. "The Cost of Application-Class Processing: Energy and Performance Analysis of a Linux-ready 1.7 GHz 64 bit RISC-V Core in 22 nm FDSOI Technology." *IEEE Transactions on VLSI Systems*, 2019. arXiv:1904.05442
7. B. Villegas, I. Vourkas. "A Gate-Level Power Estimation Approach with a Comprehensive Definition of Thresholds for Classification and Filtering of Inertial Glitch Pulses." *Journal of Low Power Electronics and Applications* 14(3):41, 2024. doi:10.3390/jlpea14030041
8. *Measuring Active Power Using PrimeTime PX: A User Perspective.* SNUG Boston 2010. https://veripool.org/papers/Active_Power_Primetime_PX_SNUGBos10_paper.pdf
9. Parallax Software. *OpenSTA* — `power/Power.cc`, `power/SaifReader.cc`. https://github.com/parallaxsw/OpenSTA
10. "Feature request — extend reporting on pin activities." parallaxsw/OpenSTA issue #162. https://github.com/parallaxsw/OpenSTA/issues/162
11. Western Digital. *CoreMark Benchmarking for SweRV*, 20 November 2019. Listed as `seh1_SweRV_CoreMark_Benchmarking.pdf` in the SweRV Support Package (chipsalliance/Cores-SweRV-Support-Package, `README.adoc` item 4.14, "Open-source SweRV EH1 benchmark results published by Western Digital"). The PDF is not committed to that repository and we know of no public copy, so the figures quoted from it here cannot currently be checked against the source.
12. P. D. Schiavone, F. Conti, D. Rossi, M. Gautschi, A. Pullini, E. Flamand, L. Benini. "Slow and steady wins the race? A comparison of ultra-low-power RISC-V cores for Internet-of-Things applications." *PATMOS 2017*. doi:10.1109/PATMOS.2017.8106976
13. N. Gallmann, P. Vogel, P. D. Schiavone, L. Benini. "From Swift to Mighty: A Cost-Benefit Analysis of Ibex and CV32E40P Regarding Application Performance, Power and Area." *CARRV 2021*. https://carrv.github.io/2021/papers/CARRV2021_paper_8_Gallmann.pdf
14. A. Djupdal, M. Själander, M. Jahre, S. Aunet, T. Ytterdal. "Optimizing Energy Efficiency in Subthreshold RISC-V Cores." arXiv:2502.06588, 2025.
15. I. Elsadek, E. Y. Tawfik. "RISC-V Resource-Constrained Cores: A Survey and Energy Comparison." *19th IEEE International New Circuits and Systems Conference (NEWCAS)*, Toulon, June 2021. doi:10.1109/NEWCAS50681.2021.9462781. Its abstract describes the seven cores as "implemented using an ASIC prototyping platform" and reports 8.7 CoreMark iterations/mJ for ibex; we read "ASIC prototyping platform" as FPGA-based, which is why it is excluded below, and a reader who establishes otherwise from the full text retires that exclusion.
16. OpenBenchmarking.org result exports (Phoronix Test Suite, `pts/coremark` 1.0, multi-threaded, `gcc -O2`, CPU package power via the suite's power monitor): `2301109-PTS-SPRREVIE33` (Sapphire Rapids review, January 2023), `2410235-NE-285KARROW68` (Arrow Lake review, October 2024), `2407128-PTS-GRAVITON53` (Graviton4 metal comparison, July 2024), `2208073-NE-M2REVIEW767` (Apple M2 on Asahi Linux, August 2022). https://openbenchmarking.org/result/<id>
17. AnandTech, *Mac mini 2020 (Apple M1) review*: wall power averaging 26.5 W under a multi-threaded load, chip estimated at 20 to 24 W.
18. TechSpot, *Apple M2 review*: about 20 W package power sustained in Cinebench R23 multi-threaded on the MacBook Air.
19. AMD / WikiChip. *Ryzen Threadripper 3970X* — Zen 2 CCDs on TSMC N7, IO die on GlobalFoundries 12/14 nm. https://en.wikichip.org/wiki/amd/ryzen_threadripper/3970x
20. Intel. *Xeon Platinum 8558U (Emerald Rapids, 5th Gen Xeon Scalable)* — Raptor Cove cores on Intel 7.
21. TSMC. *N4P Extends the Performance and Power Efficiency of the 5nm Family* — N4P is 22 % more power efficient than N5. https://pr.tsmc.com/english/news/2874
22. A. Sha. "Snapdragon X Elite Benchmarks: Geekbench, Cinebench, 3DMark & More." Beebom, 24 July 2024: peak power consumption 47.6 W and sustained clock about 3400 MHz, both measured during the Geekbench 6 CPU test. https://beebom.com/snapdragon-x-elite-benchmarks/
23. EEMBC. *CoreMark scores database.* https://www.eembc.org/coremark/scores.php
24. W. Shum, J. H. Anderson. "FPGA glitch power analysis and reduction." *ACM/IEEE International Symposium on Low Power Electronics and Design (ISLPED)*, pp. 27–32, 2011. https://janders.eecg.utoronto.ca/pdfs/warren_final.pdf
25. M. Münch, N. Wehn, B. Wurth, R. Mehra, J. Sproch. "Automating RT-level operand isolation to minimize power consumption in datapaths." *Design, Automation and Test in Europe (DATE)*, pp. 624–631, 2000. doi:10.1145/343647.343873
26. M. Keating, D. Flynn, R. Aitken, A. Gibbons, K. Shi. *Low Power Methodology Manual for System-on-Chip Design.* Springer, 2007.
27. Keysight. *Decoding Glitch Power at the RTL Stage: a shift-left approach for glitch power estimation and optimization.* White paper. https://www.keysight.com/content/dam/keysight/en/doc/gate/white-papers/Decoding-Glitch-Power-at-the-RTL-Stage.pdf
28. Zettabolt. *Accurate Post-PnR Glitch Power Estimation Using RTL Simulation Data.* Case study. https://zettabolt.com/blogs/Glitch-Power-Estimation
29. NVIDIA. *DGX H100/H200 System User Guide* — 8 × H100 SXM5, dual Intel Xeon Platinum 8480C, 10.2 kW maximum. https://docs.nvidia.com/dgx/dgxh100-user-guide/
30. NVIDIA. *GB200 NVL72* — 72 × Blackwell, 36 × Grace, ~120 kW rack; GB200 Superchip 2700 W = 2 × 1200 W GPU + ~300 W Grace CPU/IO. https://www.nvidia.com/en-us/data-center/gb200-nvl72/
31. Y. Bao. *XiangShan KMH: An Open Source RISC-V Core with >15/GHz for SPECCPU2006.* Project slides, 14 May 2025. Slide 6 (roadmap, nodes), 7 (Kunminghu µarch), 9 (SPEC CPU2006 per GHz), 10 (tape-out status: 7 nm area, power, max core frequency; NHv2 2.5 GHz), 11 (KMHv3 over KMHv2).
32. J. Zhao, B. Korpan, A. Gonzalez, K. Asanović. "SonicBOOM: The 3rd Generation Berkeley Out-of-Order Machine." *CARRV 2020.* Section 5 and Figure 7.
33. lowRISC. *Ibex RISC-V Core* README, performance and area table (CoreMark/MHz, yosys kGE per configuration). https://github.com/lowRISC/ibex
34. O. Kindgren. *SERV — the SErial RISC-V CPU* README, size table. https://github.com/olofk/serv
35. C. Wolf. *PicoRV32 — A Size-Optimized RISC-V CPU* README, performance and size sections. https://github.com/YosysHQ/picorv32
36. Western Digital. *SweRV Core EH1* announcement, RISC-V Summit, December 2018: 4.9 CoreMark/MHz, up to 1.8 GHz on 28 nm.
37. CHIPS Alliance / Western Digital. *SweRV Core EL2* announcement: 3.6 CoreMark/MHz simulated, 0.023 mm² in 16 nm, up to 600 MHz.
