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
We report three cores on ASAP7: SERV (0.0243 CoreMark/MHz), picorv32
(0.5531) and ibex (2.4543), spanning two decades of performance.

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
| SERV | rv32i | 0.0243 | 41,202,900 | 1428.6 | 6.64 mW | 5,222 |
| picorv32 | rv32im | 0.5531 | 1,807,889 | 1000.0 | 6.58 mW | 84,063 |
| ibex | rv32imc | 2.4543 | 407,448 | 833.3 | 7.77 mW | 263,224 |

**Table 1.** The three measured points. Frequency is the SDC period the
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

The per-design budget and every waiver live in
`designs/asap7/<core>/pin_policy.json`, each with a reason in writing.
All three budgets are zero.

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

| core | pins listed | annotated (SAIF) | unannotated | fatal | verdict |
|---|---|---|---|---|---|
| picorv32 | 50,512 | 50,512 (100.00 %) | 0 | 0 | pass |
| SERV | 27,287 | 27,287 (100.00 %) | 0 | 0 | pass |
| ibex | 84,841 | 84,841 (100.00 %) | 0 | 0 | pass |

**Table 2.** Pin activity annotation at global route. "Pins listed" is
OpenSTA's own pin set for power — leaf pins plus top-level ports, less
internal and power/ground pins; the ODB carries 80,736 / 43,955 /
138,315 pins in total, the difference being the cells' own rails. Every
class in §3.5 is empty for all three cores: there is nothing to waive.

| core | SAIF arm spread | vectorless arm spread | vectorless at OpenSTA's default | measured |
|---|---|---|---|---|
| picorv32 | **0.0000 %** | 93.84 % | 15.63 mW | 6.581 mW |
| SERV | **0.0000 %** | 64.52 % | 7.19 mW | 6.641 mW |
| ibex | **0.0000 %** | 128.03 % | 26.27 mW | 7.775 mW |

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
| 7 | **VeeR EH1** | **4.94** [11] | SystemVerilog | **low — wired from upstream; ORFS's `swerv_wrapper` supplies the macro views, not the RTL** |
| 8 | OpenC910 | ~4.9–7 | Verilog/SV | medium — 3-issue OoO, silicon-proven |
| 9 | SonicBOOM | 6.2 | Chisel | high — pulls in the Scala generator |
| 10 | XiangShan | ~10–15 | Chisel | high — very large |

**Before any of rungs 7–10, close §5.1.** Those cores arrive as tiles
or SoCs, and what gets hardened stops being obvious. Adding a point
above 5 CoreMark/MHz without settling that first produces a number
whose boundary nobody can state afterwards.

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
sixteenth of each — so a number taken on the default would not be
comparable with the published one. This study therefore measures
Western Digital's configuration, which is committed under
`rtl/veer/config` with that command in its header.

It is also the configuration §3.1's rule asks for. A core with no cache
is measured with the small SRAM that comes with it and holds the
program hardened as part of it, and ICCM plus DCCM is exactly that: the
memory the hot loop runs out of, inside the boundary. One memory shape
falls out of it — `ram_2048x39` — which is a fakeram7 view ASAP7
already carries.

Two departures from Western Digital's setup, both deliberate.
`-ahb_lite`, because the external bus here serves only the two-word
sim-control device of §3.2 and AHB-Lite is a far smaller adapter than
AXI4 for that. And `fpga_optimize=0`: their number was taken on a
Nexys-4 FPGA prototype at 40 MHz, where the generator's FPGA setting
minimises clock gating — a first-order term in exactly the energy this
study reports.

**That document also puts a number on §5.9's compiler threat.** Western
Digital measured 4.94 with GCC 7.2.0 and **4.84 with GCC 8.2.0** — a
2 % swing from the compiler alone, on identical hardware, in the
direction of the *newer* compiler being worse. This study builds with
GCC 13.2.0, so its VeeR CoreMark/MHz is not expected to reproduce 4.94
exactly, and the difference is not evidence about the core. It is also
a reminder that every CoreMark/MHz in §7's table is a vendor number
taken with a vendor's compiler, which is why they are labelled as
orientation rather than plotted.

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

### 8.3 The Pareto curve

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
