# CoreMark per Joule at Global Route: Energy Efficiency of Small RISC-V Cores on a Predictive 7 nm Kit

**A measurement study in the bazel-orfs repository.**
Everything in this directory is `tags = ["manual"]`; `test/` is never
shipped, and nothing here is pulled in by a wildcard build.

---

## Abstract

CoreMark/MHz is reported for almost every open-source RISC-V core;
CoreMark/Joule almost never is, because the energy half needs a
hardened netlist, a switching-activity capture, and a power engine, and
each of the three has a way of producing a plausible number that is not
a measurement. We build the whole chain in a reproducible flow —
CoreMark ELF, RTL simulation, CRC gate, synthesis, global route,
gate-level simulation, SAIF over one hot iteration, `report_power` —
and screen at global route so a point costs minutes rather than hours.
We report four cores on ASAP7: SERV (0.0243 CoreMark/MHz), picorv32
(0.5531), ibex (2.4543) and VeeR EH1 (4.7978), spanning more than two
decades of performance.

The study's central methodological contribution is negative and
checkable. OpenSTA does not fail when a pin carries no annotated
switching activity: it estimates one, and the estimate is
indistinguishable from a measurement in the report. We therefore
enumerate every pin, classify every pin the SAIF did not reach, and
bound what the estimator could be worth by sweeping the default
activity across its entire range. For all three cores the SAIF
annotates **100 % of pins** (50,512 / 27,287 / 84,841), **zero** are
unannotated, and the SAIF-driven total is bit-identical at ten
significant figures across the whole sweep, while the same sweep moves
the vectorless total by 64–128 %. The energy numbers are therefore
vector-driven in the strong sense: OpenSTA's probabilistic activity
model contributes nothing to them.

The cores compared span three decades of performance and are
qualitatively different machines, so the comparison is made
apples-to-apples not by the designs but by the definition of what is
measured: the core and its L1 caches, and explicitly not what surrounds
them. Where a core is too small to have caches, the small SRAM that
comes with it and holds the program is what is measured in their place.

The shape those points make is reported with its own diagnosis. The
three cores that harden no memory fall on a straight line in log--log
axes -- slope 0.868, R² = 0.999 -- and that was a defect rather than a
law: across a 101x span in CoreMark/MHz their power spans only 1.15x, so
the multiplier `f/P` predicts a slope of 0.862 on its own. We predicted
the cause was the boundary, and said so falsifiably. VeeR EH1, the one
core here whose L1 is hardened, tests it: the power spread across the
study goes from 1.15x to 13.58x, R² falls from 0.999 to 0.561, and the
line is gone. Extrapolating the cacheless trend to VeeR's performance
overpredicts its energy efficiency by **15.2x**. Hardening an L1 is
worth an order of magnitude, and it was invisible in every point that
lacked one.

We also state, rather than imply, what the numbers do not yet cover:
the intended boundary of core + L1 is not met by these three points,
the simulation is zero-delay and so carries no glitch power, the
parasitics are estimated rather than extracted, the corner is ASAP7's
best case, and the frequency is an SDC target rather than an achieved
maximum. Each is quantified or bounded in §5.

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
| SERV | rv32i | 0.0243 | 41,202,900 | 1428.6 | 6.68 mW | 5,190 |
| picorv32 | rv32im | 0.5531 | 1,807,889 | 1000.0 | 6.43 mW | 86,024 |
| ibex | rv32imc | 2.4543 | 407,448 | 833.3 | 7.37 mW | 277,510 |
| **VeeR EH1** | rv32imc | **4.7978** | 208,431 | 625.0 | **87.30 mW** | **34,348** |

**Table 1.** The four measured points. VeeR EH1 is the only one that
meets §3.1's boundary: its 16 kB instruction cache and 64 kB DCCM are
hardened, and one hot iteration sends zero transfers on either external
bus (§7). The other three harden no memory at all, and §4.6 is about
what that turns out to be worth. Frequency is the SDC period the
SAIF was timed against (§5.5); power is `report_power` at global route
with SAIF-driven activity, at ASAP7's BC corner (§3.6).

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
| 833 MHz (measured) | 3.60 µJ | 277,510 |
| 3.0 GHz (projected) | 46.7 µJ | 21,400 |
| 5.0 GHz (projected) | 130 µJ | 7,700 |

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

