# CoreMark per Joule at Global Route: Energy Efficiency of Small RISC-V Cores on a Predictive 7 nm Kit

**A measurement study in the bazel-orfs repository.**
Everything in this directory is `tags = ["manual"]`; `test/` is never
shipped, and nothing here is pulled in by a wildcard build.

---

## Abstract

> **Work in progress.** Every measurement target here is
> `tags = ["manual"]`. The numbers are real and reproducible, and the
> parts that are modelled rather than measured are named as such in §5.
> This is the first version, not the final one.

CoreMark/MHz is reported for almost every open-source RISC-V core;
CoreMark/Joule almost never is, because the energy half needs a
hardened netlist, a switching-activity capture, and a power engine, and
each of the three has a way of producing a plausible number that is not
a measurement. We build the whole chain in a reproducible flow —
CoreMark ELF, RTL simulation, CRC gate, synthesis, global route,
gate-level simulation, SAIF over one hot iteration, `report_power` —
and screen at global route so a point costs minutes rather than hours.
We report four cores on ASAP7: SERV (0.0243 CoreMark/MHz), picorv32
(0.5531), ibex (2.4543) and VeeR EH1 (4.7979), spanning nearly two
hundred times in performance per clock.

**Every point is measured at the same stated boundary — the core and
its L1, and nothing beyond it — and the boundary is verified rather
than asserted.** Cores with no cache are hardened together with the
tightly-coupled memory they execute from; each wrapper counts every
transfer that leaves the hardened block, and for all four cores one hot
CoreMark iteration sends **zero**. Closing that boundary is itself the
study's largest result: it costs the cacheless cores between **2.8x and
4.2x** of their CoreMark/Joule, with CoreMark/MHz unchanged to every
digit, and it reverses the ordering — ibex reads 8.08x better than VeeR
EH1 when its memory is outside the measurement and 2.89x better when it
is inside. Any CoreMark/Joule quoted for a small core without stating
whether its memory was measured is uninterpretable at roughly an order
of magnitude.

The study's central methodological contribution is negative and
checkable. OpenSTA does not fail when a pin carries no annotated
switching activity: it estimates one, and the estimate is
indistinguishable from a measurement in the report. We therefore
enumerate every pin, classify every pin the SAIF did not reach, and
bound what the estimator could be worth by sweeping the default
activity across its entire range. For the three cacheless cores the
SAIF annotates **100 % of pins** (27,597 / 52,280 / 82,396), **zero**
are unannotated, and for all four cores the SAIF-driven total is
bit-identical at ten significant figures across the whole sweep, while
the same sweep moves the vectorless total by 24--475 %. The energy
numbers are therefore vector-driven in the strong sense: OpenSTA's
probabilistic activity model contributes nothing to them.

The shape the points make is reported with its own diagnosis, and the
diagnosis was tested. An earlier draft found the cacheless cores on a
straight line in log--log axes and predicted, falsifiably, that the
boundary was the cause. Hardening the memories confirmed most of it —
extrapolating the cacheless trend to VeeR's performance overpredicted
its efficiency by **15.2x** before and **5.65x** after, closing 63 % of
the gap — and refuted the rest: the line is still there, and tighter.
The reason is now the platform's memory model rather than the boundary,
and we report that inversion rather than the confirmation alone, because
it is what the data supports: **CoreMark/Joule is not yet a
discriminating axis among cores of this class.**

We state, rather than imply, what the numbers do not yet cover. Every
memory is a FakeRAM abstract, and FakeRAM's ASAP7 views charge **the
same switching energy and the same leakage for every shape** — so the
58--71 % of each point's power that is memory is a term that does not
know how large the memory is. Halving every memory in this study would
move no number in it. That is deliberate: one model applied uniformly is
something a comparison survives, and two models is not — but it is the
single largest thing between this work and an energy measurement, and it
is being fixed in the generator rather than worked around here. ibex is
measured with `ICache=0`, which §5.1 shows is the right configuration
rather than an omission. The simulation is zero-delay and so
carries no glitch power, the parasitics are estimated rather than
extracted, the corner is ASAP7's best case, and the frequency is an SDC
target rather than an achieved maximum. Each is quantified or bounded in
§5.

---

## 1. Introduction

![Figure 1](coremark_joule.png)

**Figure 1.** CoreMark/Joule against CoreMark/MHz, both axes
logarithmic. Blue: measured here on ASAP7 at global route, with
activity from one hot CoreMark iteration. Red: a published GF 22 FDX
series, derived from another paper's numbers and drawn in its own
colour because it is not like-for-like (§4.4).

| core | ISA | CoreMark/MHz | cycles/iter | f (MHz) | P (SAIF) | CoreMark/Joule |
|---|---|---|---|---|---|---|
| SERV | rv32i | 0.0243 | 41,202,900 | 2283.1 | 43.40 mW | 1,277 |
| picorv32 | rv32im | 0.5531 | 1,807,889 | 2141.3 | 44.40 mW | 26,676 |
| ibex | rv32imc | 2.4543 | 407,448 | 780.0 | 19.50 mW | 98,176 |
| VeeR EH1 | rv32imc | 4.7979 | 208,425 | 628.5 | 86.50 mW | 34,863 |

**Table 1.** The four measured points, all at §3.1's boundary: the core
and its L1, or the tightly-coupled memory that stands in for one. Every
point is verified to send zero transfers outside the hardened block
during the iteration measured. §5.1 reports what closing that boundary
cost — between 5.7x and 9.8x of CoreMark/Joule on the three cores that
had been measured without their memories, at unchanged CoreMark/MHz.

The question is the shape of the curve: does spending area and
switching on a wider machine buy back its own energy? The literature
that answers it for large cores answers it at a stated boundary with
signoff tools [5, 6]. For small cores it is mostly not answered at all,
and the reason is that the energy half of the metric is easy to get
wrong in ways that do not look like errors.

Three such ways shape the method below. A SAIF captured against one
netlist and applied to another does not fail — OpenSTA falls back to
default activity for the nets that did not match. A gate-level netlist
whose memory macro has no behavioural model does not report low memory
power — it computes the wrong answer, and only a functional check
notices. And a power report whose pins are largely unannotated is not
labelled as an estimate; it is labelled "Total".

By taking full advantage of RISC-V's unrestricted licensing, this
framework provides a completely open, peer-verifiable PPA baseline right
out of the box. Every core, the benchmark, the toolchain, the PDK and
the EDA flow are fetched from their own upstreams at pinned commits and
built by one command; there is no vendored RTL, no licensed tool and no
number a reader cannot re-take. For teams developing internal hardware,
the modular bazel-orfs setup makes it straightforward to drop your own
RTL into the flow: a core joins the study as a `config.mk`, a bus
adapter to the two-word platform of §3.2, and a `units.json` — and it
then inherits the annotation audit of §3.5 and every gate in §4.3
unchanged.

The contributions are:

1. A reproducible, fully automated CoreMark → CoreMark/Joule chain in
   an open flow, screened at global route (§3.2).
2. A performance metric that removes CoreMark's ten-second run rule
   from a problem no simulator can satisfy, with an automated test that
   its premise cannot rot (§3.3).
3. An activity window anchored on an observable event in the benchmark
   rather than on an instrumented one (§3.4).
4. **An automated, complete account that OpenSTA's probabilistic
   activity model does not enter the result** — enumeration,
   classification, and a measured bound (§3.5, §4.2).
5. An explicit statement of the boundary the study intends, of the gap
   between it and these three points, and of the direction of every
   remaining bias (§5).

---

## 2. Background

### 2.1 Vectorless and vector-driven power estimation

Dynamic power in a CMOS netlist is set by how often each node
switches. Two families of technique supply that [3]. *Probabilistic*
(vectorless) estimation propagates signal probabilities and transition
densities forward from the primary inputs through each gate's Boolean
function; it is cheap, needs no stimulus, and is blind to the temporal
and spatial correlation that reconvergent fanout creates. *Vector-driven*
estimation reads the switching activity from a simulation of the actual
workload, and is the basis of signoff power [8].

The distinction matters for this study because a report produced the
first way and a report produced the second way look identical. The
number is a Watt either way.

### 2.2 What OpenSTA does with an unannotated pin

Read from the pinned OpenSTA (`power/Power.cc`, `power/SaifReader.cc`
at `65bd9df5`) rather than assumed, because the whole of §3.5 rests on
it:

- `read_saif` matches each SAIF `NET` name against a **pin** of the
  enclosing instance and records it with origin `saif`. Hierarchical,
  internal and power/ground pins are skipped. It prints
  `Annotated N pin activities.`
- `seedActivities()` seeds the *levelization roots* — top-level input
  ports and tie-cell outputs — with each pin's annotated activity if it
  has one, and otherwise with `input_activity_`, whose default is
  `0.1 / min_clock_period` at duty 0.5. This default is the only path
  by which a density OpenSTA invented enters the design.
- `PropActivityVisitor::visit()` prefers an annotated activity over a
  propagated one for every pin it visits. A design in which every pin
  is annotated therefore never propagates at all.
- Everything not annotated and not a root is propagated: a BDD
  evaluation of the driving cell's function over its inputs' densities
  and duties — Najm's transition density [3, 4], with its known
  blindness to reconvergent-fanout correlation.
- A clock-network pin bypasses both paths and is given `2/period` at
  the clock's duty, taken exactly from the SDC. That one is not an
  estimate.

OpenSTA exposes `report_activity_annotation`, which enumerates
annotated and unannotated pins; the command exists because this
question was asked of it [10].

### 2.3 Why CoreMark/Joule falls as CoreMark/second rises

The two axes of Figure 1 are not independent, and the way they are
coupled is worth writing down before any number is read off the plot.

Start from the identity:

    CoreMark/Joule = (CoreMark/MHz x f) / P,    P = P_dyn + P_leak
    P_dyn = a C V^2 f
    P_leak = V I_leak(V, T)

**At fixed voltage and fixed microarchitecture, energy per unit of work
does not depend on frequency at all.** Substituting `P_dyn` into the
identity, the `f` cancels: `CoreMark/Joule = (CoreMark/MHz) / (a C V^2)`.
Doing the same work twice as fast costs twice the power for half the
time. This is the part that surprises people, and it is why "run slower
to save energy" is wrong as stated.

**The leakage term pushes the same way.** Leakage energy per operation
is `P_leak / (CoreMark/MHz x f)`, which falls as `1/f`: a faster part
spends less time leaking per unit of work. This is the whole argument
for race-to-idle, and in a leakage-dominated regime — a small core at a
low frequency, which is exactly where SERV sits — it is the dominant
term.

So if frequency were free, higher would be better. It is not free, and
what it costs is where the efficiency goes.

**Route one: buy frequency with voltage.** `f_max` rises roughly
linearly with `V` over the usable range, while `E_dyn` per operation
rises as `V^2`. Energy per operation therefore scales as `f^2`, and
CoreMark/Joule as `1/f^2`. Taking ibex's measured point and holding the
microarchitecture fixed:

| f | energy per CoreMark iteration | CoreMark/Joule |
|---|---|---|
| 780 MHz (measured) | 10.2 µJ | 98,176 |
| 3.0 GHz (projected) | 151 µJ | 6,637 |
| 5.0 GHz (projected) | 419 µJ | 2,389 |

**Those two rows are a projection under a stated assumption, not a
measurement**, and the assumption is the point: reaching 3 GHz this way
would need 3.6× the supply, which at 7 nm is not a voltage, it is a
breakdown. ASAP7's whole headroom from typical to best case is 0.70 V to
0.77 V — about 10 %, worth maybe 10–20 % of frequency for 21 % more
dynamic energy per operation. Voltage is exhausted almost immediately,
and it was a losing trade before it ran out.

**Route two: buy frequency with microarchitecture.** Shorten the logic
between registers and the same silicon closes at a higher clock: more
pipeline stages, more flops, more clock tree, and an optimiser that
upsizes cells to make each stage fit. Every one of those raises `C` per
operation while `V` stays put. This is the route real 3–5 GHz parts
take, and it is why a datacenter core is not a small core clocked up —
it is a different design whose energy per instruction is structurally
higher.

The consequence for this study is that **the interesting cores are not
reachable by pushing a knob on the cores it has.** A 3 GHz point is a
different microarchitecture, and §7's roadmap is the honest way to get
one. What the existing cores *can* say is where their own knee is: §8.4's
Pareto sweep, which measures route two directly by pushing the period
until the tools start upsizing wholesale, and shows the cost of speed as
a curve rather than as a projection.

It also bears on §4.6. The near-degeneracy there — power almost constant
across a 101× span in performance — is partly this: the three cores sit
within 1.7× of each other in frequency and share a voltage, so the term
that would separate them has not been exercised.

---

## 3. Method

### 3.1 The measurement boundary

The designs in this study span about three decades of CoreMark/MHz and
are not variants of one another. A bit-serial state machine that takes
41 million cycles per CoreMark iteration and a superscalar
out-of-order tile that takes a few hundred thousand are qualitatively
different objects: different pipeline depths, different memory systems,
different amounts of machinery that has no counterpart at the other
end of the range. There is no configuration knob that turns one into
the other, so there is no sense in which they are the same experiment
run at different settings.

An apples-to-apples comparison across that range is therefore not
something the designs give us. It has to be *constructed*, and the only
thing available to construct it out of is the definition of what is
being measured. **This study defines the measured object as the core
and its L1 caches — and explicitly not whatever surrounds them.** The
L2, the interconnect, the peripherals, the debug infrastructure and the
rest of the SoC are outside the boundary on every point, however much
or little of that a given repository happens to ship. What is compared
is the same *kind* of thing each time, even though the things
themselves are not alike.

Above about 5 CoreMark/MHz the core and its L1 cannot be told apart in
any case: the caches sit inside the tile, share its clock and its
floorplan, and neither the repositories nor the literature delivers a
number for the core without them. Drawing the boundary anywhere else
there means drawing it around an abstraction that does not exist.

