> **Repo**: Run from your ORFS workspace root. Examples use bazel-orfs's own XiangShan study (`test/coremark_joule/designs/asap7/xiangshan`), the design this was developed on.

Choose which modules of a large design to harden as macros, and plan the parent floorplan their interfaces dictate, so that the parent's global route converges.

ARGUMENTS: $ARGUMENTS

Hardening by synthesis time picks the modules with the widest interfaces
per side, and the router dies on exactly those sides: on XiangShan, 34
blocks chosen that way put 6.9 pins on every micron of every pin side and
took four takes of global route past their budgets, three of them on
FastRoute's own 100x-capacity edge guard next to a macro's pin side. The
axis that predicts routability is interface width against perimeter, and
a CPU's idiomatic units are where that ratio is small, because the
architecture already drew the narrow cut: the whole frontend is 3.3 k bits
where its five pieces bring 17 k. The skill is the procedure for finding
those cuts in space and in time, and for building the floorplan around
them instead of asking a placer to discover it.

## 1. The space table, before any flow runs

```sh
bazelisk run //tools/macro_select:select_table -- --sv $PWD/bazel-bin/<design>_flat.sv \
    --module Frontend --module MemBlock --children Frontend=Bpu,Ftq,Ifu,ICache,IBuffer \
    --area Bpu=381000 --area Ftq=354000 ...
```

Interface bits per module from the RTL, the square its area makes (from a
synthesised block where one exists), pins per micron of that square's
perimeter, and each parent against the sum of its children. Read it for
the level where the interface drops by a multiple against the children:
that is the cut the architecture drew. Numbers to expect: a well-cut unit
under about 2 pins per micron; a tangled one, the out-of-order core's
issue and control, at 4 to 9, which never becomes a macro.

## 2. The time table, from each candidate's own synthesis

Synthesise each candidate block alone at the target synthesis period
(XiangShan: the planned blocks at 800 ps for a core meant to route at
1000) and open its synthesis ODB through its `odb_debug` target with
timing (`<block>_plan_synth_odb_debug`). Run the probes as they are, no
repair: a block synthesised alone has no fanout phantom (Frontend, 1.5 M
cells: none of its 11 391 worst path ends has a stage past fanout 32,
and `repair_design -pre_placement` moved its WNS by 24 ps in 575 s). The
phantom belongs to a whole-core netlist, where the reset and clock
classes of nets are kept, and `repair_design` on such a netlist does not
return in a day (`ideas/xiangshan-timing.md`, entry 4). Never run a
repair on the whole core; never read whole-core synthesis slacks.