The smallest cores have no caches at all. They have a small SRAM that
comes with the core and holds the program the hot loop runs out of, and
**that SRAM is what gets measured**, hardened as part of the core. This
is not an exception granted to the small end; it is the same rule
reaching the same object. In both cases the boundary encloses the core
and the memory it fetches and loads from at the first level, and
excludes everything past it. A cacheless core is not credited with a
free, perfect memory merely because its memory is small enough to be
overlooked.

One rule, applied to every point: **the core, its L1 or the small SRAM
that stands in for one, and nothing beyond.**

The three points in Table 1 predate that rule and do not meet it: they
harden no memory at all. §5.1 quantifies the gap and gives its
direction — which is that the comparison as it stands flatters the
cacheless cores rather than penalising them.

### 3.2 The chain

    ELF → RTL simulation → CRC gate → synthesis → global route
        → netlist → gate-level simulation → SAIF (one hot iteration)
        → report_power

| path | what |
|---|---|
| `sw/port/` | the CoreMark port layer; CoreMark's sources stay byte-unmodified (§9) |
| `sw/` | ELF builds, one per ISA and iteration count |
| `rtl/cmj_<core>.v` | each core's configuration, frozen, shared by the simulator and the flow |
| `rtl/cm_soc_<core>.v` | simulation wrapper: RAM, sim-control device, bus adapter |
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
declare zero. VeeR declares 1 % against a measured **0.986 %**, for a
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

### 4.1 The three cores

Table 1. Across two decades of CoreMark/MHz, CoreMark/Joule spans a
factor of 50: the wider machine is not merely faster per cycle, it is
far cheaper per unit of work. SERV's extreme serialism costs it 41
million cycles per iteration, and the leakage and clock energy of those
cycles is what dominates its Joule.

The reader is cautioned that the three points do not yet meet the
study's own boundary (§5.1), and that the comparison as it stands is
kind to the minimal cores rather than harsh on them.

### 4.2 Annotation completeness and the estimator bound

| core | pins listed | annotated (SAIF) | unannotated | unaccounted | verdict |
|---|---|---|---|---|---|
| picorv32 | 50,512 | 50,512 (100.0000 %) | 0 | 0 | pass |
| SERV | 27,287 | 27,287 (100.0000 %) | 0 | 0 | pass |
| ibex | 84,841 | 84,841 (100.0000 %) | 0 | 0 | pass |
| VeeR EH1 | 758,211 | 750,728 (99.0131 %) | 7,483 | **0.986 %** | pass |

**Table 2.** Pin activity annotation at global route. "Pins listed" is
OpenSTA's own pin set for power — leaf pins plus top-level ports, less
internal and power/ground pins. Every class in §3.5 is empty for the
three cacheless cores: there is nothing to waive.

**VeeR is the exception, and its 7,483 are itemised rather than
tolerated.** Seven are waived by name: four top-level input ports that
`cm_soc_veer.sv` ties to constants, which Verilator therefore never
emits into the SAIF; and the three pins of the one instance
`uniquify_netlist.py` had to rename (§5.11), of which two are on clock
nets and the audit classifies them itself, leaving **one clock-gate
enable pin** as the entire measured cost of that workaround. The
remaining 7,476 — the 0.986 % — are pins OpenSTA's hierarchical network
carries that odb's own instance enumeration does not reach: the same
clock cells whose SAIF entries had to be dropped, for the same reason,
their names containing the hierarchy separator. They were never going
to be annotated; what is conceded is classifying them from the database
rather than from their names, and the intent is to drive the fraction to
zero rather than keep it (§3.5).

| core | SAIF arm spread | vectorless arm spread | vectorless at OpenSTA's default | measured |
|---|---|---|---|---|
| picorv32 | **0.0000 %** | 93.84 % | 15.63 mW | 6.581 mW |
| SERV | **0.0000 %** | 64.52 % | 7.19 mW | 6.641 mW |
| ibex | **0.0000 %** | 128.03 % | 26.27 mW | 7.775 mW |
| VeeR EH1 | **0.0000 %** | 90.40 % | 119.13 mW | 87.281 mW |