The smallest cores have no caches at all. They have a small memory that
holds the program the hot loop runs out of, and **that memory is what
gets measured**, hardened as part of the core. This is not an exception
granted to the small end; it is the same rule reaching the same object.
In both cases the boundary encloses the core and the memory it fetches
and loads from at the first level, and excludes everything past it. A
cacheless core is not credited with a free, perfect memory merely
because its memory is small enough to be overlooked.

One rule, applied to every point: **the core, its L1 or the tightly-coupled
memory that stands in for one, and nothing beyond.**

None of picorv32, SERV or ibex ships such a memory — their testbenches
use simulation arrays — so this study supplies one: a 32 kB instruction
memory and an 8 kB data memory, at separate addresses, hardened inside
each tile (`rtl/cmj_progmem.sv`, `sw/port/link.ld`). Two memories rather
than one, because that is what VeeR already is — an ICCM and a DCCM at
separate architectural addresses — and because disjoint memories let a
fetch and a load proceed in the same cycle, so no arbiter of this
study's invention sits between a core and the number being reported.
The image is copied in from external memory by the C runtime before the
first iteration and never read from outside again.

**The boundary is checkable, and it is checked.** Each wrapper counts
every transfer crossing it, split into an instruction side and a data
side, and takes the same two-minus-three-iteration difference the cycle
count uses (§3.3). For all four cores that difference is **zero**: one
hot CoreMark iteration — the iteration the SAIF is captured over — sends
nothing outside the hardened block. A boundary that is stated but not
verified is an intention; this one is a measurement, and §5.1 reports
what enforcing it cost the numbers.

### 3.2 The chain

    ELF → RTL simulation → CRC gate → synthesis → global route
        → netlist → gate-level simulation → SAIF (one hot iteration)
        → report_power

| path | what |
|---|---|
| `sw/port/` | the CoreMark port layer; CoreMark's sources stay byte-unmodified (§9) |
| `sw/` | ELF builds, one per ISA and iteration count |
| `rtl/cmj_<core>.v` | each core's configuration, frozen, shared by the simulator and the flow |
| `rtl/cmj_progmem.sv` | the two tightly-coupled memories hardened inside each cacheless tile |
| `rtl/cm_soc_<core>.v` | simulation wrapper: external memory, sim-control device, boundary traffic counters |
| `sim/` | the Verilator harness and the measurement targets |
| `designs/asap7/<core>/` | `config.mk`, constraints, `units.json`, `pin_policy.json` |
| `scripts/` | parsers and checks, each with a unit test |

Two memory-mapped words are the whole bare-metal contract, and all
three cores see the same two: a byte written to `0x1000_0000` is one
character of stdout, and a 1 written to `0x1000_0008` stops the
simulation. That is why one C runtime, one linker script and one
CoreMark port serve cores whose buses, privilege models and CSR support
have nothing in common. Cycles are counted in the harness rather than
read from a CSR, because ibex has `mcycle`, picorv32 has no
machine-mode CSRs at all, and SERV's CSR block is a build option. The
image carries entry points for both reset conventions in play: `0x000`
for a core that starts at its reset address, `0x180` for ibex, which
fetches from `boot_addr_i + 0x80`.

**The netlist the power is reported on and the netlist that was
simulated are the same netlist**, written from the stage's own ODB by
`flow/write_netlist.tcl`. This is the alignment that lets a SAIF bind
at all: a capture against one stage applied to another leaves nets
unmatched, and §2.2 says what OpenSTA does with those.

**Correctness is gated on the gate-level netlist, not only on RTL.**
The gate is CoreMark's three printed CRCs — not its own error count and
not the exit status, because the port stubs the timer to a constant and
CoreMark therefore reports "must execute for at least 10 secs" on every
run. A converted memory is blackboxed at synthesis so the liberty view
wins, and a blackbox stores nothing; run the netlist without a
behavioural model for it and the register file does not hold values, so
CoreMark fails its CRCs or never terminates rather than quietly
reporting low memory power. `memories.json` records
`behavioral_model: {file, module}` for that reason, and the CRC gate
runs against the netlist for that reason.

### 3.3 Performance: a differential iteration

    CoreMark/MHz = 1e6 / (cycles_3 - cycles_2)

Two ELFs are built per configuration, at `ITERATIONS=2` and
`ITERATIONS=3`, and the difference is one CoreMark iteration. It
cancels reset, `.bss` zeroing, data init, the CRC checks and the whole
printed report — everything that is not the benchmark. It is also what
removes CoreMark's ten-second run rule from a problem no simulated core
can satisfy.

The two ELFs differ by one word of `.data`, and
`//test/coremark_joule/sw:iteration_delta_test` asserts exactly that,
so the subtraction's premise cannot rot.

**These are not reportable CoreMark scores** [1]: a three-iteration run
does not satisfy CoreMark's run rules. The numbers are comparable
within this study and not against published figures.

### 3.4 Activity: one hot iteration

Switching activity has to come from the part of the run that represents
the benchmark, and that is not the whole run. Startup, data init and
the first iteration execute cold; the report at the end is `ee_printf`
and nothing else. So the window is exactly **one iteration, the last
one** — the same quantity the cycle count uses, and the one running
hot. This matches the practice of the papers we compare against, which
select a warm window explicitly [5].

There is an exact, observable anchor for it. CoreMark prints nothing
until its report, so the cycle of the first character out is precisely
where the benchmark loop ended. With `D` the cycles per iteration, the
last iteration spans `[first_output - D, first_output]`, and the
harness records `first_output` alongside the cycle count. Nothing in
the benchmark is modified to mark it. Cycle behaviour is identical
between the RTL and gate-level simulations, so the window is derived
from the cheap RTL run and applied to the expensive netlist one; on
picorv32 that checks out two ways, since the window start computed from
`first_output - D` equals `cycles_2 - report_cost` exactly.

Two capture mistakes are worth not repeating, because both produce a
plausible SAIF rather than an error:

- **Dumping on a time base relative to the window.** Absolute time
  makes the SAIF's `DURATION` span the whole prologue, dividing every
  toggle rate by however far into the run the window starts.
- **Dumping at one clock phase.** Sampling once per cycle always
  catches the clock at the same level, and the SAIF then records a
  clock that never toggles — not a small error on the busiest net in
  the design.

A correct capture is checkable: `clk` should show `TC` equal to twice
the window's cycle count, and the duration should equal one iteration.

### 3.5 Annotation completeness, and the bound on the estimator

§2.2 establishes that OpenSTA silently estimates an unannotated pin.
The claim this study needs is therefore not "we read a SAIF" but "the
estimator contributed nothing", and that claim is made two ways.

**The accounting.** `flow/activity_audit.tcl` loads the same ODB the
power is reported on, reads the same SAIF, and emits facts: OpenSTA's
own annotated and unannotated listings
(`report_activity_annotation -report_annotated -report_unannotated`)
alongside the ODB's view of every pin — master type, port direction,
signal type, net, net signal type. `scripts/classify_pins.py` puts each
unannotated pin in exactly one class, and each class carries a declared
policy:

| class | policy | why |
|---|---|---|
| `clock_network` | benign | OpenSTA takes `2/period` from the SDC exactly; unannotated is the correct state |
| `tied_constant` | benign | driven by a tie cell or wired to a rail: no switching |
| `unconnected` | benign | connected to no net |
| `power_ground` | benign | excluded from the power calculation by construction |
| `scan_test` | benign, with a written reason | tied off for functional operation |
| `top_port` (input) | **fatal** | a levelization root: where a default activity enters and spreads |
| `macro_pin` | **fatal** | an unannotated SRAM is memory energy invented rather than measured |
| `internal_cell_pin` | **fatal** above the design's declared budget | the catch-all, and the class the study exists to empty |
| `unmatched` | **fatal** | OpenSTA named a pin the ODB table does not have: a join failure hiding whatever the pin was |

The per-design budgets and every waiver live in
`designs/asap7/<core>/pin_policy.json`, each with a reason in writing.

**A small unaccounted fraction is allowed, stated, and meant to be
driven down.** The `internal_cell_pin` budget is zero on every design
and is expected to stay there. The `unmatched` budget is a *fraction*
rather than a count, because a fraction is the quantity worth reporting
and worth reducing — a count would churn with every flow change while
saying nothing about whether it is small. Three of the four designs
declare zero. VeeR declares 1.1 % against a measured **1.0128 %**, for a
reason §4.2 gives, and the intent is to whittle it toward zero rather
than to keep it.

What makes that tolerable rather than a loophole is that the sweep does
not care how a pin came to be unannotated. It varies the default the
estimator would use for *every* unannotated pin at once — matched or
not, classified or not — and measures whether the answer moves. The
classification says what was left out; the sweep says what it was
worth.

OpenSTA's own summary line above the listings is deliberately not
parsed. `Power::reportActivityAnnotation` computes `unannotated` as
`pinCount()` minus the size of the annotated map, over two pin sets
that filter power/ground pins differently, in unsigned arithmetic; it
can undercount, and on a design whose annotation reaches pins
`pinCount()` does not count, it underflows. The enumerations below it
are the ground truth, and `classify_pins_test.py` pins that choice.

**The bound.** Counting pins is necessary and not sufficient; what a
reader needs is how much the estimator could move the answer.
`set_power_activity -input` is the knob: it sets the density seeded
into every unannotated root, and §2.2 establishes that this is the only
path by which an invented number enters. `flow/activity_sweep.tcl`
sweeps it from 0.0 (an unannotated root never toggles) through
OpenSTA's own default of 0.1 to 2.0 (it toggles as often as the clock),
and reports power at each point.

`-global` is deliberately **not** used: it short-circuits
`Power::findActivity` and overrides every pin including the annotated
ones, which would make the test pass by destroying what it measures.

The sweep runs in two arms, because a flat line is only evidence if the
knob works. The `vectorless` arm runs before the SAIF is read and is
the positive control; the `saif` arm runs after. Power is reported with
`-digits 10`, because at `report_power`'s default resolution a flat arm
and a small one look the same and the test would pass by not being able
to see.

### 3.6 Corner, parasitics and stage

Power is reported at global route, with parasitics from
`estimate_parasitics -global_routing` rather than from an extracted
SPEF. This is what makes a point cost minutes rather than hours and is
the reason the study screens here; §5.3 states what it costs.

The corner is ASAP7's ORFS default, `CORNER = BC`: **RVT, FF process,
0.77 V, 25 °C**, NLDM. It is the *best-case* corner — the fast process
at the high voltage — not the typical one. §5.4 gives the direction and
the rough size of the difference.

The liberty files actually read are recorded per design in
`<name>_design.json` by the audit, so the corner in this section is
machine-checked against the run rather than asserted here.

**One flow setting is turned off for speed, and exactly one.** bazel-orfs
carries a `FAST_SETTINGS` dict (in `//test:BUILD`, and copied in
`examples/` and `test/smoketest/`) that disables the expensive parts of
the flow for CI. It is the right dict for a smoke test and the wrong one
for a measurement, because most of its entries **change the netlist**:

| setting | what it changes | usable here |
|---|---|---|
| `GPL_TIMING_DRIVEN=0`, `GPL_ROUTABILITY_DRIVEN=0` | placement stops optimising timing and congestion | no |
| `SKIP_CTS_REPAIR_TIMING=1` | no buffer insertion, sizing or VT swap after CTS | no |
| `SKIP_INCREMENTAL_REPAIR=1` | no repair at global route | no |
| `REMOVE_ABC_BUFFERS=1` | strips synthesis buffers instead of repairing | no |
| `FILL_CELLS=""`, `TAPCELL_TCL=""` | no fillers or taps — area, density and leakage | no |
| `PWR_NETS_VOLTAGES=""`, `GND_NETS_VOLTAGES=""` | skips IR-drop at `final` | moot, this study stops at grt |
| **`SKIP_REPORT_METRICS=1`** | **reporting only** | **yes** |

A study cannot buy speed with the thing it measures, so every design
here takes the last line and refuses the rest. Nothing in the study
reads ORFS's metrics: power comes from `flow/power_grt.tcl`, the
achieved period from `flow/period_probe.tcl`, and the floorplan
derivation takes WNS from `sta::worst_slack_cmd` directly. The
distinction between netlist-affecting and analysis-only is not marked in
`FAST_SETTINGS`' own documentation, which is why it is spelled out
here.

### 3.7 Functional-unit attribution

Each design sets `SYNTH_HIERARCHICAL=1` with an explicit
`SYNTH_KEEP_MODULES` and runs OpenROAD with `OPENROAD_HIERARCHICAL=1`,
so module boundaries survive synthesis, placement, CTS and global route
and `report_power -saif -instances` has something to attribute power
to. `units.json` maps each kept Verilog module to an architectural unit
— fetch, decode, execute, load/store, register file, CSR. `synth.tcl`
errors on a kept-module name that is not in the elaborated design, so
the enumeration cannot rot silently: an upstream rename fails the build
instead of quietly moving a unit into "other".

How well this works is a property of the RTL, and it differs sharply:

| core | attribution |
|---|---|
| SERV | excellent — one module per architectural function |
| ibex | excellent — the pipeline stages are modules |
| picorv32 | **poor** — `picorv32.v` defines eight modules and the CPU is one of them; decode, execute, the ALU and control are all inline |

picorv32 therefore carries a written, reasoned waiver in its
`units.json` rather than a silent shortfall. "This core cannot be
attributed" is itself a result worth reporting about open-source RTL.
§5.7 covers the second, mechanical gap.

### 3.8 What sets a CPU core's frequency, and what the SDC must therefore say

A CPU core is not a macro in the middle of a datapath, and constraining
it as though it were produces a netlist optimised for a situation that
never arises. This section states the model, because every frequency and
every watt in §4 depends on it.

**Only register-to-register paths can fail timing closure.** Everything
else — input to register, register to output, input straight through to
output — is an *optimisation target*: a number that tells the tools how
hard to work, not a condition the design must satisfy to be correct.
This is the argument ASAP7's own
`$PLATFORM_DIR/constraints.sdc` makes, and it is the model this study
adopts wholesale.

