---
name: repair-headroom
description: Measure how much of a design's reg2reg period is left on the table after repair_timing, and in which kind of move — useful clock skew, threshold voltage, wires (placement, buffering, reseating) — against the one-flop-loop floors no skew or retiming can pass, with wires as built and at zero wire; zero wire alone is no floor, useful skew passes it, so wire and skew are also measured together. The odb-debug daemon's headroom tools answer for one loaded stage (a block is its abstract); orfs_headroom answers across a parent and its hardened blocks, stitched in OpenSTA, which is the answer for XiangShan-sized designs and needs a machine with memory to match. Also how to find out why repair_timing stopped (grt-stage repair arms with its own stop reasons logged). Use before tuning or blaming repair_timing, before choosing between skew, VT, sizing, a floorplan change or surgery, and when a hierarchical design's period will not come down.
---

## The question

`repair_timing` stops with WNS negative. Is that the best any repair could
do, or is there more on the table, and where? The tools here bound it from
both sides: what a move would win if done perfectly (skew, VT, wire, wire
and skew together), and what no skew or retiming can pass (the one-flop
loop, with wires as built and at zero wire). The next section says which
move each bound stops. Every number is a
**reg2reg period**: the clock period minus the worst register-to-register
slack. IO paths are left out; ORFS SDCs constrain them as optimization
targets, not as the design's period (`macro-constraints`).

## The bounds, and which move each one stops

A reg2reg period is set by its worst path. Each measurement moves one
thing and keeps the rest, so each bounds a different move, in two chains
each above its own floor:

    wires as built:  period >= vt, skew >= floor_retime >= floor_cycles
    wires removed:   period >= floor_wire >= floor_wire_skew >= floor_cycles_nowire

| measure | moves | bounds |
|---|---|---|
| `vt` | the cones' data cells to the fastest VT loaded | what VT swapping can give |
| `skew` | each flop's clock arrival, hold kept | what useful skew can give, wires as they are |
| `floor_retime` | each flop's clock arrival, hold ignored | what retiming can give |
| `floor_cycles` | nothing: the worst loop from a flop back to itself, wires as built | what skew and retiming can never pass |
| `floor_wire` | every wire to near zero, clock arrivals as built | what wire can give at today's arrivals: not a floor |
| `floor_wire_skew` | every wire to near zero, then the arrivals by useful skew | what wire and skew together can give: the logic alone, clocked at its best |
| `floor_cycles_nowire` | nothing: the worst one-flop loop at zero wire | what skew, retiming and wire together can never pass |

**The one-flop loop.** A path that starts at a flop's output and comes
back to the same flop's input within one cycle: a state bit whose next
value depends on itself, `valid <= f(valid, ...)`. Launch and capture are
the same flop on the same clock pin, so shifting its clock arrival moves
both ends at once: useful skew cannot lend the loop time. Retiming moves
registers along paths, but a loop through one register keeps one
register: the loop's whole delay stays in one cycle. A loop through k
flops spreads over k cycles, so it bounds the period at its delay over k;
the one-flop loop is the tightest. `floor_cycles` is the worst one-flop
loop over every flop with the wires as built, `floor_cycles_nowire` the
same with the wires gone, the loop's logic alone.

**What can lower it** is the loop itself getting faster: repair on the
loop's own cells and wires (sizing, a faster VT, shorter wires: the gap
between the two floors), or a change to its logic, in the RTL or by
surgery. A floor far above the target says the loop has to change, not
the clock tree.

**Why zero wire is not a floor.** `floor_wire` times every path at the
clock arrivals as built, so it bounds a path's delay at today's skew
only. Useful skew lends a path time from its neighbours on the same flops
(launch earlier, capture later) and takes the period below it; around any
loop the borrowing sums to zero, which is why only a loop bounds it.
`floor_wire_skew` is the combination: neither wire nor skew can give more
than it does, and it never passes `floor_cycles_nowire`.

**The loop floors are exact, and cheap by a bound.** A flop's loop is
one of the paths into its own data pin, so the flop's endpoint period is
at least its loop. `floor_cycles` visits the endpoints worst first, a loop
search each, and stops at the first endpoint whose period is below the
worst loop found; `visited` and `stop` say how far it went. On XiangShan's
FltRegionModule at grt that is 1,421 of 18,207 endpoints, 4 min 47 s,
where searching every flop took 71 minutes, for the same 762.2 ps
(`issuePipes/is0_valid`). The headroom runs always take the floors exact,
whatever `ends` scopes the moves to. `floor_cycles ends=N` searches the
flops of the N worst endpoints only, without the bound: a lower bound of
the floor, labelled `scope: lower bound`, conclusive only above a target.
On the same block it said 213 ps: the worst loop's flop is not on the
1,000 worst paths.