**Table 3.** Total power as the default activity seeded into
unannotated roots is swept over 0.0, 0.1, 1.0 and 2.0 toggles per clock
period. The SAIF-driven total is bit-identical at ten significant
figures at every point — for picorv32, 6.581451e-03 W four times. The
vectorless total over the same sweep runs 5.66 → 20.02 mW (picorv32),
5.62 → 11.28 mW (SERV) and 4.52 → 38.59 mW (ibex).

Read together, Tables 2 and 3 are the study's central methodological
claim, and it is a measured one rather than an assurance: **OpenSTA's
probabilistic activity model contributes nothing to the reported
energy.** The knob that would let it contribute is demonstrably live —
it moves the same design's power by 64 to 128 % when activity is not
annotated — and it moves the annotated result by zero.

**VeeR is the case that shows why the sweep, not the audit, is the
claim.** It is the one design with pins unaccounted for — 0.986 % of its
pin set — and its SAIF arm is still bit-identical at 8.728134e-02 W
across the whole sweep, while its vectorless arm runs 78.5 mW to
213.6 mW. The sweep does not care why a pin is unannotated: it varies
the default the estimator would use for every one of them at once. Those
7,483 pins are worth exactly nothing to the reported number, and that is
measured rather than argued.

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

### 4.6 Is the shape real? The boundary, tested

An earlier draft of this section reported a defect and made a
prediction. The defect: the three cacheless cores fell on a straight
line in log--log axes, **slope 0.868 with R² = 0.999**, and that line
was very nearly the x-axis in disguise. Across a 101x span in
CoreMark/MHz their power spanned only **1.15x** (6.43--7.37 mW), so the
whole multiplier `f/P` spanned 1.89x and predicted a slope of 0.862 on
its own. The energy axis was contributing about 0.13 decades of
independent signal over two decades of performance.

The prediction was that §5.1 was the cause -- that with no memory
hardened, what remained was three small blocks of logic clocked within
1.7x of each other, and the part whose cost actually differs between a
bit-serial core and a pipelined one was outside the measurement. It was
stated as falsifiable: *if hardening the memories leaves the slope at
0.85, the degeneracy was not the boundary's fault and something else is
wrong.*

**VeeR EH1 is the test, and the prediction holds.**

| | three cacheless points | with VeeR |
|---|---|---|
| power spread | 1.15x | **13.58x** |
| `f/P` spread | 1.89x | 29.87x |
| log--log slope | 0.868 | 0.535 |
| R² of that fit | **0.999** | **0.561** |

The straight line is gone. It is not that the slope moved -- it is that
a single power law no longer describes the data at all, which is what a
degenerate axis looks like once the thing it was blind to is put back
in.

**How far off the extrapolation was.** Fit the three cacheless points
and extend the line to VeeR's 4.7978 CoreMark/MHz, and it predicts
**521,311 CoreMark/Joule**. VeeR measures **34,348**. The cacheless
trend overpredicts a boundary-compliant core by **15.2x**.

Put as a comparison between two cores rather than against a fit: VeeR
delivers **1.95x** ibex's performance per clock for **0.124x** its
CoreMark/Joule, drawing **11.8x** the power. Hardening an L1 is not a
detail at the edge of the measurement. On this design it is an order of
magnitude, and it was entirely invisible in the three points that did
not have one.

**A corroboration worth noting, carefully.** VeeR at 34,348
CoreMark/Joule lands **1.17x to 1.27x** above the GF 22 FDX series of
§4.4 (27,108--29,412). That is the first point in this study measured at
a stated core-plus-L1 boundary landing near cores measured at what that
paper configures as the same boundary, on a different node with
different tools. It is a coincidence until the caveats of §4.4 are
lifted -- their boundary is unstated and their power is from a different
benchmark -- so it is offered as consistency, not as validation.

**What this does not settle.** The 22 nm series is still flat (slope
0.067, §4.4) and this study's four points are not; whether energy per
unit of work is really constant across microarchitectures, or falls with
performance as these four suggest, needs the other three cores brought
up to the same boundary. That is §5.1, and it is now the single most
valuable outstanding measurement in the study -- no longer because the
numbers are incomplete, but because one point has shown how much the
answer moves.

### 4.7 Where the power goes, and why §4.6 broke the line

`report_power` groups by cell kind, and the grouping turns §4.6's
statistical finding into a mechanical one.

