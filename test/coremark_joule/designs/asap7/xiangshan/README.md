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

Two series. The red one is the top level, the parent with its clock tree,
and it is the KPI. The squares are each hardened block measured alone,
through its odb-debug targets:

| block | stage | minimum period | worst `reg2reg` path |
|---|---|---|---|
| Frontend | cts | 5,017 ps | into `bpu/ubtb.t1_hitTargetSame` |
| MemBlock | place, ideal clock | 4,870 ps | inside `lsq.loadQueue.loadQueueReplay` |
| VecRegionModule | place, ideal clock | 2,364 ps | `issuePipes_3` to `issuePipes_4` exu data |
| Region_1 | place, ideal clock | 2,186 ps | `pipeToFEX0` to the FP convert's round shift mask |

XiangShan's `ClockGate` is mapped onto ASAP7's ICG cell (`xs_icg.ys`).
Frontend is measured with it; the other blocks and the top level in
`kpi.json` are not yet.

The blocks are abstracted at `cts`, and that is a choice with a measured
cost. On Frontend, the `cts` checkpoint's period is 5,017 ps against
3,603 ps after a route-0 global route and its `repair_design` on the same
checkpoint: 28 percent pessimistic, with the same worst paths (the same
worst endpoint, the route's top ten all within the `cts` top seventeen).
Abstracting at `grt` costs a route-0 global route per block. The grt
probe, `Frontend_grt_probe_grt`, measures it; `ideas/xiangshan-timing.md`,
entry 25, has the table.

## Running it

```
bazelisk run //test/coremark_joule/designs/asap7/xiangshan:XSTile_grt gui_grt
```

Needs 64 GB. About six hours cold, a download when the cache is warm.
Earlier stages are their own targets (`XSTile_synth`, `_floorplan`,
`_place`, `_cts`), each with `gui_`, `open_` and `_deps` forms, and
`XSTile_synth_odb_debug` and `XSTile_place_odb_debug` open a checkpoint for
questions.

Not a download although another machine built it? `/cache-miss`:
each machine captures a few kilobytes into `cache_evidence/` and a diff
names the first action whose key differs. Usually it is the commit: every
stage takes the whole patched ORFS tree as input.

## Where the period is

![what needs fixing](xscore_problems.png)

The die to scale, the four hardened blocks, the three generated register
files in the parent's rows, the 1,000 um of bottom edge that carries all
4,311 ports, and the route-0 overflow shaded over the lot. The figure
carries illustration and labels only; the four markers on it are these,
in the order they cost clock period.

1. **One escape band above the macro row.** The blocks fill the bottom
   1,050 um edge to edge and nothing routes through them, so every
   block-to-parent wire escapes through the strip above. 97% of the
   sampled route-0 overflow is in two 90 um bins there. The floorplan
   owes that escape its own channel rather than the leftovers.
2. **4,311 ports on one metre of edge**, behind MemBlock. Nets that
   belong on the far side of the die cross it twice.
3. **A millimetre per block-to-block hop.** MemBlock's output to
   Region_1's input is 1,793 ps on one parent wire, with timing-driven
   placement off and post-CTS repair skipped.
4. **Frontend's own period bounds the top level.** The worst path crosses
   the parent into a Frontend input whose setup is 12,534 ps to a
   falling clock edge: the TAGE SRAM bank's clock-gate enable latch.

The overflow shading was sampled every eighth gcell on M2 through M9 and
binned 24 x 24 over the die. It is a qualitative diagram: the geometry
and the numbers come from the routed ODB through an odb-debug session,
the choice of four and their ranking are a judgement.
`xscore_problems.py` draws it from tables at its top; re-measure with
`.claude/commands/odb-debug.md` and edit them when the baseline moves.

## The next two

1. **Block clock trees are most of a period deep**: 20 to 27 levels,
   477 to 944 ps of insertion delay at 800 ps, so every block boundary
   path is skewed by that much, or padded to match with balancing on
   (`ideas/xiangshan-timing.md`, entry 24).
2. **The block-to-block hop**: 1,793 ps on one wire across a millimetre,
   with timing-driven placement off and post-clock-tree repair skipped.

Each block's own period is no longer on this list: the per block series
in `kpi.json` measures it.

## What is deliberately broken

Global route is skipped past pin access (OpenROAD DRT-0073) and does not
converge; the grt stage fails after the route, because antenna repair on
a platform with no diode cell leaves no route for the parasitics that
follow; the register files are generated rather
than synthesised, because yosys does not finish them at this size; the
configuration is integer-only with a small last-level cache. Eight
carried patches in `patches/` make it run at all.

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

When the period approaches the 800 ps target, `kpi.json` gains the
CoreMark and power columns and the study reconnects to the simulation.
Until then the design does not depend on it.
