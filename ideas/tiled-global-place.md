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

Not measured. The estimate below is a model, with every input stated, so a
measurement can replace one input at a time.

**Model.** Write the place stage as `T_place = T_gpl + T_rest`, with
`f = T_gpl / T_place`. The tiled wall time is
`T_coarse + T_split + 4 * T_wave + T_join`:

- **Coarse place**, at C clusters instead of N cells: about `(C/N) * T_gpl`,
  plus the clustering. At C = 10^5 and N of a few 10^6, that is about 4 % of
  `T_gpl`, plus a few minutes.
- **Waves**: 2 colours times 2 shifted passes, so every tile is refined twice.
  One wave takes about `T_gpl * (1 + h) * g / K`, where:
  - K is the tile count;
  - h is the halo overhead, about 0.25 at K = 16;
  - g is the fraction of flat gpl's Nesterov iterations a tile still needs,
    starting from the coarse placement's low overflow instead of from the
    centre, about 0.4.
- **Split and join**: one full odb read and write each, about 10 minutes
  together on XSTile.

At K = 16, the gpl part comes to about `0.17 * T_gpl` plus 10 minutes. The
total CPU time stays about the same as flat gpl
(`2 * (1 + h) * g = 1.0`), so the gain is wall time and memory, not compute.

**XSTile** (`T_place` = 225 min; f is not measured):

| f | flat gpl | tiled gpl | place stage | stage speedup |
| --- | --- | --- | --- | --- |
| 0.5 | 112 min | 29 min | 141 min | 1.6x |
| 0.7 | 158 min | 37 min | 104 min | 2.2x |
| 0.85 | 191 min | 42 min | 77 min | 2.9x |

gpl itself gets about 4x faster at K = 16. As K grows the coarse phase, the
split and the join become the floor, at about 10x on gpl.

The rest of the place stage limits the stage speedup (Amdahl). Detailed
placement and `repair_design` are local too, so running them inside the same
tile actions would bring the stage close to gpl's own factor.

**Assumptions most likely to be wrong:**

- g: whether refinement from a coarse start really needs only about 40 % of
  flat gpl's iterations;
- f, the gpl share of the place stage;
- timing: rsz cannot run on clusters, so timing-driven placement needs one
  full-netlist STA run at the coarse positions, a serial step not in the
  table.

### Timing- and routability-driven placement, and the whole place stage

Timing-driven and routability-driven placement are the spanner: both read the
whole design. What gpl takes from them, though, is only a scalar per object:

- **Timing-driven** placement runs STA and gives the worst-slack nets a
  weight (`timingBase.cpp`, `resizeWorstSlackNets`).
- **Routability-driven** placement estimates congestion (RUDY, or a full
  global route at `routeBase.cpp:342`) and turns it into an inflation ratio
  per cell.

So the global analysis runs **between rounds**, in one serial action:

1. a full-design STA at the current positions, giving net weights;
2. a congestion map, giving cell inflation ratios.

Its output ships to the tiles as data. A tile needs no STA or global route of
its own, and is still a pure function of its inputs.

The cost: gpl's timing and routability checkpoints, a handful of overflow
levels, become synchronisation points. Fold them into the colour and shift
rounds the tiling has anyway, so they add no extra rounds; then each round
pays one full STA and one congestion map.

Congestion is local, so a tile with a halo could run RUDY itself. The serial
step then shrinks to the STA alone.

The other steps of the place stage split the same way, **fused into one
action per tile** so the stage pays for one split and one join, not one per
step:

| ORFS step | how it is split |
| --- | --- |
| 3_1 global place, IO skipped | becomes the coarse phase (serial, small) |
| 3_2 IO placement | serial, but only the IO nets |
| 3_3 global place | tile rounds, with weights and inflation from the analysis between rounds |
| 3_4 `repair_design` | in the last round's tile action; each net owned by its driver's tile, plus a serial pass for the few nets spanning many tiles |
| 3_5 detailed placement, mirroring | in the last round's tile action, with the halo rows fixed; a shifted pass for the cells at the boundaries |
| `check_placement` | after the join, or per tile |