| core | total | Clock | Sequential | Combinational | **Macro** |
|---|---|---|---|---|---|
| SERV | 6.68 mW | 2.85 (42.7 %) | 2.83 (42.4 %) | 1.00 (15.0 %) | **0.00 (0 %)** |
| picorv32 | 6.43 mW | 2.84 (44.2 %) | 2.89 (44.9 %) | 0.70 (10.9 %) | **0.00 (0 %)** |
| ibex | 7.37 mW | 2.46 (33.4 %) | 2.64 (35.8 %) | 2.27 (30.8 %) | **0.00 (0 %)** |
| **VeeR EH1** | **87.30 mW** | 26.80 (30.7 %) | 7.58 (8.7 %) | 2.28 (2.6 %) | **50.70 (58.1 %)** |

**58 % of the only boundary-compliant measurement in the study is the
component the other three do not measure at all.** That is §4.6's answer
stated as a mechanism rather than as a regression: the cacheless points
were not merely missing a term, they were missing the *largest* one.

Three further things fall out of the same table.

**The degeneracy has a cause you can point at.** The three cacheless
cores are not similar by coincidence — their compositions are nearly
identical. Clock power spans 2.46–2.85 mW across all three; sequential
power spans 2.64–2.89 mW. Two components that together are 65–89 % of
each core's total barely move across a 101× span in performance, because
a clock tree and a flop count are set by how much state a design has,
not by how fast it retires work. §4.6's 1.15× power spread is those two
numbers.

**Combinational power is the term that does track the architecture**:
0.70, 1.00, 2.27, 2.28 mW. It is also the smallest term in three of the
four, which is why it could not rescue the y-axis on its own.

**VeeR's logic alone is 36.66 mW** — clock, sequential and combinational
without the macros — against ibex's 7.37 mW, so 5.0× the logic power for
1.95× the performance per clock. The memory is the larger effect, but it
is not the whole of it.

This is the SRAM-against-logic split §8.1 asks for, arriving early
because VeeR is the first design with anything in the macro column.

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
system, a host built from this study's ibex point — 277,510
CoreMark/Joule — would deliver `87.5 × 277,510 ≈ 24 M CoreMark/s`, which
at 2,045 CoreMark per core is some twelve thousand cores. The number is
not a design proposal; what it shows is that the slice is set by `E` and
nothing else, and that a core whose CoreMark/Joule is an order of
magnitude worse buys an order of magnitude less host throughput for the
same rack cost.

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

### 5.1 The boundary is not yet met

The harness RAM is simulation-only: it is never hardened, so every
fetch and load in the benchmark is served by memory that costs zero
area and zero energy. picorv32 and SERV have no caches at all, so their
entire memory system is outside the measurement; ibex is configured
with `ICache=0`, so the same applies.

The gap runs one way, and it is worth being explicit about which. A
design that spends area and energy on an L1 to go faster is charged for
the L1 and credited with the speed. A design with no L1 is charged for
neither and still gets a free, perfect memory. SERV's 41 million cycles
per iteration are 41 million accesses to that free memory; a real
system would pay for them. **The comparison as it stands is kind to the
minimal cores, not harsh on them.**

Closing it is mechanical now that the rule is fixed: harden a program
SRAM with picorv32, SERV and ibex, and turn `ICache=1` on ibex so its
cache is measured rather than configured away. The three points move
down; how far is itself a result, because it is the size of the error
every cacheless CoreMark/Joule figure carries.

VeeR EH1 is the first point that meets the rule, and §7 shows the
boundary verified rather than asserted: over one hot iteration it sends
**zero** transfers on either external bus. That is the standard the
other three have to reach, and it is a measurement they can be held to
rather than a design intention.

**Above about 5 CoreMark/MHz the boundary stops being a caveat and
becomes the measurement**, which is why it had to be settled before the
first core in that range rather than after. Those cores arrive as tiles
or SoCs with L1s, an L2, an interconnect and peripherals attached.
Harden what the repository hands you and the uncore swamps the core's
energy; harden less than the L1 and the misses are served by a free
memory that no longer resembles how it runs. Core plus L1, with the L2
and everything past it excluded, is the line that can be drawn on every
one of them.

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

### 5.5 Frequency is an SDC target, not an achieved maximum