Per block, from `probe_paths.tcl` and `timing_table.py`: the worst path
end and its slack, whether it is a boundary crossing (an input-to-register
or register-to-output path against the SDC's 0.8-period budget) or
internal, its depth in pins, and the module inside that owns it.
`probe_boundaries.tcl` on the parent's hierarchical synthesis adds
whether the boundary pins are registered right inside and the empty
pipeline stages, the retiming idiom.

Read it at 50 % error bars. Thirty years of EDA have not made synthesis
timing predict global route better than that, and this table does not
try: it sorts. A boundary is well formed in time when its crossings are
registered or shallow; a crossing 50 gates deep on an otherwise clean
cut (Frontend's backend-redirect port into the uBTB compare, -492 ps at
800 ps, 1.13 ns of logic) is an entry for the inventory and a note on
the plan, not a reason to move the cut. The period is measured at
global route and nowhere else.

## 3. The plan, from both tables

```sh
bazelisk run //tools/macro_select:plan_floorplan -- $PWD/plan.json --out $PWD/plan_out.json
```

Per macro: pins, area, worst boundary slack. The planner returns the pin
side (never shorter than the pins need at the calibrated pitch, the block
square when they fit, two adjacent sides when the aspect cap cannot hold
them), the channel in front of it (wires that run along it plus a floor
for the cells the parent puts there, buffers and the clock tree), the
parent's logic region at a chosen density, the side assignment that
minimises the die, the die, and each crossing's slack after the wire it
now has to cross. A crossing that goes negative is a wrong cut for this
geometry: move that macro a level down in the table, not the floorplan.
Every block is placed R0 with its pin side chosen in its own frame, so no
flip and no track trouble (see `macro_anneal.flip_legal`).

The four constants the planner cannot derive, pin pitch, pin margin,
channel and picoseconds per micron, come from `test/macro_select`, a
synthetic parent with one pin-wall block routed in tens of seconds per
point (`calibrate.sh`), not from a take of the real design. What the
first calibration on asap7 said (route-0, two pin layers, pin side =
pins x 0.096 um x 1.5 / 2, that is 13.9 pins per micron of the side):
with the logic *facing* the pin side, 1 000 to 10 000 pins across a 10 to
100 um channel never wall, total overflow at most 31 edges; with the
logic *beside* the pin side, every wire turning along the block, 3 000
pins overflow 1e5 with edges over 100 and 6 000 pins overflow 1e6 with
edges in the hundreds, and a 100 um channel is no better than 10 um. The
pin pitch is not the constraint; the fraction of a block's pins whose
logic is in front of them is, and the plan's side assignment is what sets
it. A macro whose pins must talk to two regions is two macros or none.

`--emit DIR` writes what the flows consume: per block `<name>_pins.tcl`
(every signal pin on the planned side), `place_macros.tcl` for the parent
(by master, R0, `-exact`) and `plan.bzl` with the outlines; the design's
`.bzl` reads `PLAN` and builds the planned variant next to the unplanned
one (XiangShan: `xiangshan_flow(plan = PLAN, variant = "plan")`, targets
`XSCore_plan_*`). `keep_under.py` lists the masters under a block in the
boundary probe for the block's own `SYNTH_KEEP_MODULES`.

## 4. Build, with the gates on

Blocks as real flows with the planned outline and pins on the planned
side (one side, at real spacing; mocks only as same-outline turnaround
companions), their own internal partitions and macro banks, each
synthesised at the target period so a block that cannot close alone is
known before the parent is built. Retiming (`SYNTH_RETIME_MODULES`) per
module where the idiom is present, measured per module on its own
synthesis, kept where it pays in period and in time; the list stays
short and named, since ORFS does not verify it.

The parent from the plan. Then the gates, cheapest first, each a hard
stop: the annealer's channel check at floorplan; the free-site picture
and the RUDY map at place (`/odb-debug`); the legaliser's window check;
the zero-iteration global route, total overflow under about 100 k and no
edge in the hundreds, before any maze budget is spent. A wall on a
block's side names the block; dense everywhere names the utilisation.

## 5. The proof and the KPI

The proof is a global route that converges within its iteration budget in
bounded time. The period at global route is the project's KPI from then
on, measured as the study measures it (f from period minus WNS at a
slightly negative WNS), and the timing inventory (`ideas/`) is the
backlog that moves it: each entry a well-studied problem, ranked by the
worst paths it owns, fixed in the tool or articulated in the RTL, and
re-measured on the same floorplan.

## Rules

- Interfaces before areas; tables before flows; calibration on the
  synthetic before a take of the real design.
- Never cut through the tangled core to make blocks build faster.
- The cut follows the architecture; the RTL is not rewritten to invent one.
  The RTL is changed, idiomatically and as carried patches, where a tool
  hole would otherwise cost the flow hours or a generic optimisation
  (a broadcast net, a boundary that wants a register, a generated
  memory's model): solving it in the RTL and the flow scripts is cheaper
  than waiting for a productised algorithm, and usually better QoR.
- The first flow completes global route in hours, one iteration a day,
  before it is asked to pass a period; every stage carries a time budget
  and a stage that breaks it is a finding, not a wait.
- A gate that fails names the stage where the fix belongs; go there.
