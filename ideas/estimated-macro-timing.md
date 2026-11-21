# Estimated macro timing for the parent's placement, real timing from CTS on

Status: **in part built.** The views exist, one tier per parent run
(`orfs_flow(macro_view)`, `private/macro_views.bzl`): a ports-only mock,
the synthesis timing model, the abstract, and the report comparing a tier
with the real view per bus. The switch between them at CTS within one
parent flow is not built. An addition to the floorplan planner
(`tools/floorplan`, pull request #1658, not merged yet): the planner
already fixes every input of the parent but one before a block is built,
and this removes the last.

## Problem

A hierarchical flow builds every hardened block to its abstract before
the parent's floorplan can start. The plan gives the parent each block's
outline and pins (the mocked abstract carries them), but the block's
timing, its `.lib`, comes from the block's own flow at its abstract
stage, global route on XiangShan. So the parent's whole flow sits behind
the slowest block: on XSTile about five hours of blocks, then about four
and a half of parent, of which floorplan and placement are three to four
(`test/coremark_joule/designs/asap7/xiangshan/resources.json`).

To the parent's placement a macro's timing is an optimisation target,
not a result. It says how hard timing-driven placement and
placement-stage repair should work on the paths that cross the block's
boundary. What is reported, the period at global route, is measured on
the real blocks either way.

## Idea

Two timing views of each macro, one LEF.

- **Floorplan and placement of the parent read an estimated `.lib`** for
  each macro, made from synthesis: `orfs_timing_models` already writes a
  liberty model per kept module, and the planner's extract already
  records each port bus's boundary timing. These stages then depend on
  the plan and on synthesis only, and run beside the blocks' own flows.
- **From the parent's CTS on, it reads the real `.lib`** of each
  finished block. Clock insertion latency is the reason the switch is
  there and not later: it is signed, per block, hundreds of picoseconds
  (200 to 270 ps to the worst sink of a block on the planner's toy), it
  shifts every crossing path and moves hold the other way, and it does
  not exist before the block's own CTS. A margin on the estimate cannot
  stand in for it. With the real `.lib` from CTS on, the clock tree,
  repair after CTS, hold, global route and the measured period see
  nothing estimated.
- **The LEF does not change at the switch.** Outline and pins come from
  the plan in both views, as they do today, so the switch is another
  liberty file on the same placed database, not another macro.
- **A report at the switch**: for every boundary bus, estimated against
  real arrival and required times. A placement made against an estimate
  that was badly wrong is then seen before hours of CTS and global route
  are spent on it.

Mocks first: with a mock `.lib` and `.lef` per block, made from synthesis
and the plan, the parent's floorplan iterates with no block built, and
the planner's rungs climb in cost before any real block runs
(`tools/floorplan/README.md`, "Mock the blocks, iterate on the top").

Parallelism comes from remote execution: the parent's floorplan and
placement and each block's flow are independent actions, each on a
worker sized for it. The executor's default of one CPU per action is
what makes whole-tile stages grind there today, so each stage asks for
its cores and memory, as `orfs_sharded_sta` takes
`shard_exec_properties` per shard; `resources.json` has the measured
memory per unit and stage and no core count yet. On one workstation
`orfs_schedule` packs what fits: XSTile's block wave (about 96 GB) and
the parent's placement (31 to 47 GB) do not fit in 122 GB side by side.

## Impact

Not measured. Wall time for a tile becomes the longer of "blocks to
their abstract" and "parent to placement", plus the parent's CTS and
global route, instead of the sum: on XSTile the parent's three to four
hours of floorplan and placement stop waiting behind five hours of
blocks. A change inside a block no longer invalidates the parent's
placement, only its CTS and global route.

It does not make the result more accurate: the measurement is the one
made today.

The risk is the placement itself. It was optimised against the estimate,
and where a block's real boundary timing is far off, CTS and global
route repair have to make up a worse placement. An optimistic estimate
leaves crossings under-repaired at placement; a pessimistic one spends
area and power on them. The report at the switch says where; the proof
below says what it costs.

## Effort

Medium.

- An estimated abstract per macro: the plan's LEF and the synthesis
  timing model as its `.lib`.
- A parent flow whose floorplan and placement take the estimated views
  and whose CTS and later stages take the real ones; `orfs_flow` gives
  every stage one set of macros today.
- The report at the switch.
- Execution properties per stage, with a core count beside the memory in
  `resources.json`.
- Proof before use, on the planner's toy (`test/floorplan_toy`, #1658): the
  parent built with real timing throughout against the parent placed on
  estimates and switched at CTS, the two periods at global route
  compared, the tolerance stated in the acceptance test. Then one real
  design, one block before all of them.