Happy case on XSTile's place stage (225 min), K = 16, R = 4 rounds:

| step | min |
| --- | --- |
| coarse place + IO placement | 8 |
| split + join | 10 |
| 4 x (STA + congestion map, about 3 min; action start-up, about 1.5 min) | 18 |
| 4 x refine wave (`158 * 1.25 * 0.4 / 16`, about 5 min) | 20 |
| `repair_design` + detailed placement in the tiles (60 / 16) | 4 |
| check | 2 |
| **total** | **about 62 min, 3.6x** |

The floor is coarse place, the join and the four global analyses, about
30 min, so about 7x at K -> infinity. To push past it, make the analysis
between rounds cheaper:

- per-tile RUDY instead of a central congestion map;
- an incremental STA that re-times only the tiles that moved;
- fewer rounds.

### The flow up to grt, repair included, against a GPU

A GPU speeds up gpl alone, so it has to be compared over the whole flow up to
grt, where repair is CPU-bound and serial.

XSTile from floorplan to grt takes 323 min (11 + 225 + 45 + 42,
`resources.json`). How that time splits between gpl, repair and the rest is
**assumed, not measured**:

| bucket | min | what is in it |
| --- | --- | --- |
| gpl | 158 | f = 0.7 of place |
| repair | 102 | `repair_design` at place (40), `repair_timing` at floorplan (5), cts (30) and grt (27) |
| rest | 63 | odb I/O, IO placement, detailed placement, building the clock tree, global route |

How repair tiles:

- **`repair_design`** (slew, capacitance, fanout) is per net. Each net goes to
  the tile that holds its driver, so the pass tiles at close to K, plus action
  start-up.
- **Hold repair** is mostly local, because hold paths are short.
- **Setup `repair_timing`** runs under budgets:
  1. one full-design STA run (serial);
  2. slack handed out to each tile as `set_max_delay` (zero-slack algorithm);
  3. K parallel tile repairs;
  4. a join.

  R rounds, with the boundaries shifted between rounds. The serial steps in
  every round, full STA + join + start-up at about 4 min, make the floor:
  R = 3 rounds in each of cts and grt is about 24 min of serial work, against
  57 min of flat repair. If repair's full update per pass
  (`ideas/mlp.md`) scales with design size, the tile work itself could
  shrink faster than K; that is not measured.

Happy cases, K = 16:

| configuration | gpl | split/join | repair | rest | total | speedup |
| --- | --- | --- | --- | --- | --- | --- |
| flat, CPU (today) | 158 | 0 | 102 | 63 | 323 | 1.0x |
| flat, gpl on GPU (40x) | 4 | 0 | 102 | 63 | 169 | 1.9x |
| flat, GPU + repair fixed on one machine (3x) | 4 | 0 | 34 | 63 | 101 | 3.2x |
| tiled, CPU | 20 | 10 | 35 | 45 | 110 | 2.9x |
| tiled, gpl on GPU per tile | 12 | 10 | 35 | 45 | 102 | 3.2x |

Notes on the table:

- A GPU alone is capped by Amdahl at about 2x, because repair and the rest
  stay serial on the CPU.
- Tiling's own limit is the full-design STA it runs in every round of every
  repair stage.
- In the tiled rows, the rest drops from 63 to 45 because detailed placement
  tiles; global route and building the clock tree do not.
- The "repair fixed on one machine" row is a guess at what a batched,
  cone-local incremental update in `repair_timing` would give; it has not
  been tried.
- Both approaches top out near 3x, against the same floor: global route,
  building the clock tree and full-design odb I/O. Going past that means
  tiling global route too.
- **What separates the two is memory.** The flat runs on a single machine,
  GPU or not, keep their peak. Tiling cuts the peak of every action to one
  tile's share, and grt's peak too once global route is tiled.

The intended gains are:

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