§3.8 says what a CPU core's frequency *is* — the reciprocal of its
longest register-to-register path, with everything touching a port an
optimisation target rather than a closure condition, and it says that
the number is taken from the platform's `reg2reg` path group rather than
from the overall WNS. This section is about the other half: which period
was actually used.

`<design>_period` reports both slacks per design, so the gap between
them — the size of the IO assumption — is visible rather than folded in.
VeeR at 1600 ps closes with a reg2reg worst slack of **0.0 ps** over a
group of matched paths, so its 625 MHz is achieved rather than
understated. That is one design at one period; it says nothing about how
much faster it would go if the period were pushed, which is the job
below.

The frequency each core is scored at is the SDC period the SAIF was
timed against, not `1 / (period - WNS)` at a period pushed until WNS is
slightly negative. Positive WNS means the optimiser met its target and
coasted, so the achieved period understates the core; deeply negative
means repair gave up and the netlist is in a different regime.

The sensitivity is not uniform across the two terms of the number.
Dynamic energy per iteration is roughly frequency-independent — power
rises with `f` and the iteration takes proportionally less time — but
*leakage* energy per iteration falls as `1/f`. A core scored below its
achievable frequency is therefore charged too much leakage energy, and
the error is largest for the core with the most cycles per iteration,
which is SERV. This is a reason to report the leakage and dynamic split
rather than only the total, which Table 1 does not yet do.

Finding the right period is a tuning job, not a build sweep: what is
wanted is a decision, pinned into the design, re-derived when the
design changes — the same shape as the floorplan derivation, run rather
than built. **It cannot ride on `auto_floorplan`**, and the reason is
structural. `auto_floorplan_candidate.tcl` seeds each candidate from
`1_synth.odb` and re-runs floorplan through finish: every candidate
shares one synthesis, which is what makes racing twenty of them
affordable. The clock period is a *synthesis* input — change it and
synthesis and everything after it rebuild — so a period candidate
cannot start where a floorplan candidate starts. The two also interact:
the floorplan is derived at a period, and the period is achieved on a
floorplan. Two passes settle it — period on the incumbent floorplan,
floorplan at that period, period again — and how far the second pass
moves is worth reporting rather than assuming it converged.

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

### 5.11 VeeR's clock gates are latches, not ICG cells

