# grt: global route (FastRoute)

Paths are in OpenROAD's `src/grt/`, ORFS's `flow/scripts/`. Read at the
OpenROAD pin of 2026-11; line numbers drift, function names do not.

## Reading the log

`FastRouteCore::run()` (`fastroute/src/FastRoute.cpp`): FLUTE tree per
net, 2D pattern route (L, Z, monotonic), the **2D congestion loop**
(rip up and maze-route nets on overflowed edges, history cost growing),
layer assignment to 3D, two 3D maze passes if 2D overflow reached 0,
`fillVIA`.

- GRT-101/102 "extra iterations" / "Start extra iteration i/N": you are
  in the congestion loop. **GRT-102 does not print the overflow.** To see
  whether it converges, `set_debug_level GRT congestionIterations 1`
  ("=== Congestion Iteration i - TotalCongestion N"); `GRT timer 1`
  prints phase times. Phase times always land in metrics as
  `global_route__fastroute__*_s`.
- GRT-96 final congestion per layer; GRT-115 congestion accepted, GRT-116
  congestion is an error; GRT-704 proposes a lower layer adjustment;
  GRT-230 hit the cap of 25 overflow increases; GRT-9 "rerouting N nets"
  is incremental grt (inside repair).
- GRT-273/296/297 "Disabled NDR": the soft-NDR restart, which **resets
  the iteration counter to 1**. A loop running far past
  `-congestion_iterations` is this.
- The loop exits on overflow 0, `i > congestion_iterations` (Tcl 50,
  ORFS forces 30), 25 overflow increases, 50 iterations with no new best,
  or 500 rounds.

## Where the time goes

- **The 2D maze loop, serial.** The only parallel kernel needs
  `-snapshot_batched_width N` (default 0; ORFS does not pass it) and is
  off at low overflow and with hard NDRs. Threads do nearly nothing for
  FastRoute.
- **Timing-driven net ordering**, on by default (`critical_nets_percentage`
  10): every third congestion iteration re-estimates parasitics on all
  nets and asks STA for every net's slack. Unmeasured; lever is
  `-critical_nets_percentage 0` in `GLOBAL_ROUTE_ARGS`.
- **Resistance-aware final 3D passes** (`ENABLE_RESISTANCE_AWARE`, asap7
  default on): both passes rip up every negative-slack net, 58.8 of 60.5 s
  of FastRoute on the measured block; each pass has a ~4 s fixed cost even
  with nothing rerouted (bazel-orfs #1487).
- **In a 5_1_grt stage, FastRoute is usually not the big item.**
  `repair_timing` with incremental grt and `estimate_parasitics
  -global_routing` (4-5 full calls in `global_route.tcl`) dominate; see
  [rsz.md](rsz.md). On XSTile: route 1,224 s on under 2 cores, 942 s of
  it kernel time (no huge pages, 37 M minor faults), estimate 130 s x2
  (`ideas/xiangshan-timing.md` entry 36).
- **Large-overflow mode** (total > 15,000 and max > 400) widens maze
  windows to `max(x_grid, y_grid)/30`: each iteration gets slow. A design
  in this mode will not converge by iterating; fix the floorplan.

## Where the memory goes

GCell = 15 pitches of the fourth routing layer
(`dbBlock::getGCellTileSize`). Per layer x gcell: `Edge3D`, `Cap3D`, the
3D maze scratch arrays: ~70-80 B before our patches. Plus per-net trees
and routes, growing with wirelength in gcells. The peak of a grt stage is
the sum of steps that each keep their state: router, STA, parasitics,
dpl pixel grid ([dpl.md](dpl.md)).

- **Congestion markers**: ORFS's default `GLOBAL_ROUTE_ARGS` has
  `-congestion_report_iter_step 5`, which writes an odb marker per
  overflowed edge listing every net through it, every 5 iterations. On a
  badly congested design it bloats memory and the .odb.

## Levers

| ORFS variable | Tcl | Note |
|---|---|---|
| `ROUTING_LAYER_ADJUSTMENT` (0.5) | `set_global_routing_layer_adjustment` | lower = more capacity, harder drt; "hours to minutes" per variables.yaml |
| `MIN/MAX_ROUTING_LAYER` | `set_routing_layers` | asap7 defaults to M7; resistance-aware is worth ~141 ps at M9 on tage_update (bazel-orfs #1174), M9 without it no better than M7 |
| `GLOBAL_ROUTE_ARGS` | `global_route ...` | **replaces** the defaults: re-add `-verbose` |
| `GRT_SEED` | `set_global_routing_random -seed` | perturbation probe |
| `SKIP_INCREMENTAL_REPAIR` | skips repair at grt | measures nothing about repair, see [rsz.md](rsz.md) |

## Futile, or nothing there

- More congestion iterations once the best overflow plateaued.
- More threads for FastRoute.
- `-allow_congestion` as a fix: drt hard-errors on congested guides
  (DRT-352). It is a way to get an .odb to look at, nothing more. The
  incremental reroutes inherit it only through `GLOBAL_ROUTE_ARGS`
  (EST-0005 fixed in OpenROAD #11525/#11754, ORFS #4563).
- A route that does not converge (XSTile parent: 7 h in maze iteration 1
  of 30 at 105 GB, bazel-orfs #1055) is a macro-selection or floorplan
  problem: `macro-selection` skill. The capacity guard GRT-0228 on an
  11 um channel was fixed by planner channels (entry 13).

## History: what we tried

- **Memory, XSTile Top 196.3 -> 57.4 GiB, routes identical**
  (bazel-orfs #1474, OpenROAD #12075 open; the maintainer questions
  where the global usage graph should live). Merged upstream: #12074,
  #12148 (2 B per edge and layer, sparse NDR), #11130. The rest is carried
  as 0183-0199: smaller types, scoped maze arrays, per-net finish,
  `-no_incremental`, and an mmap backing file with page-out (0188/0189/
  0191/0196-0199).
- `global_route -cleanup` (release router state before final
  parasitics): 3.8 GiB, closed, folded into `-no_incremental`
  (bazel-orfs #1132).
- Antenna repair at grt: 108 -> 89 GiB when skipped, same period
  (bazel-orfs #1133).
- `getCongestionNets` O(P x N) hung congested designs for hours: fixed,
  OpenROAD #11114.
- Soft-NDR reset loop taking hours: `-max_soft_ndr_resets` OpenROAD
  #10988 closed. **Dead end.**
- One resistance-aware 3D pass instead of two (0200): 62.1 -> 32.4 s for
  +0.12 % period; OpenROAD #12121 closed because the second pass wins QoR
  when upper layers are scarce. Two passes on selected nets saves only
  5-11 %. 0200's fate is open.
- Vias priced ~14x too cheap against wires: OpenROAD #11350 open.
- Parallel parasitic estimation: OpenROAD #11569 (grt 3,796 -> 2,562 s),
  #11599, #11549 merged.
- "Cannot route, here is why" check: OpenROAD #11452 closed pending an
  example; grt edge usage warning 0122 retired. **Dead end so far.**