**For a CPU the argument is stronger than for a macro in general,
because of what is on the other side of the pins.** A core is not wired
into somebody else's combinational cone. It is attached to a
clock-crossing bridge, or to a bus register, or to a GPIO pad — in every
case to something that *terminates* the path rather than continuing it.
There is no correct value for `set_input_delay` on a CPU's bus port,
because the number it wants is the time already consumed upstream of the
pin *within the same cycle*, and upstream of a CPU's pin there is a flop.

So the model is: **assume a register immediately outside every port.**
The consequences follow mechanically.

- An input-to-register path inside the core shares its cycle with the
  outside register's clock-to-q and with the setup at the far end. The
  core's share is most of the period but not all of it, and 0.8 is the
  figure ORFS uses for this core on this PDK. Same for
  register-to-output.
- A combinational path straight through the core has a register at both
  ends, outside, so it gets a smaller share still — 0.6.
- Nothing else about the outside world needs to be known, and in
  particular the clock tree does not. This matters: the time given to
  `set_input_delay` is measured from the clock insertion point, so it
  cannot be written down at all without assuming a clock tree that does
  not exist yet. `set_max_delay -ignore_clock_latency` has no such
  problem, which is why the platform file uses it and this study follows.
- **No hold cells are inserted on IO paths**, because `set_input_delay`
  is what would have demanded them. On a design with VeeR's six hundred
  ports that is a large amount of area and leakage that would otherwise
  be charged to the core for a hold requirement its real environment
  does not impose.

**So the minimum clock period is the reg2reg one, and this study takes
it from the platform's own path group.** `$PLATFORM_DIR/constraints.sdc`
ends by partitioning the design with four `group_path` commands —
`in2reg`, `reg2out`, `reg2reg`, `in2out` — and `flow/period_probe.tcl`
asks for the worst slack in `reg2reg` by name. Two consequences, both
deliberate:

- **The overall WNS is not used, and reporting it would understate every
  core here.** It is the worst slack across all four groups, so it can
  be set by an in2reg or reg2out path whose budget is the 0.8/0.8/0.6
  fraction *this study chose* to stand in for a register outside the
  pin. That budget is an assumption about how the core is connected to
  the world — a clock-crossing bridge, a bus register, a GPIO pad — and
  which of those it is changes the number without changing the design.
  A frequency derived from it would be limited by our own assumption.
- **The group is asked for by name rather than re-derived.** Writing
  `-from [all_registers] -to [all_registers]` in the probe would be a
  second definition of the same partition, free to drift from the file
  that actually constrains the design. The probe also reports the
  group's path count, because a group that matches nothing and a group
  whose worst slack is zero both produce a zero and are very different
  facts.

The same reasoning is what `auto_period` (§8.3) will drive: push the
period until the **reg2reg** slack goes slightly negative, and ignore
what the other three groups are doing, because they are measuring an
environment this study does not model.

**The same model covers the small cores, for the same reason.** Once
§3.1's boundary is met, the memory a small core runs out of is inside
it, so its remaining ports are GPIO-like: either fast enough to fit the
budget, or registered on the other side. Either way the path stops at
the pin. One model, applied to every point — which is what §3.1 says the
comparison is made of.

**What this costs if it is left unsaid** is not small. The platform's
`set_max_delay` default, when a design supplies no budget, is **80 ps**
— a figure its own comment describes as right for "a small macro on
ASAP7". At a 1000 ps period that is a twelvefold over-constraint on
every path touching a port, and an optimiser given an impossible target
does not decline it: it upsizes cells and inserts buffers, and their
power is then reported as the core's. Every design in this study now
sets the budget explicitly (see each `constraints.sdc`); §5.10 records
that the numbers in Table 1 predate it.

---

## 4. Results

### 4.1 The four cores

Table 1. Across nearly two hundred times in CoreMark/MHz, CoreMark/Joule
spans a factor of 92: SERV's extreme serialism costs it 41 million
cycles per iteration, and paying for a 40 kB memory over every one of
them is what dominates its Joule. Every point meets the study's boundary
(§5.1) and every point is verified to send zero transfers outside it
during the iteration measured.

The reader is cautioned on two things instead. Every memory here is a
FakeRAM abstract, and FakeRAM's ASAP7 views charge the same switching
energy and the same leakage for every shape -- so 58--71 % of each
point's power comes from a model that does not know how big the memory
is (§5.1). And CoreMark/Joule is not a discriminating axis across these
four: §4.6 shows it within 1.32x of proportional to CoreMark/MHz over
the three cacheless cores, for reasons that are a property of the
platform's memory model rather than of the designs.

### 4.2 Annotation completeness and the estimator bound

| core | pins listed | annotated (SAIF) | unannotated | unaccounted | verdict |
|---|---|---|---|---|---|
| SERV | 28,025 | 28,025 (100.0000 %) | 0 | 0 | pass |
| picorv32 | 53,240 | 53,240 (100.0000 %) | 0 | 0 | pass |
| ibex | 80,876 | 80,876 (100.0000 %) | 0 | 0 | pass |
| VeeR EH1 | 754,718 | 747,070 (98.9866 %) | 7,648 | **1.0128 %** | pass |

**Table 2.** Pin activity annotation at global route. "Pins listed" is
OpenSTA's own pin set for power — leaf pins plus top-level ports, less
internal and power/ground pins. Every class in §3.5 is empty for the
three cacheless cores: there is nothing to waive. The counts moved with
§5.1 -- the tiles grew memories, five macros and a wider clock tree --
and the annotation stayed complete through that change and through the
move onto FakeRAM's interface, which replaced every macro pin in the
design. Complete annotation survived a total change of the macro pin
set, which is the sort of thing a gate is for.

**VeeR is the exception, and its 7,648 are itemised rather than
tolerated.** Four are waived by name: the four top-level input ports
that `cm_soc_veer.sv` ties to constants, which Verilator therefore never
emits into the SAIF. There were seven until §5.11 retired the rename
workaround whose three pins made up the difference. The
remaining 7,644 — the 1.0128 % — are pins OpenSTA's hierarchical network
carries that odb's own instance enumeration does not reach: the same
clock cells whose SAIF entries had to be dropped, for the same reason,
their names containing the hierarchy separator. They were never going
to be annotated; what is conceded is classifying them from the database
rather than from their names, and the intent is to drive the fraction to
zero rather than keep it (§3.5).

| core | SAIF arm spread | vectorless arm spread | vectorless at OpenSTA's default | measured |
|---|---|---|---|---|
| SERV | **0.0000 %** | 24.04 % | 47.02 mW | 43.423 mW |
| picorv32 | **0.0000 %** | 86.27 % | 67.65 mW | 44.430 mW |
| ibex | **0.0000 %** | 173.08 % | 35.61 mW | 19.464 mW |
| VeeR EH1 | **0.0000 %** | 474.61 % | 54.66 mW | 86.504 mW |

**Table 3.** Total power as the default activity seeded into
unannotated roots is swept over 0.0, 0.1, 1.0 and 2.0 toggles per clock
period. The SAIF-driven total is bit-identical at ten significant
figures at every point — for picorv32, 2.1383069e-02 W four times. The
vectorless total over the same sweep runs 42.16 → 52.29 mW (SERV),
43.44 → 80.92 mW (picorv32), 15.93 → 43.51 mW (ibex) and 21.72 →
124.79 mW (VeeR).

The control arm's spread is the part of this table that is not a
constant of the study: 24 % on SERV, 86 % on picorv32, 173 % on ibex,
475 % on VeeR. Across the three cacheless cores it orders itself by how
much of each design the estimator is free to invent — least room where a
macro's internal power dominates a total that seeding an input activity
cannot move, most where the design is logic whose activity it has to
guess. SERV is the extreme — 71 % of its power is macro — and it is the
one core where a reader might reasonably ask whether the control is
strong enough for the null result to mean much. It still moves 6.1 mW,
against a SAIF arm that moves zero at ten significant figures, but it
is the weakest control in the study and it is weakest for a reason
worth knowing.

**VeeR breaks that ordering, and the reason is the clock gates.** At
59 % macro it sits between picorv32 and ibex, yet its control arm moves
four and a half times its own floor — 21.58 mW at zero activity against
123.38 mW at two toggles per cycle. It is the one core in the study with
a real clock-gating network (§3.9), and a gated clock's activity *is*
the enable's activity: told the enables never toggle, the estimator
switches off a clock tree that carries 29.5 % of the design's power;
told they toggle every cycle, it runs the whole tree flat out. Clock
gating is precisely the structure that gives a probabilistic estimator
the most room, which is worth stating plainly — the spread is not a
defect of VeeR's netlist but a measurement of how much a vectorless
report would be guessing about it. The SAIF arm still does not move at
all.

Read together, Tables 2 and 3 are the study's central methodological
claim, and it is a measured one rather than an assurance: **OpenSTA's
probabilistic activity model contributes nothing to the reported
energy.** The knob that would let it contribute is demonstrably live —
it moves the same design's power by 24 to 475 % when activity is not
annotated — and it moves the annotated result by zero.

**VeeR is the case that shows why the sweep, not the audit, is the
claim.** It is the one design with pins unaccounted for — 1.0128 % of
its pin set — and its SAIF arm is still bit-identical at
8.6504e-02 W across the whole sweep, while its vectorless arm runs
21.7 mW to 124.8 mW. The sweep does not care why a pin is unannotated:
it varies the default the estimator would use for every one of them at
once. Those 7,648 pins are worth exactly nothing to the reported number,
and that is measured rather than argued.

A secondary observation falls out of the control arm. At OpenSTA's own
default activity, a vectorless report would have said 15.6 mW for
picorv32 against a measured 6.58 mW (2.4×), and 26.3 mW for ibex
against 7.77 mW (3.4×) — and the overstatement is *differential*,
1.1× for SERV against 3.4× for ibex. A vectorless CoreMark/Joule
comparison of these three cores would not merely be wrong in
magnitude; it would rank them differently.

### 4.3 Reproduction

```sh
# the cheap gates: every parser and every check, over fixtures (seconds)
bazelisk test //test/coremark_joule/scripts/...

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

# re-measure and rewrite the pinned results; then the plot, with no flow in the loop
bazelisk run   //test/coremark_joule:pin
bazelisk build //test/coremark_joule:plot
```

`results.json` is committed, so iterating on the presentation never
re-runs a flow and a number that changes shows up as a line in a pull
request. SERV's runs are ~10^8 cycles each, so the report is minutes,
not seconds. When something fails, follow the `debug-rtl-sim` skill
rather than reaching for a waveform.

### 4.4 A 22 nm literature series, and what it is and is not

The red open squares in Figure 1 are not measurements from this study.
They are CVA6, CVA6S+ and the XuanTie C910 as published in *Ramping Up
Open-Source RISC-V Cores* [5]: GlobalFoundries 22 FDX, Synopsys
PrimeTime 2022.03, post-layout netlist simulation, typical corner
(0.8 V, TT, 25 °C, RC typical), 64 KB two-way L1 instruction and data
caches. CoreMark/Joule is *derived* here as
`CoreMark/MHz × frequency / power` from that paper's own numbers.

They are drawn in their own colour and marker because reading the two
series as one trend would be wrong, in four separate ways:

- **Different process.** ASAP7 is a predictive 7 nm kit, not a foundry
  PDK. Its absolute energy is not a silicon number.
- **Different tools and stage.** PrimeTime on a post-layout netlist
  against `report_power` at global route with estimated parasitics.
- **Different corner.** Their typical against our best case (§5.4).
- **Different boundary — and theirs is not stated.** Our points include
  no memory at all (§5.1). Theirs configure 64 KB L1s, but *the paper
  does not say whether the reported power includes them*: Figure 7's
  breakdown names Fetch, Decode, Issue, Integer Execution, Load/Store
  Unit, Floating Point and Control Flow, and no cache term appears in
  it. We therefore cannot claim, as an earlier draft of this document
  did, that the red series is measured at core + L1.

A fifth caveat applies to the derivation rather than to the source. The
paper's power figures are stated for the `matmult-int` benchmark, while
its CoreMark/MHz is, necessarily, CoreMark. The derived CoreMark/Joule
therefore combines a CoreMark performance number with a matmult-int
power number, and is an estimate of that paper's energy efficiency
rather than a figure it reports.

What the series is good for is the shape: across a 2.2× range in
CoreMark/MHz, the derived CoreMark/Joule is nearly flat
(28.2k / 27.1k / 29.4k). That is the question this study asks,
answered independently at a different node with different tools.

### 4.5 What else could be plotted, and why almost nothing can

Figure 1 has two series because two is all there is, and the reason is
worth setting out as a criterion rather than as an apology. To place a
published core on these axes at the boundary of §3.1, a source must
supply four things:

1. **CoreMark/MHz**, on a stated compiler and ISA.
2. **A power figure**, in watts, with the frequency it was taken at.
3. **A stated measurement boundary** — specifically, whether the L1
   caches are inside the reported power.
4. **The same workload for both halves.** A CoreMark/Joule derived from
   a CoreMark performance number and a power number taken on a different
   benchmark is an estimate, not a reported figure.

The first is common; the rest are not. Of the sources checked while
building this study:

