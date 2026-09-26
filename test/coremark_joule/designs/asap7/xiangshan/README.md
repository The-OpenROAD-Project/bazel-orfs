# XiangShan XSTile on asap7

The tile of XiangShan's Kunminghu generation, the core and its L2, as a
reference frame: something that reproduces, that anyone can look at,
and that we improve one concern at a time.

Nothing here runs in CI. Every target is `tags = ["manual"]`.

## The KPI

![minimum clock period](kpi.png)

`kpi.json` is the series and `kpi.py` draws it. When a change moves the
number, add a row and re-render.

The number is the SDC period minus the worst slack of the `reg2reg`
group, which is the only group that can fail timing closure. Ask a
checkout for it with `.claude/commands/odb-debug.md`, and read
`.claude/skills/macro-constraints` before quoting any other group. Ask
for the group by name and not for the worst slack: on VecRegionModule the
overall worst slack is -2,006 ps and belongs to another group, while
`reg2reg` is -1,564 ps, and only the second one is a period.

Two series. The red one is the top level, XSTile with its clock tree,
and it is the KPI: **5,543 ps**, at global route with the route's own
parasitics. The squares are each hardened block measured alone at its
place stage against an ideal clock, through `<block>_place_odb_debug`:

| block | minimum period | worst `reg2reg` path |
|---|---|---|
| Frontend | 6,186 ps | `bpu/mbtb.t1_startPcVec` to a main-BTB bank's write-buffer set index |
| MemBlock | 5,527 ps | the redirect's `robIdx` into `loadQueueReplay`'s vaddr |
| CoupledL2 | 2,820 ps | the directory's state into `mainPipe`'s L1 hint queue |
| VecRegionModule | 2,471 ps | `Vfma` widen flag into its CSA stage |
| Region_1 | 1,990 ps | the FMA's fp64 flag into its shift mask |

XiangShan's `ClockGate` is mapped onto ASAP7's ICG cell (`xs_icg.ys`) in
every flow, the parent's and every block's.

The blocks are abstracted at `cts`, and that is a choice with a measured
cost. On Frontend, the `cts` checkpoint's period was 28 percent
pessimistic against a route-0 global route and its `repair_design` on
the same checkpoint, with the same worst paths. Abstracting at `grt`
costs a route-0 global route per block. The grt probe,
`Frontend_grt_probe_grt`, measures it; `ideas/xiangshan-timing.md`,
entry 25, has the table.

## Running it

```
bazelisk run //test/coremark_joule/designs/asap7/xiangshan:XSTile_grt gui_grt
```

Needs 64 GB. About six hours cold, a download when the cache is warm.
Earlier stages are their own targets (`XSTile_synth`, `_floorplan`,
`_place`, `_cts`), each with `gui_`, `open_` and `_deps` forms, and
`XSTile_cts_odb_debug` and `XSTile_grt_odb_debug` open a checkpoint for
questions.

Not a download although another machine built it? `/cache-miss`:
each machine captures a few kilobytes into `cache_evidence/` and a diff
names the first action whose key differs. Usually it is the commit: every
stage takes the whole patched ORFS tree as input.

## Where the period is

The parent's worst paths at global route, by group:

| group | worst slack at 473 ps | path |
|---|---|---|
| reg2reg | -5,070 ps | MemBlock's `intWriteback_0_0_toFpRf_valid` output into the parent's `dispatch/fpBusyTable` |
| in2reg | -1,605 ps | `io_hartId` into the CSR in the integer ALU |
| reg2out | -866 ps | the L2's `io_chi_syscoreq` out to the tile's port |

Only the first is a period (`.claude/skills/macro-constraints`); the
other two are optimisation targets.

Route-0 at global route: total congestion 37,180, worst edge 31/42, 20.7
percent of the routing resources used. The floorplan is the planner's at
parent density 0.2 and layer adjustment 0.1; `plan/plan.json` is its input.

## The next two

1. **MemBlock's write-back valid into the dispatch busy table**, 5,070 ps
   over the period: a block output crossing the parent into a register,
   the path that sets the top level. 1,938 ps of it is one unbuffered net
   from MemBlock's pin to Region_1's, 2.4 mm apart, at a slew of 6 ns.
2. **Block clock trees are a period deep**: 20 to 27 levels, 477 to
   944 ps of insertion delay against a 591 ps target, so every block
   boundary path is skewed by that much, or padded to match with
   balancing on (`ideas/xiangshan-timing.md`, entry 24).

## What is deliberately broken

Global route is skipped past pin access (OpenROAD DRT-0073) and does not
converge: it runs with congestion allowed, and the period is the number
tracked; the register files are generated rather than synthesised,
because yosys does not finish them at this size; the configuration is
integer-only with a small last-level cache. The carried patches in
`patches/` make it run at all.

`ideas/xiangshan-timing.md` has the inventory: 25 entries, each a
measurement and what it implies. That is where a question about this
design is usually already answered.

## The loop

Run the baseline. Find one measured thing wrong. Reproduce that thing in
the battery next door, which runs in seconds to minutes:
`test/structured_netlist`, `test/planned_parent`, `test/macro_select`.
Fix it where it belongs. Re-run, and add a row to `kpi.json`.

A day of this design costs what a minute of the small one does, so
nobody should be debugging against XSTile when a two-minute case
reproduces the same thing.

## Later

When the period approaches the 591 ps target, `kpi.json` gains the
CoreMark and power columns and the study reconnects to the simulation.
Until then the design does not depend on it.