## Step 1 — make sure repair actually gave up

A design that meets timing measures nothing: repair stops at WNS = 0 and
there is no headroom to find. Repair must have stopped with WNS < 0 at the
stage you measure. The daemon's `headroom` tool lists each flow stage's
ending setup WNS, TNS and violation count from the stage metrics; in a log
the sign is `[WARNING RSZ-0062] Unable to repair all setup violations`.

If the stage closed, tighten the clock (an SDC variant, 10 % at a time)
until repair leaves violations, and measure there. With every VT loaded,
aes-block closed at 405 ps and stalled at 365; riscv32i closed down to
770 ps and stalled at 620.

The opposite case is a design whose SDC asks far less than anyone hopes to
reach, so that nearly every endpoint violates: XiangShan's tile asks
473 ps against a 2,000 ps goal. Its violating count and TNS say nothing;
the period alone says where one path went. Give a **target** (`period` and
`headroom` take `target`, `orfs_headroom` takes `target = 2000`): every
measurement then also counts the reg2reg endpoints at or over it and their
total excess over it, the mass a move has to shift, and that is what to
compare.

## Step 2 — one stage, through the odb-debug daemon

Load the stage (`odb-debug`, `warm-gui`) and ask:

| MCP tool | Answers |
|---|---|
| `period` | the reg2reg period, violating endpoints, TNS |
| `floor_wire` | zero-wire bound: every wire's R and C near zero, clock wires too, at the clock arrivals as built; useful skew can beat it |
| `floor_cycles` | one-flop-loop floor, wires as built: the worst path from a flop back to itself |
| `floor_cycles_nowire` | the same at zero wire: the loop's logic alone |
| `floor_wire_skew` | zero wire, then useful skew on it, hold kept |
| `skew_headroom` | useful skew in timing only, hold kept |
| `floor_retime` | retiming floor: useful skew with hold ignored, and the instances whose flops it moves |
| `vt_headroom` | the data cells of the cones at the fastest VT loaded, and its leakage cost |
| `headroom` | all of them in one table, each with its gain in percent, and how each stage ended |

Each tool undoes its what-if and reports `restored`, the period measured
again: it must equal the start. The scope (`ends`) defaults to every
endpoint; limit it only when a very large design does not answer
otherwise, and say so with the number; the loop floors stay exact (above) (skew needs the flops around the
violations free to move: riscv32i scoped to its 1,000 worst endpoints gave
613.8 ps instead of 562.2).

The daemon holds one ODB. On a hierarchical design that is the parent
with each block as its abstract: the parent's own flops and cells are
measured, a path through a block is a fixed arc. That misses what sits
inside the blocks.

## Step 3 — across the parent and its blocks: `orfs_headroom`

```starlark
load("@bazel-orfs//:openroad.bzl", "orfs_headroom")

orfs_headroom(
    name = "cpu_headroom",
    parent = "cpu",                    # the parent's module name
    parent_stage = ":cpu_grt",
    blocks = {"alu": ":alu_grt", "regfile": ":regfile_grt"},
    target = 2000,                     # optional: count the mass over it
)
```

`bazelisk build //my:cpu_headroom //my:cpu_headroom_nowire` exports each part
at its stage, stitches them in OpenSTA with every block's real cells in
place of its abstract (a block used N times is placed N times), and runs
the same measurements (`tools/odb_debug/headroom.tcl`). `cpu_headroom.json`
has the period, `floor_cycles`, `skew` (its moves split `moved_parent` /
`moved_block`), `floor_retime` and `vt` / `vt_parent_only`, each with
`over_target` / `excess_target` when a target is given;
`cpu_headroom_nowire.json` the
same at zero wire: the period (`floor_wire`), `floor_cycles` (the loop
floor of the logic alone) and `skew` (`floor_wire_skew`). Measure at grt: the blocks' abstracts there carry their
clock trees and the route's parasitics.

On XiangShan this is a whole core in one OpenSTA session: the flat KPI that
does the same load took about ten minutes, its memory not yet recorded.
Run it on the >128 GB machine, under a memory cap (`scale-to-memory`).

## Reading the answer

The study behind this skill (aes-block, riscv32i-mock-sram, uart-blocks
with BLOCKS; ISPD 2026's aes, jpeg and ariane), each at the period where
repair stalled:

- **Repair itself**: running `repair_timing` harder (`-repair_tns 100
  -max_passes 10000`) after the contest's baseline found 0.6–2.3 %. Repeating
  the flow's own grt repair on riscv32i fixed endpoints (752 to 301
  violating) but moved the period 0.5 %.
- **Useful skew** is the big missing move: up to 20 % (0.8 % on ISPD aes, 4–12 % on the rest, jpeg 438.8 to 349.1 ps
  with hold kept), and it lands within about 1 % of the one-flop-loop
  floor. OpenROAD has no useful-skew optimization; the gain needs a clock
  tree that delivers the arrivals, which nobody built here.
