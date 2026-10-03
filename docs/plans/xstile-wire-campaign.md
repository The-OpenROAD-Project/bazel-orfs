# Plan: XSTile's period is a macro and global placement problem

Status: **plan, awaiting approval; nothing run.** Parked here because it
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

1. **Harness, on any machine** (no XiangShan run). A measure script that
   writes one JSON row per run with the fields above, a collector that
   skips rows already present (so the campaign resumes after any stop)
   and a plot. Tested on `test/planned_parent`, which builds in minutes.
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

`PLACE_DENSITY` in {0.2, 0.3, 0.4, 0.5, 0.6, 0.7} on A0 and on the best
of A1 to A3; three seeds at the end points and the best density, one
elsewhere. Each point is one place action on a cached floorplan. Three
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

## Budget

A guess until Phase 0 measures one place run; re-budgeted after it.

| phase | runs | wall |
|---|---|---|
| 0 | 3 place, 1 global route | half a day |
| 1 | 5 arms, 1 to 3 seeds, planner work for A2/A3 | 1 to 1.5 days |
| 2 | about 24 place points, 3 global routes | 1.5 to 2 days |

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

## Open decisions

1. A2 and A3 in scope, or A0/A1/A4 only?
2. Densities 0.2 to 0.7 by 0.1, or finer near the top?
3. Which machine, and how many parents at once.
