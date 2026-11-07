# drt: detailed route (TritonRoute) and antenna repair

Paths are in OpenROAD's `src/drt/`, ORFS's `flow/scripts/`.

## Reading the log

Pin access (DRT-165/166, DRT-164 "Number of unique instances"), track
assignment (DRT-181/182), search-and-repair (DRT-194 start, DRT-195
"Start Nth {optimization|guides tiles|stubborn tiles} iteration", DRT-199
number of violations, DRT-198 done).

- **DRT-267 "cpu time, elapsed, memory, peak"** after every phase and
  iteration is the memory track.
- **DRT-199 should fall roughly geometrically through iterations 3-20.**
  A plateau in the hundreds or thousands that only moves when the rip-up
  mode changes means the problem is upstream (guides, pin access,
  congestion), not iterations.
- Below 100 violations the flow switches to "guides tiles" then "stubborn
  tiles", boxes around markers; DRT-200 SKIPPED means nothing changed and
  the last iteration did not help.
- DRT-352 "Input route guides are congested": grt ran with
  `-allow_congestion`; see [grt.md](grt.md).
- DRT-0073 "No access point": see below. DRT-0255 via enclosure outside
  the die: a pin on a die corner (generate_ram, 0170).

## Where the time goes

- Each iteration tiles the die into 7x7-gcell workers in a 2x2
  checkerboard: four sequential phases, batches of up to 1024 workers,
  `omp parallel for schedule(dynamic)` (`dr/FlexDR.cpp`). **Iteration
  time is about four times the slowest worker per batch**: macro edges,
  pin-dense cells and high fanout set the tail. Late iterations mostly
  idle threads.
- Pin access runs per unique instance class (master, orientation, origin
  modulo track pitch): a design with many off-grid placements has many
  classes.
- **The post-route antenna loop** re-runs a full `detailed_route` after
  every `repair_antennas`, up to `MAX_REPAIR_ANTENNAS_ITER_DRT` (5) times.
  `SKIP_ANTENNA_REPAIR_POST_DRT=1` skips it.
- Antenna repair (`GlobalRouter::repairAntennas`) at each iteration:
  check, jumpers (grt only), diodes, **dpl legalises**, incremental grt
  with pin-access update.

## Where the memory goes

drt builds its own `frDesign`, a copy of the odb geometry, plus
region-query R-trees, next to odb and STA (unmeasured; roughly twice the
geometry).

## Levers

| ORFS variable | Effect |
|---|---|
| `DETAILED_ROUTE_END_ITERATION` (64) | last iteration; the strategy table ends at 64 anyway |
| `DETAILED_ROUTE_ARGS` | **replaces** all defaults, including `-verbose 1` |
| `SKIP_ANTENNA_REPAIR_POST_DRT`, `MAX_REPAIR_ANTENNAS_ITER_*` | the antenna loops |
| `VIA_IN_PIN_MIN/MAX_LAYER` | access-point lever for DRT-0073 |
| `SKIP_PIN_ACCESS` (carried 0085) | studies only: grt without pin access |

## Futile, or nothing there

- Capping drt's threads: it wants every thread; capping cost ~15 %
  (bazel-orfs #968).
- Iterations past a plateau.

## DRT-0073: no access point

A hard stop from `genInstAccessPoints`, raised at grt's `pin_access`.
Ask the odb-debug `pin_access` tool for DRT's own markers on every
rejected candidate (`odb-debug` skill). Known causes here:

- A macro pin 2 nm off-track because mpl's Snapper snapped only SIGNAL
  pins, not the clock (carried 0177, not upstreamed).
- Wide pins on a macro clock pin (bazel-orfs #1294 trap 8).
- OpenROAD #11766 (DRT-0073 names no rule) is open; the maintainer says
  there may be no single rule to name.

## History

- Total-order priority queues for deterministic results: OpenROAD #10816
  merged. Abort early without guides: #11144 merged.