- **The one-flop-loop floor** is the hard limit for skew and retiming:
  aes-block has 296 flops on one-flop loops (its round state), so neither
  can pass 347.5 ps there. Yosys retiming (`SYNTH_RETIME_MODULES`, `abc
  -dff`, unverified) made aes-block worse: 406 against 386 ps.
- **Retiming** has something to work with only where `floor_retime` is
  below the period. Moving a register through its logic shifts the same
  path delays a clock arrival does, in whole gates, and the hold it breaks
  can be padded; so it cannot pass the balance skew reaches with hold
  ignored, set by the loops through the registers (their delay per
  register), and the one-flop-loop floor is a floor of that floor. The gap
  between `floor_retime` and `skew` is what hold costs skew and does not
  cost retiming. `top_moved` lists the instances whose flops the balance
  moves most ("instance flops ps"): a retiming tool works inside one
  module, never across a hardened block or a memory, so these are the
  `SYNTH_RETIME_MODULES` candidates, each with its loops inside it or not
  worth trying. A retimed module is not the RTL's state: prove it
  equivalent (sequential equivalence with a negative control, `surgery`),
  or do not ship it.
- **VT** that repair left: riscv32i −4.9 % in the parent's own cells;
  aes-block −6.9 %, all of it inside its sbox blocks. A block is repaired
  against its own SDC; when that SDC asks less than the parent's paths
  need, the block stops early, and the parent's repair cannot reach in.
  Flows that load one VT (ORFS's asap7 default is RVT only) leave all of it.
  `vt_headroom` reports what the swap costs in leakage (before, with it,
  after the undo); weigh the gain against it.
- **Wire**: zero wire is worth 10–24 % (ariane 24 %); what of it any
  placement or buffering could recover is not answered here.
- **Zero wire is a bound at today's clock arrivals, not a floor** (The
  bounds): read the gap from `floor_wire` down to `floor_wire_skew` as
  what skew adds once the wires are gone, and `floor_cycles_nowire` as
  the floor under both.
- **Block abstracts at grt** timed riscv32i's parent 5 % pessimistic
  against the stitched view (668 against 634.9 ps).

## Why repair stopped: grt-stage repair arms

`repair_timing` cannot be rerun in an ad-hoc session on a loaded grt ODB:
its incremental global-route update has no router state there
(`GRT-0228 ... usage=65534`) and OpenROAD may segfault. Rerun the flow's
own grt stage instead, as variants that change only its repair settings:

```starlark
orfs_flow(
    name = "cpu",
    ...,                              # the flow exactly as it is
    sources = {..., "PRE_GLOBAL_ROUTE_TCL": [":rsz_debug.tcl"]},
    stage_arguments = {"grt": {"SETUP_SLACK_MARGIN": "0"}},
    variant = "g_m0",
)
```

with `rsz_debug.tcl` holding `set_debug_level RSZ repair_setup 1`. The
stage log then says, per endpoint, why repair moved on ("No change
possible for endpoint", "stuck after N non-improving passes") and why it
quit ("Exiting due to no TNS progress for two opto cycles").

On riscv32i it visited 469 of 1,083 violating endpoints and quit on the
TNS-progress rule (`SetupLegacyBase::terminateProgress`: after iteration
1,000, every 100 iterations TNS must improve by a threshold that starts at
0.01 % of the initial TNS and doubles every 1,000 iterations; two misses in
a row end the repair). No ORFS variable reaches it. 316 of the 469 ended
"No change possible": one move on one endpoint's worst path does nothing
for a thousand register-file writes on near-identical paths. Margin,
critical-VT-swap and VT-only arms moved the period at most 0.4 %; swapping
the violating cones to SLVT met timing.

## Traps

- **A swapped cell's nets lose their parasitics.** OpenSTA deletes the
  reduced parasitics of every net driving a replaced cell
  (`ConcreteParasitics::loadPinCapacitanceChanged`); such a net times as
  zero wire and flatters the swap. The tools re-estimate (daemon) or
  re-read SPEF (stitched) after swapping and after undoing. Any hand-made
  VT experiment must too: this study's first VT numbers were twice too
  good.
- **A net with no global route gets no parasitics** under
  `estimate_parasitics -global_routing` (`estimateGlobalRouteRC` skips
  it): clearing a moved net's guides makes it free, not re-estimated.
- **The single worst-path search wobbles**: `find_timing_paths
  -group_path_count 1` gave periods 4 ps apart on an unchanged design;
  `period` takes the worst over every endpoint, which repeats exactly.
- **Units**: periods are in the liberty's time unit (ps on asap7, ns on
  gf180 and ihp-sg13g2).