VeeR builds its clock gating in RTL. `beh_lib.sv` defines
`` `TEC_RV_ICG `` as a transparent-low latch and an AND —

```systemverilog
always @(CP, enable) if (!CP) en_ff = enable;
assign Q = CP & en_ff;
```

— and `rvclkhdr`/`rvoclkhdr` instantiate it. Upstream's hook for
replacing it is the `TEC_RV_ICG` define, which their `pd_defines.vh`
points at a technology cell; this study leaves it alone, because
`PHYSICAL` is what would also change the Verilog between simulation and
synthesis (§3.8's frozen-configuration rule).

The consequence is measurable. VeeR's global-route netlist contains
**952 latch cells** (`DLLx1` ×951, `DLLx2` ×1) and **zero ICG cells**,
though ASAP7 ships ten of them (`ICGx1` through `ICGx8DC`). Each gate is
a latch plus an AND where a library cell would do, so the gating costs
roughly twice the cells, on the clock network.

**It shows up first as timing, not as energy.** `flow/period_probe.tcl`
returns eight reg2reg paths all with slack exactly 0.000000, every one
ending at a latch D pin inside a clock gate
(`...lsu_freeze_c2dc1_cgc.clkhdr.en_ff$_DLATCH_N_/D`). Eight identical
zeros is not repair stopping at non-negative; it is what a latch-
terminated path looks like when time borrowing is unconstrained. **So
VeeR has no trustworthy achieved period, and §8.3's `auto_period` cannot
run on it until this is settled.** ibex, for contrast, returns eight
distinct slacks from −9.13 to −4.79 ps.

**As energy it is a smaller effect than it first appeared.** §4.7 puts
58.1 % of VeeR's power in the macros and 30.7 % in the clock group, and
the clock group is dominated by the tree driving thirty thousand flops
and twenty-eight SRAM macros rather than by 952 gating cells. Mapping
them onto `ICGx1` would reduce clock power somewhat; it would not move
the §4.6 conclusion, which rests on the macro column. Recording that
distinction is the point of this section: the finding is real, and it is
a timing blocker rather than a reason to doubt the headline number.

Fixing it needs a wrapper rather than a define, because VeeR's port
names (`TE`, `E`, `CP`, `Q`) do not match ASAP7's
(`SE`, `ENA`, `CLK`, `GCLK`) — the same shape as `macros.v` does for the
memories, and the same shape ORFS's own `swerv_wrapper` uses via
`CLKGATE_MAP_FILE`. It is not done here.

### 5.12 Two carried workarounds, and what each costs the measurement

VeeR is the first design in the study with hardened macros and a
hierarchical ODB, and getting a number out of it needed two workarounds.
Both are carried here rather than reported upstream, per the moratorium
in `CLAUDE.md`; both cost the measurement something, and what they cost
is measured rather than waved at.

**A duplicate instance name in the written netlist.** OpenROAD's
`write_verilog` gave two different `AND2x2` clock cells — on
`clknet_leaf_24_clk_i` and `clknet_leaf_152_clk_i` — the same name
`_131758_` inside `ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp`. That is one
collision among that module's 88,520 instances and the netlist's
1,027,239 lines, and the result is not valid Verilog. odb's own instance
namespace is unique per block, so the collision is created on the way
out: the name mapping in `write_verilog` is not injective.

Verilator rejecting it is the good outcome. **A reader that accepted it
would keep one of the two and simulate a design the power was not
reported on** — a plausible number from a netlist that does not exist.
`scripts/uniquify_netlist.py` renames rather than drops, and runs on
every core with a budget of zero, so for the other three it asserts that
their netlists have no collisions. Cost: one instance's pins carry a name
the SAIF cannot match, so they go unannotated. VeeR's `pin_policy.json`
waives exactly that instance, by name.

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
119 mW for this design, for scale.)

`scripts/filter_saif.py` drops only the entries the format cannot carry
and classifies every one. On VeeR: **5,284 of 1,002,201 net entries
(0.53 %)**, of which 5,283 are `clknet_*` and the remaining one is
`clonenet_1_swerv.ifu.bp/bht_dataoutf.genblock.clkhdr.clkhdr.Q` — a
cloned clock-gate output, so a clock net named by the resizer's cloning
pass rather than by CTS. §3.5 establishes that this is the benign case:
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
| 7 | **VeeR EH1** | **4.798 measured** (4.94 published [11]) | SystemVerilog | **done — and the only point that meets §3.1 (§4.6)** |
| 8 | OpenC910 | ~4.9–7 | Verilog/SV | medium — 3-issue OoO, silicon-proven |
| 9 | SonicBOOM | 6.2 | Chisel | high — pulls in the Scala generator |
| 10 | XiangShan | ~10–15 | Chisel | high — very large |

**Before any of rungs 7–10, close §5.1.** Those cores arrive as tiles
or SoCs, and what gets hardened stops being obvious. Adding a point
above 5 CoreMark/MHz without settling that first produces a number
whose boundary nobody can state afterwards.

That warning was written before rung 7 was measured, and the measurement
has made it sharper rather than redundant. VeeR's CoreMark/Joule is
**15.2x below** what the three cacheless points extrapolate to at its
performance (§4.6). A study that had added it without hardening its L1 —
or added it alongside three points that had not hardened theirs, without
saying so — would have reported a number off by an order of magnitude
and had no way to know.

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

**Measured here: 4.798 CoreMark/MHz** (208,431 cycles per iteration,
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

Zero, on both buses, over 208,431 cycles. One CoreMark iteration leaves
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

### 8.3 Push every core to its own maximum frequency

Every frequency in Table 1 is an SDC period someone picked, not one the
core was pushed to (§5.5), and §2.3 explains why that matters more than
it sounds: the frequency term is the one that has not been exercised, so
the energy axis has not yet been allowed to say anything the performance
axis did not.

The job is a period tuner in the shape of the floorplan derivation —
`auto_period`: run, read `clk_period - WNS`, pin the result into the
design, re-derive when the design changes. §5.5 says why it cannot ride
on `auto_floorplan` (the period is a synthesis input, so a period
candidate cannot start from a shared `1_synth.odb` the way a floorplan
candidate can) and why the two interact enough to need two passes.

Until it exists, every CoreMark/Joule here is taken at a frequency
chosen for convenience, and comparing cores at such frequencies compares
the choices as much as the designs.

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
