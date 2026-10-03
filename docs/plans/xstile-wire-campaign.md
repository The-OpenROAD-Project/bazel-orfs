# Plan: XSTile's period is a macro and global placement problem

Status: **approved 2026-10-03; Phase 0's harness is in this pull
request, nothing on XiangShan run.** Parked here because it
needs a machine with more memory than the one that wrote it; any machine
that meets "Where it runs" picks it up from this file.

## The claim

The parent's minimum clock period (3,860 ps, the last row of `kpi.json`;
2,976 ps at global route once its CTS balances the blocks' clock trees,
6b64410d) is set by long wires, and both levers that
shorten them are upstream of routing:

- **Which modules are macros.** A block boundary puts a pin between logic
  and its partners; the planner aims every logic-facing pin at one point
  (`ideas/xiangshan-timing.md`, entry 34). Flattening a block lets global
  placement put its logic next to its partners.
- **Placement density.** The parent runs at `PLACE_DENSITY` 0.2
  (`xiangshan.bzl`, chosen for take 23's routability); a denser placement
  shortens every wire, and density is a global placement knob.

The claim is **supported** if both levers move the parent's period at
place by more than the seed spread while the wire-free floor stays put;
**refuted** if the floor moves with them or dominates (logic depth, not
wire); **not resolved** if the effects are inside the noise.

## The measure, the same in every run

All at the place stage (after 3_5), placement parasitics, ideal clock,
through `XSTile_place_odb_debug` and the method in
`.claude/commands/odb-debug.md`, section 5:

| field | how |
|---|---|
| parent period | SDC period minus `reg2reg` worst slack |
| floor | the same with every wire RC set to 1e-6 (entries 37/38's split) |
| wire share | (period - floor) / period |
| HPWL, worst path wire | `report_wire_length`-style sum; the worst path's total wire |
| design period | max(parent, each remaining block at place); the only comparable number across arms, since flattening moves a block's paths into the parent |
| RUDY congestion | at the end of global placement |
| `3_3` peak RSS, wall time | `/usr/bin/time -v` / the stage log |

No arm needs global route except the three place-versus-route checks;
that keeps every arm off the 119 GB wall entry 34 hit in the parent's
global route.

## Phase 0: harness and baseline

1. **Harness, on any machine** (no XiangShan run). `test/wire_campaign`:
   `wire_probe` (an `orfs_run` of `wire_probe.tcl` on a place stage)
   writes one JSON row with the fields above; `campaign.py add` keeps one
   row per (arm, density, seed) in a committed `results.json`, so the
   campaign resumes on any machine; `campaign.py next` says which density
   to sample next. Proven on `test/planned_parent`, whose parent is placed
   at 0.2 and 0.7 from one floorplan (`wire_d02`, `wire_d07`).
2. **Wiring.** Arms and densities as variants that share the parent's
   synthesis and floorplan (`previous_stage` from `XSTile_floorplan`, or
   `orfs_sweep`); checked with `/cache-miss` that a density point
   rebuilds only `place`.
3. **Baseline (big machine).** Today's five-block parent at place, three
   `GPL_RANDOM_SEED` values: the spread every later comparison must beat.
4. **Place against route (big machine).** On one seed, check the period
   at place still tracks the period at global route on the same build. Entry 38's 2x gap
   (10,855 against 5,402 ps) was kept rebuffer chains that
   `GPL_KEEP_OVERFLOW=0` removed; if the two disagree badly, stop and
   report before Phase 1.

## Phase 1: what the macro boundaries cost

Same die, density 0.2, same flags. Each arm's floorplan is the planner's
from its own block list, in its own `plan_*` directory
(`xiangshan_flow(plan_dir = ...)`).

| arm | hardened blocks | note |
|---|---|---|
| A0 | Frontend, MemBlock, CoupledL2, VecRegionModule, FltRegionModule | today |
| A1 | Frontend, MemBlock, CoupledL2 | regions flattened; built in entry 34, died in global route only |
| A2 | Frontend, CoupledL2 | MemBlock flattened too; needs the planner to place its SRAMs (no netlist mode, MPL-0050) |
| A3 | CoupledL2 | as flat as asap7 allows; stretch |
| A4 | Frontend, MemBlock, CoupledL2, Backend | one cut more; entry 34 has its route (9,038 ps), this adds place |

If A2 or A3 runs out of memory in `3_3`, a partitioned global placement
becomes its own task, and only then.

## Phase 2: density sweep

Adaptive, on A0 and on the best of A1 to A3. Start at the ends, 0.2 and
0.7, three seeds each; then `campaign.py next` names the midpoint of the
interval whose ends differ most, one seed, and so on. An interval whose
ends differ by less than the seeds' spread is not split, and nothing is
split below 0.1: the rough picture, enough to decide what to spend time
on next, not a curve. Each point is one place action on a cached
floorplan. Three
A0 points also get a global route, to check the gain at place survives
contention (`docs/studies/pre-route-pessimism`: placement reads
optimistic when the router is contended).

## Flow settings

The KPI flow's: timing- and routability-driven global placement on,
`GPL_KEEP_OVERFLOW=0`, everything else as `xiangshan.bzl` has it. Only
the arm's block list, `PLACE_DENSITY` and `GPL_RANDOM_SEED` vary.

## Where it runs

- **Not on a 30 GB machine.** The parent's ODB, liberty and STA alone
  are 28 GiB (entry 36).
- **At least 128 GB**, one parent at a time. The parent's place-stage
  peak with timing-driven placement on has never been recorded; Phase 0
  step 3 records it and sets the concurrency (two at a time if a place
  run stays under about 60 GB).
- **256 GB** for A2/A3 with any headroom, or for global-route checks
  beside a place run.

## Running it on the big machine

Phase 0 and the ends of the density sweep on A0 are declared already
(`wire_points` in the xiangshan `BUILD`). From a checkout of this branch:

```sh
X=//test/coremark_joule/designs/asap7/xiangshan
# one point first: it measures the place stage's peak and sets --jobs
bazelisk build --jobs=1 $X:XSTile_wire_d02_s0
# the rest of the ends, two at a time if that peak was under ~60 GB
bazelisk build --jobs=2 $X:XSTile_wire_d02_s1 $X:XSTile_wire_d02_s2 \
  $X:XSTile_wire_d07_s0 $X:XSTile_wire_d07_s1 $X:XSTile_wire_d07_s2
# into the ledger, then the table and the next densities
R=test/coremark_joule/designs/asap7/xiangshan/wire_results.json
for t in d02_s0 d02_s1 d02_s2 d07_s0 d07_s1 d07_s2; do
  d=0.${t:2:1}; s=${t:5}
  bazelisk run //test/wire_campaign:campaign -- add --results $PWD/$R \
    --arm A0 --density $d --seed $s $PWD/bazel-bin/${X#//}/XSTile_wire_$t.json
done
bazelisk run //test/wire_campaign:campaign -- table --results $PWD/$R
bazelisk run //test/wire_campaign:campaign -- next --results $PWD/$R
```

A density `next` names is one more entry in `wire_points`. Commit
`wire_results.json` after every batch: it is the campaign's state, and
the next machine resumes from it.

## Budget

A guess until Phase 0 measures one place run; re-budgeted after it.

| phase | runs | wall |
|---|---|---|
| 0 | 3 place, 1 global route | half a day |
| 1 | 5 arms, 1 to 3 seeds, planner work for A2/A3 | 1 to 1.5 days |
| 2 | 6 per arm at the ends, then 1 per split (about 4 to 6 per arm), 3 global routes | 1 to 1.5 days |

## Deliverables

- An entry in `ideas/xiangshan-timing.md`: arms at fixed density, the
  density sweep with congestion, the place-versus-route check, and the
  verdict the data allows.
- The plot: design period at place against density, one line per arm,
  floor drawn.
- The result JSON rows committed beside the harness, so the tables are
  generated, not typed.
- Phases land as their own pull requests; flow changes an arm needs
  (A2's SRAM placement) land first, on their own. An OpenROAD or ORFS fix
  is carried as a patch here.

## Follow-up, only on a yes: the hub (A5)

Approved 2026-10-03 as a follow-up. It starts only if Phases 1 and 2 support the
claim: flattening (A1 to A3) and density each move the design period at
place by more than the seeds' spread, and the floor stays put. On a no
or a not-resolved it is dropped. Its premise is that the wires are the
problem; it adds nothing if they are not.

**Why.** A yes says the parent wants its partners flat around it. A3,
the flattest arm, buys that by putting most of the core in one top
level, whose global route already passed 119 GB with only the regions
flattened (entry 34). A5 keeps the flatness only where the wires cross:

| | today (A0) | A3, flattest | A5, the hub |
|---|---|---|---|
| hard | Frontend, MemBlock, CoupledL2, VecRegionModule, FltRegionModule | CoupledL2 | Backend, CoupledL2 |
| flat in the top level | CtrlBlock, int Region, issue queues | everything else | Frontend, MemBlock |
| interface crossing a hard boundary | 33,793 block pins (the planner's pin-partner dump) | CoupledL2's | Backend's 7,086 bits, CoupledL2's |

Backend is the narrow cut the architecture drew: 7,086 interface bits
against 42,868 for its four children (entry 34's space table). The
tangled core (issue, rename, the ROB) stays whole inside it and is never
cut, which is the macro selection skill's rule. Frontend and MemBlock,
its partners, are flat around it and can wrap at least three of its
sides: at the skill's 2 pins/um, 7,086 bits need about 3,540 um of pin
edge, about three sides of a 1.1 mm square, more than one or two hard
neighbours could face.

**What it can save, against A3.** The top level loses Backend, the
tangle whose repair and legalisation are the slowest of the parent's
steps, and Backend builds as its own block, in parallel with CoupledL2
and cached while the top level iterates. Whether that is a saving
against today (A0) is not known: the top level gains Frontend's 1.2 to
1.36 M instances and MemBlock's. The A3 and A0 rows of the ledger are
what A5 is compared with, on period, the top level's peak memory and
the build's critical path.

**Gates, cheapest first; each stops the follow-up if it fails:**

1. **Backend's boundary in time.** `probe_boundaries.tcl` on the
   parent's hierarchical synthesis, no flow: the crossings into
   CtrlBlock's decode buffer and store set table, today's worst paths,
   are registered or shallow inside Backend.
2. **Backend alone at place.** Entry 34 measured 9,038 ps there, on the
   rename buffer's enqueue loop, which the flat parent closed in 5,188:
   the loop is not long, the packaging made it long. The levers not
   tried then: pins on the sides that face Frontend and MemBlock, and a
   tight outline at high density, which is Phase 2's lever applied
   inside the hub, so `wire_probe` and the ledger measure it. The gate:
   Backend's own period at place at or below the parent's at place in
   the best Phase 1/2 arm.
3. **The top level.** Frontend and MemBlock flat beside Backend and
   CoupledL2: the design period at place against A3's and A0's, and
   global route under the 115 GB gate. If global placement or global
   route does not fit, this arm is where a partitioned global placement
   earns its place, and that is a task of its own.

**Deliverables.** A plan directory for A5 from the planner (Backend's
pins on the sides facing its partners), its ledger rows beside the
other arms', and a row in entry 34's cut table.

## An idea, not planned: cut at any module boundary, route by abutment

Possibly useful after A5, and only if A5 says yes. Not approved, not
budgeted.

**The cut.** Today a hardened block nests its children: if `a`
contains `b`, `b` is a macro inside `a`'s die and its wires cross `a`.
Instead, lift `b` out: `a′` is `a` with `b`'s instance removed and its
pins promoted to ports, and a wrapper with `a`'s pins instantiates `a′`
and `b` side by side. Give `b` a full-width strip of `a`'s footprint, so
both stay rectangles, and put the `a′`/`b` pins on the shared edge at
the same coordinates and layer: routing by abutment, a crossing with
almost no wire. Size the shared edge to the interface at the macro
selection skill's 2 pins/um.

```
 ┌──────────── a_wrap ───────────┐
 │ ┌────────── a′ ─────────────┐ │
 │ │ a's own logic, ext pins   │ │
 │ │ on N / E / W              │ │
 │ │ ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ │ │  a′/b pins, same x, same layer
 │ ╞═══════ shared edge ═══════╡ │
 │ │ ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ │ │
 │ │ b; a's ports that went    │ │
 │ │ straight to b on its S    │ │
 │ └───────────────────────────┘ │
 └───────────────────────────────┘
```

Applied more than once, the shape that keeps every cut abutted is the
hub: Backend, with Frontend, MemBlock and CoupledL2 on its sides, and
next to nothing left in the top level.

**Tools.** No SystemVerilog source change is needed. The language
has no module-typed parameter; interface ports with modports would
express the cut, but only by rewriting `a`. The cut is a netlist
transform, and OpenROAD has it: `write_partition_verilog` (`par`) writes
a top module with the original ports and one child module per
`partition_id`, a port on both sides of every net that crosses. Tag
`b`'s cells 1 and the rest 0 (`read_partitioning`, or the property
directly); the hierarchy below is written flat, which a macro does not
mind. Alternatives: CIRCT's `ExtractInstances` (FIRRTL), or a najaeda
script on the hierarchical netlist.

**Why it is not first.** At 2,976 ps (entry 41), 972 of the parent's
1,000 worst endpoints start in its own `core/backend` logic; 28 are
crossings. With every crossing's wire at zero the period would not
move. It pays only once a cut like A4 or A5 puts that logic in a block
and the top level is mostly crossings: entry 40's census puts repeaters
and wire at 1,188 and 393 ps per path, which an abutted crossing does
not pay.

**What could cancel it.** Few ports are registered (CoupledL2: 8 of
1,346 inputs), so a crossing still pays both sides' logic and their
`set_max_delay` budgets (`macro-constraints`). Abutted pins are fixed
on both sides, so the placer cannot move them. That OpenROAD connects
pins on a shared edge, a zero halo there, and the power grid continuing
across it, are not checked.

**First step, minutes.** On `test/planned_parent`: split one block out
of its parent with `write_partition_verilog`, check the wrapper is
equivalent to the original with yosys, and place and route the two
halves abutted.

**Prior art.** Abutted-pin hierarchical design, true abutment with no
top-level logic (US 6857116, 6865721, 6757874; EDN's SoC
hierarchical-design glossary); restructuring the logical hierarchy into
a physical one (Hier-RTLMP, arXiv 2304.11761); tiled processors built
from abutted tiles (Raw, OpenPiton, HammerBlade), the easy case of a
regular mesh.

## Decisions (2026-10-03)

1. A2 and A3 are in scope.
2. Density: the ends first, then sample where the uncertainty is
   biggest until the rough picture is in (Phase 2).
3. The harness is built on a small machine now; the XiangShan runs wait
   for a machine with at least 128 GB. Concurrency is set by Phase 0's
   measured peak.
