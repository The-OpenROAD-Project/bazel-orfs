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
and it is the KPI: **5,143 ps**, at global route with the route's own
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

## The 333 ps goal

XiangShan's published goal for Kunminghu is 3 GHz on an advanced node,
7 nm: a 333 ps cycle. It is a target, not a silicon result. The team's
HPCA'25 tutorial lists Kunminghu as "Advanced-node, 3GHz, 1.5x IPC of
NH" ([slides](https://tutorial.xiangshan.cc/hpca25/slides/20250302-HPCA25-1-Introduction-XiangShan.pdf)),
Hot Chips 2024 reported 7 nm and 3 GHz
([report](https://riscv.org/ecosystem-news/2024/08/xiangshan-high-performance-risc-v-processors-at-hot-chips-2024/)),
and at RISC-V Summit Europe 2025 "KMHv2" was "ready to tape-out" with
SPEC scores estimated at 3 GHz
([keynote](https://riscv-europe.org/summit/2025/media/proceedings/2025-05-14-RISC-V-Summit-Europe-09h30-BAO-slides.pdf),
[poster](https://riscv-europe.org/summit/2025/media/proceedings/2025-05-13-RISC-V-Summit-Europe-P2.1.06-TANG-poster.pdf)).
No measured frequency is published and no corner is stated for the core;
the same keynote quotes XiangShan's NoC at "7nm_SS". The previous
generation came close to its goal: Nanhu targeted 2 GHz on 14 nm, its
GDSII was delivered at 2 GHz, and the keynote lists its second tape-out
at 2.5 GHz. What we build is the V3 head, integer-only with a small
last-level cache.

In fanouts of four, 333 ps is 41.1 FO4 at the published ASAP7 RVT FO4 of
8.1 ps, which the ASAP7 authors call realistic for industrial 7 nm. On
the library this flow times with (RVT at the FF corner, FO4 14.37 ps)
that is 591 ps at global route, and the SDC synthesises at 0.8 of it,
473 ps (`period_fo4_test`). A cycle leaves about 38 FO4 of logic: the
flops on the paths below take 31 ps clock-to-output and 6 to 13 ps setup.

Is the Chisel RTL congruent with that? Read at the source, the worst path
of each block and of the top level is 6 to 30 gate levels, which at about
1.5 FO4 per level (logical effort for fanout-of-four stages) is 9 to 45
FO4. Measured, the same paths are 138 to 430 FO4:

| worst `reg2reg` path | construct in the RTL | gate levels, read | FO4, estimated | FO4, measured |
|---|---|---|---|---|
| Frontend: `mbtb.t1_startPcVec` to a bank's write `setIdx` | 8-bit equality and 16-bit zero detect into a flop enable, one bit fanning out to 4 banks of 4 ways | 6 to 8 | 9 to 12, plus the fanout tree | 430 |
| MemBlock: redirect `robIdx` to `loadQueueReplay` vaddr | 10-bit age compare, pop count, free-slot mux, 7-to-120 decode, write mux into a 120 by 50-bit flop array | about 15 | about 22, plus the array's fanout | 385 |
| CoupledL2: directory state to the L1 hint queue | 8-way hit and one-hot mux, main-pipe control, an arbiter, a queue write | 15 to 20 | 23 to 30 | 196 |
| VecRegionModule: `Vfma` widen flag to its CSA stage | operand muxes, radix-4 Booth encoding, a 27-to-4 carry-save tree | 16 to 20 | 24 to 30 | 172 |
| Region_1: the FMA's fp64 flag to its shift mask | a 107-bit add with carry select, a 110-bit invert and AND-reduce compare | about 20 | about 30 | 138 |
| XSTile: vector issue queue's accept to the decode buffer | a ready chain back through six modules, a priority encode, an adder and an 8-to-1 index mux | 20 to 30 | 30 to 45 | 358, with clock trees |

The measured column is each block alone at its place stage against an
ideal clock, and for XSTile the KPI; the read and estimated columns are
source reading, with files and lines in `ideas/xiangshan-timing.md`,
entry 27.

By logic depth the RTL is congruent with the goal: every one of these
paths fits in 41 FO4, the deepest two, the FMA's wide add and the top
level's ready chain, at the edge of it, and XiangShan's own comments mark
the ready chain as a timing concern. The measured paths are 4 to 45 times
their logic, and the difference is ours to explain, not the RTL's. The
shallowest paths are the furthest off, which points at fanout and
buffering (Frontend's startPc, MemBlock's 120-entry array) before logic,
and at synthesis mapping for area (`ABC_AREA=1`). None of the six runs
through a memory XiangShan builds as SRAM: the replay queue, the write
buffer and the hint queue are flops in its RTL too.

What would make the RTL incongruent is a path whose logic alone exceeds
41 FO4 however it is mapped. None of the six does by reading; the
best-effort mapping of each cone, and the logic-only period of each
block with the wires taken out, are the measurements that would show one.

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
| reg2reg | -4,670 ps | VecRegionModule's `out_toIntRegion_vstdCanAccept_1_0` output into the parent's `ctrlBlock/decodeBufBits` |
| in2reg | -1,562 ps | `io_hartId` into the CSR in the integer ALU |
| reg2out | -866 ps | the L2's `io_chi_syscoreq` out to the tile's port |

Only the first is a period (`.claude/skills/macro-constraints`); the
other two are optimisation targets.

Route-0 at global route: total congestion 37,180, worst edge 31/42, 20.7
percent of the routing resources used. The floorplan is the planner's at
parent density 0.2 and layer adjustment 0.1; `plan/plan.json` is its input.

## The next two

1. **VecRegionModule's store-data accept into the decode buffer**, 4,670
   ps over the period: 1,436 ps of the block's clock-to-output, then
   3,671 ps across the parent, 1,756 of them repeaters and 727 wire, a
   long crossing rather than a missing one. Across the 11 distinct worst
   paths, repeaters are 36 percent of the data delay, logic 33, wire 23
   (`ideas/xiangshan-timing.md`, entry 26).
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