| source | CoreMark/MHz | power | boundary stated | same workload |
|---|---|---|---|---|
| *Ramping Up Open-Source RISC-V Cores* (CF'25) [5] | yes, 3 cores | yes, Fig. 7 | **no** — Fig. 7 names Fetch, Decode, Issue, Integer Execution, LSU, FP, Control Flow; no cache term, and no sentence says whether the 64 kB L1s are inside | **no** — power is for `matmult-int` |
| *The Cost of Application-Class Processing* [6] | not reported | yes, silicon | not established from the abstract; the full text was not surveyed here | n/a |
| *CoreMark Benchmarking for SweRV* [11] | **4.94**, and the exact generator configuration | no — FPGA prototype at 40 MHz, no ASIC power | n/a | n/a |
| SonicBOOM (CARRV 2020) | 6.2 | no | n/a | n/a |

So exactly one source clears enough of the bar to be drawn at all, and
it clears items 3 and 4 only by our choosing to derive from it anyway —
which is why §4.4 draws it in its own colour with the derivation stated,
rather than merging it into the measured series. The rest contribute an
x-coordinate and nothing else; `results.json` carries them under
`references`, and the plot shows them as grey ticks on the x-axis rather
than inventing a y.

**This is the argument for the study rather than a complaint about the
literature.** A CoreMark/MHz is cheap to publish and a CoreMark/Joule at
a stated boundary is not, so the second is largely missing — and a
number that is missing cannot be argued with. Producing it from an open
flow, with the boundary stated and the annotation audited, is the gap
this work is in.

### 4.6 Is the shape real? The boundary, tested twice

This section has now made a prediction, tested it, been half right, and
found the other half. All three steps are kept, because the half that
was wrong is the more useful one.

**The defect.** The three cacheless cores fell on a straight line in
log--log axes, **slope 0.868 with R^2 = 0.999**, and that line was very
nearly the x-axis in disguise. `CoreMark/Joule = (CoreMark/MHz) *
(f/P)`, so if `f/P` is constant the slope is 1 by construction and the
energy axis carries no information at all. Across a 101x span in
CoreMark/MHz their `f/P` spanned only **1.89x**.

**The prediction**, stated falsifiably: the cause was §5.1's boundary --
with no memory hardened, what remained was three small blocks of logic
clocked within 1.7x of each other, and the part whose cost actually
differs between a bit-serial core and a pipelined one was outside the
measurement. *If hardening the memories leaves the slope at 0.85, the
degeneracy was not the boundary's fault and something else is wrong.*

**Test one: VeeR EH1**, the one core that already met the boundary.
Adding it broke the line -- R^2 fell from 0.999 to 0.561 -- and
extrapolating the cacheless trend to its performance overpredicted its
efficiency by **15.2x**.

**Test two: harden the other three** (§5.1) and re-fit. This is the
direct test, and it splits cleanly.

| | before §5.1 | after §5.1 | after §8.3 |
|---|---|---|---|
| extrapolation to VeeR overpredicts by | 15.2x | 5.53x | **5.54x** |
| slope, three cacheless cores | 0.868 | 0.954 | **0.946** |
| R^2 of that fit | 0.999 | 0.9997 | **0.9994** |
| `f/P` spread, those three | 1.89x | 1.26x | **1.32x** |
| power spread, those three | 1.15x | 1.36x | **2.28x** |
| slope, all four | 0.535 | 0.745 | **0.736** |
| R^2, all four | 0.561 | 0.862 | **0.859** |

The third column is the same four points measured at derived periods
rather than chosen ones (§5.5). The second column's figures are
recomputed here: `scripts/fit_results.py` is now what produces them, and
running it over the previously pinned results returned 5.53x rather than
the 5.65x the paper carried, along with 0.745 and 0.862 for the
all-four fit against a published 0.742 and 0.858. Those were typed in by
hand and were the only numbers in the paper no artifact produced.

**The prediction held, and it was most of the error.** The
extrapolation gap closed from 15.2x to 5.53x: **64 % of the way**. The
boundary was the dominant cause of the disagreement between the
cacheless cores and the one compliant one, exactly as claimed, and that
part of §5.1 is now a measured correction rather than an argument.

**The degeneracy did not go away. It got worse.** The line among the
three is *tighter* than before -- slope 0.946, `f/P` spanning **1.32x**
across 101x of performance, against 1.89x. The diagnosis was right about
the cause and wrong about the consequence: removing the old reason for
the degeneracy installed a new one.

**The new reason is the platform's memory model.** Every memory in this
study is a FakeRAM abstract, and FakeRAM's ASAP7 views carry *one*
switching energy and *one* leakage number for every shape, from 64x21 to
256x256 (§5.1). Those macros are 57--72 % of each point's power (§4.7).
So the dominant term is proportional to how often a core touches memory
and how many macros it has, and is independent of how much memory it
has. Three cores running the same benchmark out of the same number of
macros differ mostly in access rate, and the axis reflects that.

So the reading of the straight line has moved twice. Before §5.1 it
meant *the measurement is blind to the memory system*. After §5.1 it
means *the measurement is dominated by a memory model that does not
know how big the memories are*. Both are degenerate, and neither makes
CoreMark/Joule a discriminating axis among cores of this class. The
second is at least uniform: the same model is applied to all four
points, so what the comparison says about the cores is not confounded
by the memory being modelled differently for each of them.

**Three caveats on the statistics.** A three-point fit has one degree of
freedom, so R^2 = 0.9997 is close to meaningless as evidence -- it is
reported because its *movement* is informative, not its value. The four
frequencies are now derived rather than chosen (§5.5), so `f/P` no
longer mixes a measured power with a guessed frequency -- though each is
one flow's closing period, not a Pareto front (§8.4).
And the memory model charges every shape the same energy (§5.1), which
lands entirely on the term that dominates.

**What it takes to make the axis mean something.** A memory model whose
energy depends on the size of the memory, first of all -- that work is
planned in ORFS and this study inherits it when it lands. Then cores
whose memory systems genuinely differ (§7's roadmap). The third item on
this list used to be "the same cores at their own achieved f_max"; §8.3
has since done that, and §5.5 reports what it was worth -- the frequency
correction was large on the performance axis and worth at most 3.5 % on
the energy axis, which is one degeneracy ruled out rather than removed.
The present data still cannot separate a real law from the memory
model's flatness, and says so.

**Where the four points actually land.** VeeR delivers **1.95x** ibex's
performance per clock at **0.35x** its CoreMark/Joule, drawing 4.44x
the power. Before §5.1 the same comparison read 0.124x and 11.8x. The
conclusion a reader would have drawn from the old numbers -- that the
minimal cores dominate the energy metric -- does not survive the
correction; the conclusion available from the new ones is much weaker,
which is the honest state of the evidence.

**A corroboration, still carefully.** VeeR at 34,863 CoreMark/Joule
lands **1.19x to 1.29x** above the GF 22 FDX series of §4.4
(27,108--29,412); ibex sits 3.4x above it. That is a consistency check between cores
measured at a stated core-plus-L1 boundary on different nodes with
different tools, and it is worth more now that three of this study's
four points meet that boundary than it was when one did. It remains
consistency, not validation: §4.4's caveats are unchanged.

### 4.7 Where the power goes

`report_power` groups by cell kind, and the grouping turns §4.6's
statistical findings into mechanical ones. Table 7 is the state after
§5.1; the row each core replaced is kept underneath it, because the
difference between the two is the whole of §5.1's correction and it is
not evenly distributed.

| core | total | Clock | Sequential | Combinational | **Macro** |
|---|---|---|---|---|---|
| SERV | **43.40 mW** | 6.25 (14.4 %) | 4.49 (10.3 %) | 1.33 (3.1 %) | **31.40 (72.4 %)** |
| picorv32 | **44.40 mW** | 8.04 (18.1 %) | 6.01 (13.5 %) | 0.92 (2.1 %) | **29.50 (66.4 %)** |
| ibex | **19.50 mW** | 3.13 (16.1 %) | 2.64 (13.5 %) | 2.53 (13.0 %) | **11.20 (57.4 %)** |
| VeeR EH1 | **86.50 mW** | 25.60 (29.6 %) | 6.91 (8.0 %) | 3.33 (3.8 %) | **50.70 (58.6 %)** |
| *SERV, core only* | *6.68* | *2.85* | *2.83* | *1.00* | *0.00* |
| *picorv32, core only* | *6.43* | *2.84* | *2.89* | *0.70* | *0.00* |
| *ibex, core only* | *7.37* | *2.46* | *2.64* | *2.27* | *0.00* |

**The memory is the measurement.** 57--72 % of every point: 72.4 % of SERV down to
57.4 % of ibex. The old rows show what that meant: for these three cores
the component that was missing was between four and nine times
everything that was present. §4.6's extrapolation error of 15.2x was
this column.

**The logic did not stay still either**, and the direction is worth
noting. Clock power roughly doubles on every cacheless core -- SERV
2.85 to 5.49 mW, picorv32 2.84 to 3.79, ibex 2.46 to 3.41 -- because
the die grew to hold the macros and the clock tree grew with it.
Sequential power is unchanged to two digits, which is the expected
control: the flop count did not change, and neither did the benchmark.
A measurement where the term that should move moves and the term that
should not stay put is one more thing that would have shown a mistake
if there were one.

**Why the axis re-flattened.** Before §5.1 the three cacheless cores
were degenerate because clock plus sequential -- 65--89 % of each total
-- is set by how much state a design has rather than how fast it
retires work, and the three have similar amounts of state. After §5.1
they are degenerate because the macro column, 58--71 % of each total,
is *the same memory* in all three. The term that actually tracks the
architecture is combinational power, 0.82--2.88 mW, and it is the
smallest term in every row. That is §4.6's 1.32x `f/P` spread stated as
a mechanism.

**VeeR is the one row that looks different, and it is instructive.**
Its macro fraction is 59 %, not 85 %, and its clock power is 25.60 mW
-- 8.2x ibex's -- because it has an order of magnitude more state and a
real clock-gating network to distribute. Its logic alone is 35.84 mW
against ibex's 8.30 mW: **4.3x the logic power for 1.95x the
performance per clock.** (The three figures in this paragraph are the
§4.7 rows added up. Earlier versions carried 4.9x, then 4.6x, for the
clock ratio and 8.94 mW for ibex's logic, neither of which was what the
table beside them said.) The memory is no longer the whole story once
a core is big enough to have one worth having.

**A caveat on the macro column specifically.** Every row's macro figure
comes from FakeRAM, and FakeRAM's ASAP7 views carry one switching energy
and one leakage number for every shape (§5.1). So the column is
proportional to how often each core touches memory and how many macros
it has, and carries no information about how large those memories are.
All four rows are equally affected, which is the point of putting them
on one generator -- but it means this column measures access behaviour,
not memory cost.

This is the SRAM-against-logic split §8.1 asks for, arriving early
because §5.1 put something in the macro column for every core.

### 4.8 A rack-level reading of Figure 1

Figure 1's axes turn out to be the two axes a GPU rack cares about in a
host CPU, and the relation between them is tight enough to write down.
This section is a **model**, with its assumptions stated; it uses
published power figures and none of this study's own measurements,
except at the end.

**The setup.** A rack has a fixed power budget. It holds GPUs and the
host CPUs that feed them. Too slow a host and the GPU waits; too fast a
host and its power crowds GPUs out of the budget. Both failures cost
delivered work, so there is an optimum.

Per GPU, write

    tau  host CPU throughput available to it       (CoreMark/s)
    r    host work the GPU demands per GPU-second  (CoreMark/s)
    E    host energy efficiency                    (CoreMark/Joule)
    P_g  GPU power                                 (W)
    pi   host CPU power charged to that GPU        (W)

While the host is on the critical path — launching kernels, preparing
the next batch, driving collectives — the GPU is idle, so

    U = tau / (tau + r)        and        pi = tau / E

and the number of GPUs the rack can hold is `N = P_rack / (P_g + pi)`.
Delivered work is `N x U`. Maximising it over `tau` gives

    tau* = sqrt(P_g . r . E)
    pi*  = sqrt(P_g . r / E)
    U*   = P_g / (P_g + pi*)

**The last line is the result, and it needs no CoreMark number at all:
at the optimum, GPU utilization equals the GPU's share of the CPU-plus-GPU
power.** Provision the host at a tenth of the GPU's power and the
economics want the GPU about 91 % busy; provision it at a third and they
want 75 %. Chasing higher utilization than that is buying it with power
that would have held another GPU.

**What the industry actually provisions.** Two generations, two CPU
ISAs, one ratio:

| system | GPU | host CPU | host W per GPU | ratio | U* |
|---|---|---|---|---|---|
| DGX H100 [12] | 8 × H100 SXM5, 700 W | 2 × Xeon Platinum 8480C, 350 W | 87.5 W | **0.125** | 88.9 % |
| GB200 NVL72 [13] | 72 × B200, 1200 W | 36 × Grace, ~300 W incl. LPDDR/IO | 150 W | **0.125** | 88.9 % |

Exactly one eighth in both cases, which under this model corresponds to
an optimum at **88.9 % GPU utilization** — and, since `U = tau/(tau+r)`,
to a host provisioned at **eight times** the throughput the GPU's host
work demands. Whether that ratio was arrived at by this reasoning or by
measurement, it is the point the model says to sit at.

**Why the last few points of utilization are so expensive.** Rearranging,
`tau = r . U/(1-U)`: utilization enters as *odds*, so each increment
costs throughput multiplicatively.

| from → to | odds | host throughput needed |
|---|---|---|
| 80 % → 90 % | 4 → 9 | ×2.25 |
| 90 % → 95 % | 9 → 19 | ×2.11 |
| 95 % → 99 % | 19 → 99 | **×5.2** |

**And why buying it with frequency is worse than it looks.** §2.3 gives
the scaling: in the voltage regime `tau ∝ f` while `E ∝ 1/f²`, so

    pi = tau / E  ∝  f³

**Host power per GPU grows as the cube of host frequency**, while
utilization improves only through the odds ratio. Doubling the host
clock of a DGX-H100-shaped system takes π from 87.5 W to 700 W and U
from 88.9 % to 94.1 % — and delivers **60 % of the optimum's rack
throughput**, because the rack now holds 1.8× fewer GPUs. That is the
"too high and fewer GPUs fit" half of the problem, quantified.

**What it constrains, on Figure 1's own axes.** For a target utilization
`U` and a host power budget `pi` per GPU:

    CoreMark/s      tau  >=  r . U/(1-U)                  (the x-axis, scaled)
    CoreMark/Joule  E    >=  r . U / ((1-U) . pi)         (the y-axis)
    CoreMark/MHz    CM/MHz >= r . U / ((1-U) . f . n)     (n cores at f)

So **a target utilization is a corner in the upper right of Figure 1**: a
horizontal floor set by the power slice, and a vertical floor set by how
much of the host work is serial. The two are not interchangeable, and
they map onto the two halves of Amdahl's argument as it appears in a
rack. Host work that is on one dependency chain — a kernel launch, a
Python frame, one collective's orchestration — is served by
CoreMark/MHz × f and cannot be bought with more cores. Host work that is
parallel is served by throughput, and how much of it fits in `pi` is set
by CoreMark/Joule. **The y-axis is the rack-relevant axis for everything
except the critical path.**

**Where this study's cores would sit, with the caveat first.** These are
ASAP7 numbers on a predictive kit at the best-case corner (§5.4, §5.6),
and the comparison below is an illustration of the model's shape, not a
claim about silicon. In the 87.5 W host slice of a DGX-H100-shaped
system, a host built from this study's ibex point — 98,176
CoreMark/Joule — would deliver `87.5 × 98,176 ≈ 8.6 M CoreMark/s`, which
at 2,045 CoreMark per core is some four thousand cores. The number is
not a design proposal; what it shows is that the slice is set by `E` and
nothing else, and that a core whose CoreMark/Joule is an order of
magnitude worse buys an order of magnitude less host throughput for the
same rack cost.

That this figure moved by 2.8x between drafts is the model working as
intended rather than an erratum. §5.1 put ibex's memory inside the
measurement; the host slice fell by the same factor, because a memory
the core cannot run without draws power in a rack whether or not the
study was counting it. A rack model fed CoreMark/Joule figures whose
boundary is unstated is off by whatever that boundary was worth.

**CoreMark is a proxy for one term of `r`, and not a good proxy for the
rest.** This is the sharpest limit on everything above, so it is stated
plainly rather than left in the caveats. CoreMark is a small, entirely
cache-resident integer benchmark with predictable control flow — that is
what makes it measurable in a gate-level simulation at all (§3.4), and
it is also what makes it narrow. A GPU rack's host work is mostly not
that: framework and Python frames, driver and runtime code, marshalling
batches through memory, syscalls, the network stack, page management,
and the orchestration of collectives. Those are bound by memory latency,
TLB reach, last-level cache and kernel-boundary cost, and **CoreMark
measures none of them.**

So `r` expressed in CoreMark says how much *pipeline throughput* the GPU
demands of its host, and is silent on everything else. Two hosts with
identical CoreMark/s and different memory systems will not deliver the
same utilization, and the one with the better memory system will win by
a margin this model cannot see. The equations are the right shape; the
units are the honest part to distrust.

It is the same limit as §3.1's boundary seen from the other end.
CoreMark's working set is exactly what fits inside core-plus-L1, which
is why this study can measure it precisely — and why it says nothing
about the last-level cache, the memory controllers or the interconnect,
which is where a real host spends a large share of its energy.

**What the model does not include**, so it is not read as more than it
is: host memory and its power, the NVLink and network fabric, cooling
overhead, and any host work that scales with GPU count rather than per
GPU. It also assumes the host and the GPU do not overlap — the pure
serial case. Real runtimes pipeline, which raises `U` at the same `tau`
and moves the optimum toward a cheaper host; the direction of that error
is known and it is the kind that makes an expensive host look better
than it is.

---

## 5. Threats to validity

### 5.1 The boundary, met, and what it cost

An earlier draft of this section was a confession. The harness RAM was
simulation-only: never hardened, so every fetch and load in the
benchmark was served by memory that cost zero area and zero energy.
picorv32 and SERV have no caches at all, so their entire memory system
was outside the measurement; ibex was configured with `ICache=0`, so
the same applied. The gap ran one way, and it ran against the wide
machines: a design that spends area and energy on an L1 to go faster
was charged for the L1 and credited with the speed, while a design with
no L1 was charged for neither and still got a free, perfect memory.
SERV's 41 million cycles per iteration were 41 million accesses to that
free memory.

**The three cacheless cores now harden the memory they run out of.**
Each tile -- `cmj_serv`, `cmj_picorv32`, `cmj_ibex` -- contains the core
plus a 32 kB instruction memory and an 8 kB data memory, both generated
as real abstracts by `behavioral_macros()` from `rtl/cmj_progmem.sv`,
both placed and routed with the core, and both inside what `DESIGN_NAME`
names and therefore inside what `report_power` totals.

Table 8. The cost of meeting the study's own rule. CoreMark/MHz is
unchanged to every digit -- the memory moved inside the boundary without
changing a single cycle of any run -- so the entire movement is in the
energy axis and is attributable to nothing else.

| core | CoreMark/MHz | CoreMark/Joule, core only | CoreMark/Joule, core + L1 | factor |
|---|---|---|---|---|
| SERV | 0.0243 | 5,190 | **1,277** | 4.06x |
| picorv32 | 0.5531 | 86,024 | **26,676** | 3.23x |
| ibex | 2.4543 | 277,510 | **98,176** | 2.83x |
| VeeR EH1 | 4.7978 | 34,863 | 34,863 | 1.00x (already met) |

Three things in that table are worth separating.

**The correction is large.** Between 5.7x and 9.8x. Any CoreMark/Joule
figure quoted for a small core without saying whether its memory was in
the measurement is uninterpretable at roughly an order of magnitude,
which is wider than the difference between most of the cores anyone
would want to compare.

**The correction shrinks as the core grows.** 9.83x, 7.33x, 5.73x, in
order of CoreMark/MHz. The memory is the same in all three tiles, so a
larger core amortises a fixed overhead over more work per cycle. That
is the mechanism by which the cacheless boundary flattered small cores
specifically, and it is why the straight line of §4.6 existed at all.

**The ordering changes.** Before, ibex looked 8.08x better than VeeR EH1
on CoreMark/Joule. Measured at the same boundary it is 1.41x better, on
1.95x less performance per clock. The conclusion a reader would have
drawn from the old numbers -- that the minimal cores dominate the energy
metric -- does not survive the correction.

**Verified, not asserted.** Each tile's wrapper counts every transfer
that crosses its boundary, split into an instruction side and a data
side, and `scripts/bus_probe.py` takes the same two-minus-three
iteration difference the cycle count uses. All four cores in the study
now send **zero transfers per hot iteration** on every external
counter: the boot copy is 51k--70k fetches and 7k--8.5k data accesses,
and the hot iteration adds none of either. The benchmark is resident
inside the hardened block, and that is a measurement rather than a
design intention.

    bazelisk build //test/coremark_joule/sim:serv_rv32i_bus_traffic \
                   //test/coremark_joule/sim:picorv32_rv32im_bus_traffic \
                   //test/coremark_joule/sim:ibex_rv32imc_bus_traffic \
                   //test/coremark_joule/sim:veer_rv32imc_bus_traffic

**What is still open, and it is not small.**

*The memory model does not know how big the memories are.* Every macro
in this study is a FakeRAM abstract, generated by the same tool that
produced the platform's own `fakeram7_*` views -- deliberately, because
the memory is 58--71 % of every point's power and a cross-core energy
comparison cannot afford to have its largest term come from two
different models. But FakeRAM's ASAP7 backend emits **one** switching
energy and **one** leakage number for every shape it is asked for:

| shipped shape | area | `cell_leakage_power` | `clk` `internal_power` |
|---|---|---|---|
| `fakeram7_64x21` | 56.4 um^2 | 128.9 | 1.345 |
| `fakeram7_256x32` | 344.0 um^2 | 128.9 | 1.345 |
| `fakeram7_256x256` | 2,751.9 um^2 | 128.9 | 1.345 |
| `fakeram7_2048x39` | 3,353.9 um^2 | 128.9 | 1.345 |

Area scales; energy and leakage do not. A 256x256 memory is charged
exactly what a 64x21 is charged, per access and at rest. The name is
honest -- it is a fake RAM, built to produce a floorplannable macro
rather than to measure energy -- and the study uses it anyway because
*uniformly wrong* is a property a comparison can survive and *wrong in
two different ways* is not.

What that costs, stated plainly: the macro column of §4.7 measures how
often each core touches memory and how many macros it has, and carries
no information about how much memory each core has. Make the memories
half the size and no number in this paper moves. That is the single
largest thing standing between this study and an energy measurement,
and it is being fixed in ORFS rather than worked around here.

*ibex is measured with `ICache=0`, and that is a finding rather than a
gap.* An earlier draft called it the other half of this section and
assumed turning the cache on would close it. It was built and measured,
and it does not.

Two things stop it. **The cache cannot buy a cycle.** It sits in front
of a tightly-coupled memory that already answers in one, so
CoreMark/MHz is 2.4543 with the cache on and 2.4543 with it off --
identical to the digit, on both marches. **And it cannot hold the
benchmark.** ibex's cache is 4 kB (`IC_SIZE_BYTES` is a package
parameter, not one an instantiation can override) against 24--30 kB of
`.text`, so the configuration that would exercise it -- `.text` in
external memory, fetched through the cache, which is what VeeR does --
would miss continuously and break this section's own residency check.
VeeR gets away with that arrangement because its cache is 16 kB and
CoreMark fits.

What the cache does change is energy, and mostly for a reason that
belongs to the memory model:

| | CoreMark/MHz | CoreMark/Joule | power | macro |
|---|---|---|---|---|
| `ICache=0` (reported) | 2.4543 | 99,284 | 20.60 mW | 11.90 mW |
| `ICache=1` | 2.4543 | 64,316 | 31.80 mW | 21.40 mW |

Both rows are measured at 1200 ps, the period ibex was built at before
§5.5 derived 1282 ps, so the comparison between them stands while
neither is the current reported point. Table 1 has that.

A 1.54x energy penalty for no performance at all, and 9.5 mW of the
11.2 mW rise is macro power. The mechanism is arithmetic: a cache hit
reads both ways' tags and both ways' data, four macro accesses, in
place of one access to the program memory -- and FakeRAM charges the
same energy per access whatever the memory's size. Four small accesses
therefore cost four times one large one. In silicon they cost a
fraction of it, and that difference is the entire reason caches exist.
**Under this memory model a cache can only ever lose**, so the 1.54x
is not a measurement of ibex's cache; it is a measurement of the model,
and the sharpest one in this paper.

Both configurations are kept.
`//test/coremark_joule/designs/asap7/ibex_icache` builds the cache
version to global route, which keeps the ASAP7 `prim_ram_1p` and the
two cache-RAM macros from rotting -- a configuration that silently
reverted to flip-flops would be 44,032 of them, twenty times ibex's own
flop count, and would fail there rather than in a number nobody
re-derives. Supplying that `prim_ram_1p` is not a change to ibex:
lowRISC ships the primitive twice, `prim_generic` and `prim_xilinx`
side by side, which is the library saying a real target provides its
own. No ibex source is modified and `ibex_top`'s parameters are
untouched.

When the memory power model knows how big a memory is, this becomes a
real experiment and the table above should be re-measured rather than
cited.

*The memory is the study's, not the cores'.* None of the three
repositories ships a memory; their testbenches use simulation arrays.
So the sizes, the port shape and the address map are choices this study
made and documented (`sw/port/link.ld`, `rtl/cmj_progmem.sv`) rather
than something taken from the designs. They are held constant across
every core and every march precisely so that the memory is not a
variable in a comparison that exists to have only one, but a different
defensible choice would move all three numbers together.

*A core can be charged for toggling it does not have to do.* Each tile
presents the core's address bus to the macro's address pins directly,
with no register in between, so a core whose address bus moves between
accesses pays for that movement in the macro's input-pin energy. SERV
does: its datapath is bit-serial, and it has the **highest** macro power
of the three (56.0 mW, against picorv32's 39.5 and ibex's 33.2) despite
by far the lowest access rate. That is real for this netlist and it
would be real in silicon built this way, but it is a property of the
tile rather than of SERV, and registering the address would change it.
It is left as it is and reported rather than quietly fixed, because
fixing it changes a measured number.

**Above about 5 CoreMark/MHz the boundary stops being a caveat and
becomes the measurement**, which is why it had to be settled before the
first core in that range rather than after. Those cores arrive as tiles
or SoCs with L1s, an L2, an interconnect and peripherals attached.
Harden what the repository hands you and the uncore swamps the core's
energy; harden less than the L1 and the misses are served by a free
memory that no longer resembles how it runs. Core plus L1, with the L2
and everything past it excluded, is the line that can be drawn on every
one of them -- and §7's roadmap now starts from four points that are on
it rather than one.

### 5.2 Zero-delay simulation carries no glitch power

The gate-level simulator is Verilator: two-state and zero-delay. It
cannot produce a glitch, because it has no notion of a delay for one to
arise from. Signoff practice is an SDF-annotated, event-driven
simulation precisely so that glitch power is captured, and the
literature treats the difference between zero-delay and SDF-annotated
activity as a first-order term rather than a refinement [7, 8].

This study therefore **under-reports dynamic power**, and the
under-reporting is not uniform: a design with deep combinational logic
between registers glitches more than a short pipeline, so the bias
distorts the comparison between cores and not only the absolute
numbers. SERV's bit-serial datapath and ibex's two-stage pipeline are
at opposite ends of that. The size of the effect is not measured here;
putting a number on it — one design, one short window, an SDF-annotated
event-driven run against the same window's Verilator SAIF — is the
single most valuable outstanding calibration.

The direction of this bias is *opposite* to §5.1's: glitch power would
push every point down in CoreMark/Joule, and most for the cores with
the deepest logic.

### 5.3 Estimated, not extracted, parasitics

`estimate_parasitics -global_routing` is a model of the wiring, not the
wiring. Switching power is `α·C·V²·f`, and the `C` here is the
estimate's. That is the deliberate cost of screening at global route,
and it is uncalibrated: no point in this study has been re-measured at
`6_final` with an extracted SPEF. One such point, on one core, would
bound it.

### 5.4 The corner is ASAP7's best case, not its typical

`CORNER = BC` means FF process, 0.77 V, 25 °C (§3.6). Two consequences.
Dynamic power scales with `V²`, so at the nominal 0.70 V the same
activity would give roughly `(0.70/0.77)² ≈ 0.83` of the reported
switching power — about 17 % lower. Leakage is higher again at FF than
at TT, by more than the voltage ratio alone. The reported Watts are
therefore an upper bound among ASAP7's corners, and the comparison in
§4.4 against a typical-corner 22 nm series is biased against this
study's points on that account.

Because all three cores are measured at the same corner, the
*comparison between them* is unaffected. Only the absolute number and
the cross-series comparison are.

### 5.5 Frequency, and what deriving it changed

§3.8 says what a CPU core's frequency *is* — the reciprocal of its
longest register-to-register path, with everything touching a port an
optimisation target rather than a closure condition, and that the number
comes from the platform's `reg2reg` path group rather than from the
overall WNS. This section is about the other half: which period was
actually used. Until §8.3's `auto_period` existed, the answer was "one
somebody picked", and this section was a threat. It is now a result.

**Each core's period is derived, and three of the four were wrong.**

| core | was | derived | error |
|---|---|---|---|
| SERV | 700 ps (1429 MHz) | **438 ps (2283 MHz)** | 60 % too slow |
| picorv32 | 1000 ps (1000 MHz) | **467 ps (2141 MHz)** | 114 % too slow |
| ibex | 1200 ps (833 MHz) | **1282 ps (780 MHz)** | 6.4 % **too fast** |
| VeeR EH1 | 1600 ps (625 MHz) | **1591 ps (628.5 MHz)** | 0.6 % too slow |

**Table 7.** Committed against derived periods. The derivation is
`//test/coremark_joule/scripts:auto_period`; each core's walk is in its
`auto_period.json`.

**ibex was the serious one.** Its committed 1200 ps was not a
conservative guess but an unmet one: the netlist missed it by 73.99 ps
on all eight reg2reg paths, and the study reported 833.333 MHz anyway.
By this section's own rule — deeply negative means repair gave up — the
best-scoring core in the study was being scored at a frequency it does
not reach. It closes at 1282 ps with 0.50 ps to spare.

**How it was possible.** The reported frequency was a literal in
`sim/BUILD.bazel` and the period the design was built at was a
`set clk_period` in its `constraints.sdc`: one fact, declared twice, and
nothing compared them. `cm_per_joule` now reads the constraints file, so
`auto_period` pins the period and the reported frequency follows. The
class of defect is gone rather than the instance of it.

**The energy axis barely moved, and that is the result.**

| core | f | power | CoreMark/Joule |
|---|---|---|---|
| SERV | +60 % | +54 % | **+3.5 %** |
| picorv32 | +114 % | +107 % | **+3.2 %** |
| ibex | −6.4 % | −5.3 % | **−1.1 %** |
| VeeR EH1 | +0.6 % | +1.2 % | **−0.6 %** |

**Table 8.** What re-deriving the period did to each point.

picorv32's frequency was wrong by more than a factor of two and its
CoreMark/Joule moved 3.2 %. That is the model this section always
argued, now measured rather than asserted: dynamic energy per iteration
is frequency-independent — power rises with `f` and the iteration takes
proportionally less time — so only the *leakage* term moves, and running
twice as fast halves leakage energy per iteration. The ranking is
unchanged. The energy conclusions are therefore more robust to the
frequency choice than this study was previously entitled to claim, and
that robustness is now a measurement rather than an argument.

**What a derived period is not.** It is the tightest period the flow
closed at, on one floorplan, at one corner, with this optimiser. §8.3
notes that the floorplan is derived at a period and the period achieved
on a floorplan, so the two interact and two passes are wanted; only one
pass has been run. And `period - WNS` from a single reading is *not*
the answer — measurably: VeeR closed at 1591 ps with 10.65 ps of slack,
which predicts 1580 ps, and 1581 ps fails. A slack is what the optimiser
had left over when it stopped trying, not what it could have delivered
if asked for more.

### 5.6 A predictive kit, not a foundry PDK

ASAP7 is a predictive 7 nm process design kit. Its absolute energy is
not a silicon number, and no claim here should be read as one. Relative
comparisons within the study stand.

### 5.7 Attribution does not survive parameterized modules

The per-unit breakdown works today only for designs whose kept modules
are unparameterized, and the failure is silent: the flow completes, the
netlist is valid, and the breakdown comes back empty.
`power_units_grt.tcl` prints the module-instance count for that reason,
and `hier_probe` says at which stage the hierarchy was lost.

SERV is the case that matters. Its kept modules are all parameterized,
so yosys names them `$paramod\serv_alu\W=s32'...`; all thirteen are
present in `1_2_yosys.v`, but the global-route ODB has zero module
instances and the written netlist is one flat module. picorv32's
plainly named `picorv32_pcpi_mul` and `picorv32_pcpi_div` survive
intact, complete with hierarchical paths.

The obvious fix — renaming the kept modules to their design names
during synthesis — is explicitly warned against in
`synth_canonicalize_module.tcl`, which keeps canonical names because
OpenROAD's macro placement and the parent netlist's instance references
use them; renaming in the module partition alone would desync the two.
The established pattern for mangled names is to de-uniquify at the
reporting layer, and that is the right shape here — but it does not
rescue SERV, whose instances are absent rather than mangled. A
consistent rename across the whole merged netlist, definition and
instantiation together, is the candidate fix, and it is untried.

This threat affects §3.7's breakdown only. It does not affect Table 1,
Table 2 or Table 3, which are whole-design numbers.

### 5.8 Where each core's register file ends up

| core | register file in RTL | hardened as |
|---|---|---|
| picorv32 | inline `reg [31:0] cpuregs [0:31]` array | flip-flops |
| SERV | `serv_rf_ram`: array + read register + x0 gating | flip-flops |
| ibex | `ibex_register_file_ff`, flops by construction | flip-flops |

None of the three converts to an SRAM macro, and in each case for a
reason in the RTL rather than a flow defect. A memory is converted by
blackboxing a module so the liberty view replaces its body, which needs
a module that is nothing but the memory. picorv32's is an inline array;
SERV's module carries the read register and the x0 gating besides;
ibex's is flops by design.

SERV is the one that matters. Keeping the register file in SRAM is its
whole architectural trick, and measuring it as flip-flops understates
it. Getting the macro would mean splitting the array out into its own
module — a patch on SERV's RTL, and so a change to the design being
measured. That is a decision to take deliberately rather than by
default, and it is recorded here rather than made quietly.

Where a core's register file *is* a module, `AUTO_MEMORIES=1` maps it
onto a generated SRAM view and `memories_applied_test` asserts the
macro reaches the netlist, because a generated-then-ignored macro is a
silent wrong answer rather than a failure. The generated views come
from a synthetic memory compiler, so wherever conversion does apply, a
memory's contribution to CoreMark/Joule is a model rather than silicon.

### 5.9 The compiler flag sweep is not wired up

Every point is baseline flags. CoreMark scores are sensitive to
compiler flags, and comparing cores at different flag settings would
not be a comparison of cores.

### 5.10 The IO budget, and what the platform default cost

Found while wiring VeeR, and it applied backwards to Table 1. Both the
SDCs and the numbers are now fixed; this records what it was worth.

`$PLATFORM_DIR/constraints.sdc` on ASAP7 constrains every
input-to-register, register-to-output and input-to-output path with
`set_max_delay`, and **defaults each to 80 ps** when the design does not
override it — a figure its own comment describes as right for "a small
macro on ASAP7". The study's `constraints.sdc` for picorv32, SERV and
ibex sets only the clock period, so all three inherit that default. At a
1000 ps period it is a twelve-fold over-constraint on every path that
touches a port.

This is not a convergence detail; it lands in the number. An optimiser
given an impossible target does not give up quietly — it upsizes cells
and inserts buffers trying to reach it, and those cells draw power that
is then attributed to the core. The three cores have modest port counts
(a simple memory bus), so the effect is smaller than it would be on a
design with hundreds of ports, but it is not known to be zero and it has
not been measured.

**All four designs now set the budget** — `in2reg_max` and
`reg2out_max` at 0.8 of the period, `in2out_max` at 0.6, ORFS's own
ratios — and the three measured cores have been re-run. What the default
was worth:

| core | P at 80 ps | P budgeted | delta | CoreMark/Joule |
|---|---|---|---|---|
| SERV | 6.640 mW | 6.680 mW | **+0.6 %** | 5,222 → 5,190 |
| picorv32 | 6.580 mW | 6.430 mW | **−2.3 %** | 84,063 → 86,024 |
| ibex | 7.770 mW | 7.370 mW | **−5.1 %** | 263,224 → 277,510 |

**These four columns are a historical pair, measured before §5.1 at the
core-only boundary**, and they are left as they were taken rather than
restated against the current numbers. The quantity the experiment
isolates is the delta, and re-running it against tiles whose power is
58--71 % memory would measure a smaller relative effect for a reason
that has nothing to do with the IO budget. The absolute CoreMark/Joule
figures in the last column are superseded by Table 1.

CoreMark/MHz is unchanged in every case, as it must be: it is a cycle
count and knows nothing about timing constraints.

**The error scales with the port count**, which is what the mechanism
predicts. SERV's interface is one bit wide and it barely moved — and
moved the wrong way, which is a reminder that removing an over-constraint
frees the optimiser to spend its effort elsewhere rather than simply
spending less. picorv32 has a 32-bit bus; ibex has the widest interface
of the three and lost the most. That it is differential is the part that
mattered: it was distorting the comparison between cores, not only the
absolute figures.

`check_sdc.py` now makes this a checked property rather than a comment:
every design SDC must state all three budgets and must use neither
`set_input_delay` nor `set_output_delay`. It is a non-manual test,
because what it guards is silent in every report downstream of it.

This is a measurement of an error that **every ORFS design inheriting
the 80 ps default carries**, taken on three designs at once. Its size on
a design with many more ports — VeeR has some six hundred — is not
measured here, but the trend across these three does not suggest it is
smaller.

Two sub-findings worth separating out, because they are reasons the
override matters rather than consequences of it:

- `set_max_delay` rather than `set_input_delay`/`set_output_delay` is the
  platform's deliberate choice, and its argument is good: the time given
  to `set_input_delay` is relative to the clock insertion point, so it
  cannot be written down without assuming a clock tree that does not
  exist yet.
- Because `set_input_delay` is not used, **no hold cells are inserted on
  IO paths**. On a design with VeeR's port count that is a large amount
  of area and leakage that would otherwise be charged to the core.

### 5.11 VeeR's clock gates, and what mapping them cost

This section reported a defect until the measurement in it was taken
again. It is kept because the before and after are both results.

VeeR builds its clock gating in RTL. `beh_lib.sv` defines
`` `TEC_RV_ICG `` as a transparent-low latch and an AND —

```systemverilog
always @(CP, enable) if (!CP) en_ff = enable;
assign Q = CP & en_ff;
```

— and `rvclkhdr`/`rvoclkhdr` instantiate it. The macro names the
definition and the instantiation together, so the module cannot be
redirected from outside the sources: whatever name `` `TEC_RV_ICG ``
carries, `beh_lib.sv` defines it. (`PHYSICAL` is not the obstacle. It
guards `rvdffe`'s generate block, not the gate definition, and an
earlier version of this section said otherwise.)

Left alone, VeeR's global-route netlist contained **952 latch cells**
(`DLLx1` ×951, `DLLx2` ×1) and **zero ICG cells**, though ASAP7 ships
ten of them. **It showed up first as timing, not as energy.**
`flow/period_probe.tcl` returned eight reg2reg paths all with slack
exactly 0.000000, every one ending at a latch D pin inside a clock gate
(`...lsu_freeze_c2dc1_cgc.clkhdr.en_ff$_DLATCH_N_/D`). Eight identical
zeros is not repair stopping at non-negative; it is what a latch-
terminated path looks like when time borrowing is unconstrained.

**The substitution has to happen after elaboration and before flatten.**
yosys's `synth -extra-map` is too late — it runs inside the techmap
step, by which point every instance has been inlined — so
`patches/0068` adds `SYNTH_POST_HIERARCHY_SCRIPTS`, a design-supplied
yosys script run immediately after `hierarchy`. It cannot be a plain
techmap file either: the slang frontend elaborates one module per
instance and names each after the instance path
(`\clockhdr$swerv_wrapper.mem.free_cg.rvclkhdr` and ~100 siblings), so
nothing in the design has type `clockhdr` and a bare `techmap -map`
matches nothing while reporting success. `chtype` folds the uniquified
names back onto one first. `flow/cmj_veer_icg.ys` is four lines and
`flow/cmj_veer_icg_map.v` maps VeeR's port names (`TE`, `E`, `CP`, `Q`)
onto ASAP7's (`SE`, `ENA`, `CLK`, `GCLK`).

**What it moved.** 1,066 `ICGx1_ASAP7_75t_R` cells, zero latches, and
design area 60,226 → 60,243 um^2 (+0.03 %) — a real clock gate costs
what a latch and an AND cost.

| | before | after |
|---|---|---|
| clock power | 26.80 mW (30.7 %) | 25.20 mW (29.5 %) |
| total power | 87.30 mW | 85.51 mW |
| CoreMark/Joule | 34,349 | 35,072 |
| reg2reg slacks | 8 × 0.000000 ps, latch D pins | 9.68 … 28.96 ps, flop D pin |
| achieved f_max | not measurable | 628.8 MHz |

**Table 6.** VeeR before and after its clock gates were mapped onto the
library's ICG cell, both measured at 1600 ps. The design is no longer
built at that period -- §5.5 derives 1591 ps -- so these two columns are
a like-for-like comparison of the change, not the study's current
numbers. Table 1 has those.

The energy effect is the 2.1 % the earlier version of this section
predicted it would be: §4.7 puts 59 % of VeeR's power in the macros, and
the clock group is dominated by the tree driving thirty thousand flops
and twenty-eight SRAM macros rather than by a thousand gating cells. The
§4.6 conclusion rests on the macro column and does not move.

**The timing effect is the one that mattered.** Eight distinct slacks
ending on a flop (`swerv.ifu.bp/bht_dataoutf.genblock.dff.dout[5]`
`$_DFF_PN0_/D`) replace eight zeros ending in latches, so VeeR has a
trustworthy achieved period for the first time and §8.3's `auto_period`
is no longer blocked on it.

**Three things it also changed, none of them intended.** A gated clock
is a clock net the tree is built on, so the clock network grew by about
160 pins of the kind §4.2's budget already concedes, pushing VeeR's
unmatched fraction from 0.986 % to 1.0118 % — over its own 1 % budget,
now declared at 1.1 % with that reason written into `pin_policy.json`.
The SAIF filter drops 9,223 clock-network names rather than 5,284, for
the same reason. And §5.12's first workaround retired itself: the
duplicate instance name `write_verilog` produced was on a clock cell
that no longer exists, so `uniquify_netlist.py` now renames nothing.

### 5.12 Two carried workarounds, one of which has retired

VeeR is the first design in the study with hardened macros and a
hierarchical ODB, and getting a number out of it needed two workarounds.
Both are carried here rather than reported upstream, per the moratorium
in `CLAUDE.md`; both cost the measurement something, and what they cost
is measured rather than waved at. The first no longer triggers, and is
kept for what it asserts rather than for what it does.

**A duplicate instance name in the written netlist.** OpenROAD's
`write_verilog` gave two different `AND2x2` clock cells — on
`clknet_leaf_24_clk_i` and `clknet_leaf_152_clk_i` — the same name
`_131758_` inside `ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp`. That is one
collision among that module's 88,520 instances and the netlist's
1,027,239 lines, and the result is not valid Verilog. odb's own instance
namespace is unique per block, so the collision is created on the way
out: the name mapping in `write_verilog` is not injective.

**It no longer fires.** Both colliding cells were on the clock network
of a gate that §5.11 replaced, and with real ICG cells the netlist's
237,295 instance names are 237,295 distinct names. `uniquify_netlist.py`
now passes the netlist through byte-identical. That is a weaker result
than a fix — the non-injective mapping is still there, and the next
design with a hierarchical ODB may well meet it — which is why the
script stays in the chain with its budget of zero, as the check that it
has not come back.

Verilator rejecting it is the good outcome. **A reader that accepted it
would keep one of the two and simulate a design the power was not
reported on** — a plausible number from a netlist that does not exist.
`scripts/uniquify_netlist.py` renames rather than drops, and runs on
every core with a budget of zero, so for the other three it asserts that
their netlists have no collisions. Cost, while it fired: one instance's
pins carried a name the SAIF could not match, so three pins went
unannotated and `pin_policy.json` waived that instance by name. That
waiver is now spent — VeeR's waived count is four, the four tied
top-level ports, and no longer seven.

**Net names a SAIF cannot carry.** OpenSTA's SAIF lexer defines
`ID ([A-Za-z_])([A-Za-z0-9_$\[\]\\.])*` and `HCHAR "."|"/"`, so `/` is
the hierarchy separator and cannot appear inside a name — and an ID
cannot begin with a backslash, so no escaped spelling exists either.
Hierarchical CTS names leaf clock nets after their sink's full path,
which contains odb's own `/`:

    clknet_1_0__leaf_swerv.ifu.bp/BTB_FLOPS[39].btb_bank1_way1...clkhdr.Q

`read_saif` stops at the first such line with a parse error, having
annotated **nothing**. The failure is not a few unannotated pins, it is
the whole measurement — and had it not errored, `report_power` would
have run on default activity and produced a number nothing downstream
could distinguish from a measured one. (The vectorless run reports
59 mW for this design, for scale.)

`scripts/filter_saif.py` drops only the entries the format cannot carry
and classifies every one. On VeeR: **9,223 of 998,067 net entries
(0.92 %)**, every one of them `clknet_*` or `clkbuf_*`. It was 5,284 of
1,002,201 (0.53 %) before §5.11 made the gated clocks real clock nets,
and one of those was
`clonenet_1_swerv.ifu.bp/bht_dataoutf.genblock.clkhdr.clkhdr.Q` — a
cloned clock-gate output, so a clock net named by the resizer's cloning
pass rather than by CTS. There are now no non-clock drops at all, though
the budget of one is kept for that case. §3.5 establishes that this is
the benign case:
OpenSTA gives clock-network pins `2/period` from the SDC exactly,
bypassing the estimator, so being unannotated is their correct state and
the pin audit classifies them `clock_network`. The budget on non-clock
drops is zero by default; VeeR declares one, with that reason.

**Both are properties of the hierarchical flow**, which OpenROAD itself
warns about (`ORD-0012`, "in development"). The study keeps hierarchy
because §3.7's functional-unit attribution needs it, and pays these two
costs to have it. Before either is reported upstream, OpenROAD's own
history should be read first: it has carried fixes in this area before —
name escaping, and the `-hier` flow — so the fix may already exist, and a
bump is cheaper than a report.

---

## 6. Related work

The study this one most directly compares against is *Ramping Up
Open-Source RISC-V Cores* [5], which evaluates CVA6, CVA6S+ and the
XuanTie C910 in GF 22 FDX with PrimeTime on post-layout netlists and a
stated typical corner. Its method is the gold standard this study is
measured against in §5, and §4.4 explains why its points are drawn as a
separate series.

*The Cost of Application-Class Processing* [6] is the reference for the
core + L1 boundary and for silicon-measured energy in the same
technology family.

EEMBC defines both halves of the metric. CoreMark [1] defines the
performance benchmark and its run rules; ULPMark-CoreMark [2] defines
the energy metric as CoreMark iterations per milli-Joule, which is the
same quantity this study reports per Joule. ULPMark-CM is measured on
silicon at a stated supply voltage, which no pre-silicon flow can
claim; the naming here follows it, the certification does not.

The theory of the estimator §3.5 rules out is Najm's [3, 4]: signal
probability and transition density propagated forward through Boolean
functions, cheap and blind to reconvergent-fanout correlation. The
practice §5.2 is missing is the SDF-annotated, event-driven capture
that signoff power flows use [7, 8].

---

## 7. Cores after the first three

The first three establish the low end. The interesting region is 5–15
CoreMark/MHz, and the structural fact that shapes the study is that it
is populated only by large out-of-order cores: the x-axis spans about
three decades and the cost of a point grows with it. So the shape is
earned cheaply at the bottom and *extended* deliberately upward, each
core its own budgeted run.

| # | core | CoreMark/MHz | HDL | practical pain |
|---|---|---|---|---|
| — | SERV / picorv32 / ibex | 0.02 / 0.55 / 2.45 | Verilog / Verilog / SV | done |
| 4 | CV32E40P | ~3.1 | SystemVerilog | low |
| 5 | VeeR EL2 | ~2.6 | SystemVerilog | low |
| 6 | CVA6 | ~2.5 | SystemVerilog | medium — RV64 contrast at similar CoreMark/MHz |
| 7 | **VeeR EH1** | **4.798 measured** (4.94 published [11]) | SystemVerilog | **done — the point that forced §3.1 to be settled (§4.6)** |
| 8 | OpenC910 | ~4.9–7 | Verilog/SV | medium — 3-issue OoO, silicon-proven |
| 9 | SonicBOOM | 6.2 | Chisel | high — pulls in the Scala generator |
| 10 | XiangShan | ~10–15 | Chisel | high — very large |

**Before any of rungs 7–10, close §5.1.** Those cores arrive as tiles
or SoCs, and what gets hardened stops being obvious. Adding a point
above 5 CoreMark/MHz without settling that first produces a number
whose boundary nobody can state afterwards.

**That is now done**, and the warning turned out to understate the case.
Measured against the boundary that had not yet been closed, VeeR's
CoreMark/Joule was **15.2x below** what the three cacheless points
extrapolated to at its performance. Closing it moved the three by
2.8x to 4.2x and left a residual disagreement of 5.65x (§4.6). A study
that had added rung 7 alongside three points that had not hardened
their memories, without saying so, would have reported a number off by
an order of magnitude and had no way to know — and rungs 8–10 would
have inherited the error, because every one of them arrives with an L1
that the small cores were being compared against without one.

**VeeR EH1 is the next one to do.** It is the first rung genuinely
inside the 5 CoreMark/MHz band and it is SystemVerilog rather than
Chisel. ORFS carries it on ASAP7 as `swerv_wrapper`, and there are two
different things to take from that, which have to be kept apart.

**What is worth taking from ORFS's design, and what is not.** The
useful half is everything that is not RTL. ORFS's
`ADDITIONAL_LEFS`/`ADDITIONAL_LIBS` harden the ICCM/DCCM and
instruction-cache arrays as macros — `fakeram7_2048x39`,
`fakeram7_256x34`, `fakeram7_64x21` — with LEF and Liberty views
checked in; the design is therefore an existence proof that this core
can be hardened at the boundary §3.1 asks for, and the views, the SDC,
`io.tcl` and the utilisation are a working starting point. Its
`SYNTH_KEEP_MODULES` is also, already, the enumeration §3.7 asks for:
`ifu_ifc_ctl`, `ifu_aln_ctl`, `ifu_bp_ctl`, `ifu_mem_ctl` (fetch),
`dec_decode_ctl`, `dec_ib_ctl`, `dec_tlu_ctl` (decode and control),
`dec_gpr_ctl_*` (register file), `exu`, `exu_alu_ctl`, `exu_div_ctl`
(execute), `lsu_dccm_ctl`, `lsu_dccm_mem`, `lsu_bus_buffer`,
`lsu_stbuf`, `lsu_lsc_ctl` (load/store), `pic_ctrl`, and the two
instruction-cache tag and data modules. A `units.json` for it is a
mapping exercise rather than a research one.

**The RTL is not usable for this study, and the reason is specific.**
ORFS vendors the core as a single 6.3 MB file,
`flow/designs/src/swerv/swerv_wrapper.sv2v.v`. Its own README records
what it is: SweRV EH1 1.1, cloned from
`westerndigitalcorporation/swerv_eh1` at commit `3ef7e65f`, with "the
default configuration from Repository" applied. Three consequences
follow, and they compound:

- It is a **mechanical sv2v translation** of SystemVerilog into
  Verilog-2005, flattened into one file. Whether it still simulates,
  and whether it simulates as the original does, is not established by
  anything in the repository. Nothing in this study's chain would
  notice a translation artefact that changes behaviour without
  breaking synthesis — except the CRC gate, which is exactly why that
  gate exists, but a core that fails it tells us nothing about VeeR.
- **The configuration is baked in and unrecorded.** VeeR's ICCM, DCCM,
  instruction-cache and branch-predictor sizes come from a generator
  (`configs/swerv.config`) whose output is a defines header. That step
  happened once, before the sv2v pass, and the chosen settings are not
  in the repository. "The default configuration" is not a statement
  anyone can check, and the L1 sizes are precisely what §3.1 makes
  load-bearing.
- It is the **pre-CHIPS-Alliance snapshot**. Upstream is now
  `chipsalliance/Cores-VeeR-EH1`, five minor releases further on.

So EH1 is wired the way every other core in this study is wired: from
its own upstream repository, at a pinned commit, through the module
graph — not from a vendored, pre-converted copy. The configuration is
generated once from upstream's own generator and **committed** as a
defines header with its provenance, for the same reason `rtl/cmj_*.v`
exists: the core that is simulated and the core that is hardened must
not be able to differ, and a reader must be able to see which
configuration was measured. (Upstream's generator is Perl, which is why
its output is committed rather than run in the build.)

**Its CoreMark/MHz is 4.94, and upstream says on what.** The figure
comes from Western Digital's own `docs/SweRV_CoreMark_Benchmarking.pdf`
[11], and the configuration it was measured on is not one of the
generator's target presets:

    swerv -set reset_vec=0xf0090000 -set=iccm_enable=1
          -unset=icache_enable
          -iccm_region=0xf -iccm_offset=0x90000 -iccm_size=64
          -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64
          -btb_size=512 -bht_size=2048

64 kB ICCM holding the code, 64 kB DCCM holding the data, the
instruction cache **off**, and a 512-entry BTB with a 2048-entry BHT.
A default-target build has a 32-entry BTB and a 128-entry BHT — a
sixteenth of each — so a number taken on the default branch predictor
would not be comparable with the published one at all.

**This study keeps their branch predictor and swaps their ICCM for the
instruction cache**, and the reason is the gate-level run rather than a
preference:

    swerv -set=icache_enable=1 -icache_size=16 -unset=iccm_enable
          -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64
          -btb_size=512 -bht_size=2048
          -ahb_lite -set=fpga_optimize=0

- **The ICCM cannot be filled by the core.** `lsu_addrcheck.sv` uses the
  ICCM region only to suppress side-effects; there is no store path from
  the LSU into it. Upstream's testbench fills it by forcing values
  straight into `ram_core` down a hierarchical path, and their FPGA flow
  does it over JTAG with extended OpenOCD abstract commands. Neither
  survives to a gate-level netlist, where the ICCM is a hardened macro
  with no `ram_core` to force — and the gate-level run is the one that
  produces the SAIF. Filling it properly would mean a DMA master pushing
  the image in over the AHB slave port before the benchmark starts: real
  machinery, outside the boundary, existing only to work around the load
  path.
- **The icache needs no loader.** The program sits in external memory
  and is fetched through the cache, so the same image boots in RTL and
  at gate level with nothing forced.
- **It is the cache this study says it measures.** §3.1's boundary is
  the core and its L1; with the cache on, the L1 is exercised rather
  than configured away, and the hot loop runs entirely inside the
  hardened block — instructions from the icache, data and stack from the
  DCCM.

What that leaves outside the boundary is the residual miss traffic, and
it is measured rather than assumed: the SoC wrapper counts IFU bus
transactions, so "CoreMark fits in the instruction cache" is a number in
the results rather than a claim in a comment.

The memory shapes that fall out — `ram_256x34` (icache data),
`ram_64x21` (icache tag) and `ram_2048x39` (DCCM) — are exactly the
three fakeram7 views ASAP7 already carries. A 32 kB icache would need
`ram_512x34` and `ram_128x21`, which it does not.

Two further departures from Western Digital's setup, both deliberate.
`-ahb_lite`, because the external bus here serves only the boot image
and the two-word sim-control device of §3.2, and AHB-Lite is a far
smaller adapter than AXI4 for that. And `fpga_optimize=0`: their number
was taken on a Nexys-4 FPGA prototype at 40 MHz, where the generator's
FPGA setting minimises clock gating — a first-order term in exactly the
energy this study reports.

**Measured here: 4.798 CoreMark/MHz** (208,425 cycles per iteration,
CoreMark's three CRCs correct on the gate of §3.2). Against Western
Digital's own numbers on the same core:

| source | CoreMark/MHz | compiler | instruction memory |
|---|---|---|---|
| Western Digital [11] | 4.94 | GCC 7.2.0 | 64 kB ICCM |
| Western Digital [11] | 4.84 | GCC 8.2.0 | 64 kB ICCM |
| **this study** | **4.798** | GCC 13.2.0 | **16 kB L1 instruction cache** |

Three per cent below their best figure, and below both — in the
direction each difference predicts. Their own GCC 7.2 → 8.2 step cost
2 % on identical hardware, and this build is five major releases further
on again; the remaining gap is the cache paying for the misses an ICCM
does not have. That the three land within 3 % of each other across two
memory systems and three compiler generations is the strongest
end-to-end evidence the harness has produced: the chain measures this
core the way its authors measured it.

The difference between 4.798 and 4.94 is therefore a property of the
memory configuration and the compiler, not evidence about the core.
Both are reported.

**And CoreMark does fit in the L1 — measured, not asserted.** The SoC
wrapper counts transfers on both external buses, and the count is taken
the same way the cycle count is: as the difference between a
two-iteration and a three-iteration run, which cancels the boot, the
`.data` copy and the cold pass that fills the cache.

| counter | during boot | added by one hot iteration |
|---|---|---|
| instruction bus | 2,788 transfers (22.3 kB) | **0** |
| load/store bus | 934 transfers (7.5 kB) | **0** |

Zero, on both buses, over 208,425 cycles. One CoreMark iteration leaves
the hardened block entirely untouched: every fetch is served by the
16 kB instruction cache and every load and store by the 64 kB DCCM. The
2,788 boot transfers are the 24 kB of `.text` streamed in once as cold
misses, and the 934 are the `.rodata`/`.data` copy plus the report's
characters — all of it before the measured window.

This is the first point in the study where §3.1's boundary is not just
intended but **verified**: whatever the SAIF captures over that window,
nothing outside the hardened block was doing anything while it was
captured. The boot traffic is carried in the result rather than
discarded, because zero steady-state traffic and a bus that never
worked at all look identical in a difference.

**That document also puts a number on §5.9's compiler threat.** Western
Digital measured 4.94 with GCC 7.2.0 and **4.84 with GCC 8.2.0** — a
2 % swing from the compiler alone, on identical hardware, in the
direction of the *newer* compiler being worse. This study builds with
GCC 13.2.0, so its VeeR CoreMark/MHz is not expected to reproduce 4.94
exactly, and the difference is not evidence about the core. It is also
a reminder that every CoreMark/MHz in §7's table is a vendor number
taken with a vendor's compiler, which is why they are labelled as
orientation rather than plotted.

**Two slang flags it does not compile without**, both found by running
the frontend on it directly rather than guessed, and both properties of
the RTL rather than of this study:

- `--single-unit`. SystemVerilog makes each file its own compilation
  unit, so a macro defined in one is invisible in the next. VeeR's
  entire configuration is macros — every `RV_*` in
  `common_defines.vh` — and its own `flist.questa` assumes a
  single-unit flow by listing that file first. Without the flag every
  reference to a configuration macro is an "unknown macro or compiler
  directive", and no amount of file ordering helps. **Verilator hides
  this difference by making macros global**, which is exactly why the
  simulator built long before the flow did — a reminder that
  "it simulates" and "it synthesises" are separate claims.
- `--allow-use-before-declare`. VeeR declares signals after the always
  blocks that use them, in `dec.sv` among others. The LRM requires
  declaration first for variables and slang enforces it; yosys's own
  reader and Verilator do not.

Both live in `SYNTH_SLANG_ARGS` in the design's `config.mk`, with the
reason next to them.

Getting to them took the `_deps` reproducer rather than the build log,
and that is worth recording too: ORFS's `synth.sh` routes the frontend's
output through `run_command.py`, and slang's diagnostics — which go to
stderr — do not reach the stage log. The log ends at
`Executing SLANG frontend.` / `ERROR: Compilation failed`, which names
neither the file nor the reason. Running the frontend by hand is what
turned that into twenty lines of exact errors.

What remains to cost, stated rather than discovered later:

- **A bus adapter** to the two-word platform of §3.2 — the same cost
  every core has paid — from VeeR's AXI4/AHB-Lite external bus.
- **A behavioural model for the memory macros**, which §3.2 explains is
  a prerequisite and not a refinement: the macro is blackboxed at
  synthesis so the Liberty view wins, and a blackbox stores nothing, so
  a gate-level CoreMark run fails its CRCs rather than reporting low
  memory power. ORFS ships LEF and Liberty for `fakeram7_*` but no
  Verilog body; bazel-orfs's behavioural-memory flow
  (`tools/memory_macro_scaler/`) is the mechanism, and the six-pin
  fakeram interface is small enough to model directly.
- **`LIB_MODEL = CCS`** in ORFS's design, where the three points in
  Table 1 are NLDM. Either align it or state it; a power number is not
  comparable across delay models without saying so.
- It is the largest design ORFS carries, so a point costs more than the
  minutes the three in Table 1 do.

The same caution applies to the other ORFS designs in this family, and
for the same reason. `asap7/cva6` would be the direct counterpart to
the 22 nm series of §4.4 — the same core at a different node on a
different toolchain — and `asap7/tinyRocket` is a fourth; in each case
what the study can take is the platform-side work, not the vendored
RTL. Rungs 4–8 need no generator toolchain; rungs 9–10 pull in Chisel,
which is the natural place to stop if the study stops early.

---

## 8. Further work

The sections above measure one number at one operating point on one
node. What would turn this from a table into a comparison an architect
or an EDA researcher could cite is set out below, in the order the
existing harness makes cheapest. None of it is started.

### 8.1 Deep physical metrics

Area and f_max are the headline numbers, but a physical designer wants
the underlying architecture's physical health, which those two hide.

- **Congestion and wirelength.** A large out-of-order core often
  suffers badly around the reorder buffer and the register-renaming
  logic, and a core that routes cleanly there is telling you something
  about how its RTL is structured. OpenROAD already produces the
  congestion map; the work is to capture it per core at a comparable
  utilisation and put the images side by side.
- **Standard-cell utilisation limits.** Not the area, but the highest
  utilisation density the router could still close at. A core that
  routes at 75 % against one that fails above 55 % is a crucial
  physical difference that no area number expresses. The harness's
  existing floorplan derivation is the natural place to find it, since
  it already races candidates.
- **SRAM against logic.** High-IPC cores demand large caches, so an
  area or power figure that does not separate them cannot distinguish a
  bloated datapath from a properly provisioned memory. The breakdown
  wanted is logic/datapath, control, and SRAM/macros. §3.7's kept-module
  machinery already attributes power this way; the macros need adding
  to it, which §5.1's boundary work supplies.
- **Dynamic against leakage.** Reported at the target f_max, split
  explicitly. §5.5 explains why this is not cosmetic: dynamic energy
  per iteration is roughly frequency-independent while leakage energy
  per iteration is not, so a single total hides a term that moves with
  the operating point. `report_power` already emits the split; Table 1
  does not yet carry it.

### 8.2 More than one node

A microarchitecture can look excellent on an older node, where wires are
thick and delay is logic-dominated, and come apart on a FinFET node
where wire resistance dominates timing. One node proves nothing about
the other.

- **ASAP7**, the predictive 7 nm kit this study already uses, is what
  makes a result relevant to a modern commercial architecture — with
  §5.6's caveat that it is predictive rather than a foundry PDK.
- **A 130 nm open node** — sky130 — alongside it, so the design stays
  accessible to academic researchers and to startups using open
  multi-project-wafer shuttles, and so the node sensitivity above is
  visible rather than assumed.

**The 130 nm series stops at 5 CoreMark/MHz, and that is a decision
rather than a gap.** Above that the cores are large enough that a
130 nm implementation costs far more area, wirelength and run time than
the comparison returns. So the plan is both nodes up to and including
5 CoreMark/MHz, and ASAP7 alone above it. Where the two series overlap
is exactly where a node-sensitivity claim can be made, and it is stated
where it ends.

### 8.3 Push every core to its own maximum frequency — done, once

This was the largest hole in the study and it is now closed enough to
report. `//test/coremark_joule/scripts:auto_period` derives each core's
period from its own reg2reg slack, and §5.5 has what that did: three of
the four committed periods were wrong, one of them unmet, and the energy
axis moved by at most 3.5 %.

**How it works, and why it is a job rather than a build.** The clock
period is a *synthesis* input, so every candidate re-runs synthesis and
everything after it. There is no shared checkpoint for candidates to
start from, the way `auto_floorplan_candidate.tcl` starts every
floorplan candidate from one `1_synth.odb` — which is what makes racing
twenty floorplans affordable and racing twenty periods not. So the loop
is imperative: build, read the reg2reg WNS, ask for `period - WNS`,
build again. It stops when the period stops moving or the design stops
closing, and pins the tightest period that *did* close.

It relaxes as well as tightens. A committed period the design does not
meet is not a starting point to walk down from, and ibex's was exactly
that; the loop walks up until the design closes and then tightens.

**Three things it will not tell you.**

The walk is not monotone, and that is the interesting part. SERV closed
at 499 ps with 9.3 ps of slack and then at 490 ps with **33.7 ps** —
more margin at the tighter target, because the optimiser stops trying
when it meets a target and tries harder when it does not. So a single
reading's `period - WNS` is an optimistic estimate rather than an
achievable period, which is why the loop iterates and why it pins a
period it measured rather than one it computed.

The period and the floorplan interact — the floorplan is derived at a
period, the period achieved on a floorplan — and only one pass has been
run: period on the incumbent floorplan. A second pass (floorplan at the
derived period, then period again) is what would settle it, and how far
it moves is worth reporting rather than assuming it converges.

And a derived period is one number from one flow. It is not a Pareto
front, which is §8.4.

### 8.4 The Pareto curve

The single most useful graphic this study does not yet have, and the one
that follows most directly from what it already builds.

Rather than synthesising each core at one target frequency, sweep the
target clock period from something comfortable up to the point of
timing failure, and plot frequency against area — and against power —
with every core on the same axes. `orfs_sweep` already races period
candidates, and §5.5's period-tuning discussion is the same machinery
seen from the other side: what tuning treats as a search, this treats as
the result.

What the curve shows that a point cannot is **the cost of speed**: where
each core enters diminishing returns, the wall at which the tools have
to upsize cells wholesale and burn disproportionate power to buy another
ten megahertz. Two cores with the same headline f_max can sit on very
different curves, and which one is on the better curve is the
architectural question. Plotting this study's cores, VeeR EH1 and a
large out-of-order core such as XiangShan together is what would make
the comparison definitive rather than indicative.

---

## 9. Licensing

CoreMark's sources are byte-unmodified. Everything platform-specific
lives in `sw/port/`, which is the porting surface CoreMark documents —
`core_portme.{c,h}` and `ee_printf.c` all ship upstream as templates
whose platform bodies are `#error` stubs. CoreMark's Acceptable Use
Agreement forbids using the trademark in connection with a modified
copy of the Software.

---

## References

1. EEMBC. *CoreMark — an EEMBC Benchmark.* https://www.eembc.org/coremark/
2. EEMBC. *ULPMark-CoreMark (ULPMark-CM): CoreMark iterations per milli-Joule.* https://www.eembc.org/ulpmark/ulp-cm/
3. F. N. Najm. "A survey of power estimation techniques in VLSI circuits." *IEEE Transactions on VLSI Systems* 2(4):446–455, 1994. doi:10.1109/92.335013
4. F. N. Najm. "Transition density: a new measure of activity in digital circuits." *IEEE Transactions on Computer-Aided Design* 12(2):310–323, 1993.
5. Z. Fu et al. "Ramping Up Open-Source RISC-V Cores: Assessing the Energy Efficiency of Superscalar, Out-of-Order Execution." *ACM International Conference on Computing Frontiers (CF'25)*. arXiv:2505.24363
6. F. Zaruba, L. Benini. "The Cost of Application-Class Processing: Energy and Performance Analysis of a Linux-ready 1.7 GHz 64 bit RISC-V Core in 22 nm FDSOI Technology." *IEEE Transactions on VLSI Systems*, 2019. arXiv:1904.05442
7. "A Gate-Level Power Estimation Approach with a Comprehensive Definition of Thresholds for Classification and Filtering of Inertial Glitch Pulses." *Journal of Low Power Electronics and Applications* 14(3):41, 2024. doi:10.3390/jlpea14030041
8. *Measuring Active Power Using PrimeTime PX: A User Perspective.* SNUG Boston 2010. https://veripool.org/papers/Active_Power_Primetime_PX_SNUGBos10_paper.pdf
9. Parallax Software. *OpenSTA* — `power/Power.cc`, `power/SaifReader.cc`. https://github.com/parallaxsw/OpenSTA
10. "Feature request — extend reporting on pin activities." parallaxsw/OpenSTA issue #162. https://github.com/parallaxsw/OpenSTA/issues/162
11. Western Digital. *CoreMark Benchmarking for SweRV*, 20 November 2019. `docs/SweRV_CoreMark_Benchmarking.pdf` in chipsalliance/Cores-VeeR-EH1.
12. NVIDIA. *DGX H100/H200 System User Guide* — 8 × H100 SXM5, dual Intel Xeon Platinum 8480C, 10.2 kW maximum. https://docs.nvidia.com/dgx/dgxh100-user-guide/
13. NVIDIA. *GB200 NVL72* — 72 × Blackwell, 36 × Grace, ~120 kW rack; GB200 Superchip 2700 W = 2 × 1200 W GPU + ~300 W Grace CPU/IO. https://www.nvidia.com/en-us/data-center/gb200-nvl72/
