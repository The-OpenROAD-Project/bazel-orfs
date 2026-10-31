# Global placement as coarse place, static tile split and join: one Bazel action per tile

Status: **proposed, not built.** The first step is a measurement: how much of
the place stage's peak memory is gpl's own data. If it is a few GB, tiling gpl
saves little and global route is the stage to split first.

## Problem

Global placement runs as one process that holds the whole design. Measured
peaks (`test/coremark_joule/designs/asap7/xiangshan/resources.json`):

| unit | floorplan | place | grt |
| --- | --- | --- | --- |
| XSTile | 10.5 GB | 47.4 GB | 84.6 GB |
| MemBlock | 10.0 GB | 28.6 GB | 42.2 GB |

XSTile's place stage also takes 225 minutes on one machine, and remote
execution cannot spread that across machines.

The many-body trick is already in gpl and is not where the memory goes. The
density term is ePlace's electrostatic analogy, solved with an FFT on a bin
grid (`src/gpl/src/fft.cpp`). Its bins are about 23 MB at 512x512 and its FFT
grids about 4 MB (`ideas/mlp.md`). The memory goes to:

- the per-object `GCell`/`GNet`/`GPin` records and about 20 per-cell
  `FloatPoint` vectors (`nesterovBase.h:1470-1496`);
- the whole odb;
- OpenSTA and the resizer for timing-driven placement (`timingBase.cpp`);
- a full global route for routability-driven placement
  (`routeBase.cpp:342`).

## Idea

Use the near-field/far-field split of many-body methods, done as domain
decomposition. Netlist coupling does not decay with distance the way charge
does: placement *creates* locality, so the coarse phase has to come first.

1. **Coarse global place** (one action): cluster the netlist to about 10^5
   clusters (TritonPart `par`, or gpl's own clustering) and run flat gpl on
   the clusters. This is the far field. Timing-driven placement can run here,
   on the whole design, while it is small.
2. **Static split** (one action): cut the die into K tiles with a halo of
   bins. For each tile, write a small odb with the tile's own cells, plus every
   outside cell they connect to fixed at its coarse position. Those fixed
   cells are terminals, the terminal propagation of min-cut placement. Each
   tile also gets boundary budgets for timing as `set_max_delay`, as for a
   hardened macro (`macro-constraints` skill).
3. **Local refine** (K actions, remote-executable): run gpl on each tile in
   red/black (checkerboard) rounds, then repeat with the grid shifted by half a
   tile so no cut line becomes permanent. This is the Schwarz alternating
   method. The tiles of one colour are independent of each other.
4. **Join** (one action): write the cell coordinates back into the full odb.
   This needs one full odb load, roughly floorplan-sized, without STA or grt.
   Then the remaining stages run as usual (repair, legalisation).

**Determinism:** fix the tiling, the colour order and the number of rounds,
and keep gpl's threading deterministic per tile. Every action is then a pure
function of its inputs, so the result does not depend on how remote execution
schedules the actions. The result differs from a flat gpl run, which is
acceptable, but it is reproducible and cacheable. Changing one tile's inputs
re-runs only that tile.

Routability fits naturally, because congestion estimates (RUDY) are local.
Timing is the hard part: paths cross tiles, so a tile sees them only through
the budgets the coarse phase leaves.

## Prior art

ePlace, RePlAce, DREAMPlace and Xplace speed up the field solve with FFTs and
GPUs, and stay in one process. Min-cut placement (Capo) is a static split, but
its cuts are made before placement exists, and analytic placers replaced it on
quality. Searches turned up no recent distributed-memory global placer. The
closest work is 1990s partition-based parallel placement, and deterministic
parallel FPGA annealing that lets distant data go stale on purpose (a UBC
thesis). The hierarchical flow bazel-orfs already has, with hardened macros
(`macro-selection`), is the extreme case: cuts along interfaces that are
actually narrow, and fixed for good.

## Impact

Not measured. The intended gains are:

- a place stage's peak memory down to the size of one tile plus the join's
  odb load;
- a place stage's wall time spread across remote executors;
- per-tile caching.

The flow's peak only drops if global route is split the same way, because
grt's peak is above place's in every measured unit.

The quality cost of the cut lines is unknown, and the comparison against flat
gpl is HPWL, and WNS after repair, on the same design.

## Effort

**Large.** The work, in order:

1. **Gate** (small): split XSTile's place peak between gpl data,
   STA/resizer and the global route inside gpl. Stop here if gpl's own share
   is small.
2. **Small trial** (medium): on a toy design of about 10^5 cells, with
   clustering, coarse place, a 2x2 split, refine and join done by hand in a
   dirty lane, compare HPWL and runtime against flat gpl.
3. **Engineering** (large):
   - tile odb extraction and the join;
   - the Bazel rule, with K actions per round and the rounds unrolled
     statically;
   - timing budgets per tile.
4. **Then the same treatment for grt**, which sets the flow's peak.
