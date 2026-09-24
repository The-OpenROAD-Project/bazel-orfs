# XiangShan XSCore on asap7

The core of XiangShan's Kunminghu generation, about 4.1 million instances,
as a reference frame: something that reproduces, that anyone can look at,
and that we improve one concern at a time.

Nothing here runs in CI. Every target is `tags = ["manual"]`.

## The KPI

![minimum clock period](kpi.png)

`kpi.json` is the series and `kpi.py` draws it. When a change moves the
number, add a row and re-render.

The number is the SDC period minus the worst slack of the `reg2reg`
group, which is the only group that can fail timing closure. Ask a
checkout for it with `.claude/commands/odb-debug.md`, and read
`.claude/skills/macro-constraints` before quoting any other group.

## Running it

```
bazelisk run //test/coremark_joule/designs/asap7/xiangshan:XSCore_grt gui_grt
```

Needs 64 GB. About six hours cold, a download when the cache is warm.
Earlier stages are their own targets (`XSCore_synth`, `_floorplan`,
`_place`, `_cts`), each with `gui_`, `open_` and `_deps` forms, and
`XSCore_cts_odb_debug` and `XSCore_grt_odb_debug` open a checkpoint for
questions.

## Where the period is

![what needs fixing in XSCore](xscore_problems.png)

A qualitative diagram, generated from the routed ODB through the
odb-debug MCP server: the geometry and the numbers are measured, the
choice of five problems and their ranking are a judgement about what
needs fixing. `xscore_problems.py` draws it; re-measure through
`.claude/commands/odb-debug.md` and edit the tables at the top of that
script when the baseline moves.

## The next three

1. **Abstract each block after its own clock tree.** 43,715 ps of the
   45,985 is the clock reaching MemBlock's pin, whose liberty model says
   145,071 fF because the abstract was written before the block had a
   tree.
2. **The block-to-block hop**: 1,793 ps on one wire across a millimetre,
   with timing-driven placement off and post-clock-tree repair skipped.
3. **Each block's own period**, which no number today describes.

## What is deliberately broken

Global route is skipped past pin access (OpenROAD DRT-0073) and does not
converge; antenna repair is off because it discards the route on a
platform with no antenna cell; the register files are generated rather
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
nobody should be debugging against XSCore when a two-minute case
reproduces the same thing.

## Later

When the period approaches the 800 ps target, `kpi.json` gains the
CoreMark and power columns and the study reconnects to the simulation.
Until then the design does not depend on it.
