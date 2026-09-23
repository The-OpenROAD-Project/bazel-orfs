# Global-route scaling: the grid, not the netlist

Global route on the 3.6 mm XiangShan parent ran seven hours into the first
of thirty maze iterations at a 105 GB working set, on a machine with
62 GB. Perf put 95 % of the cycles in FastRoute's pattern routing and
edge-usage reads, then 94 % in the sequential maze router, 69 % of which
was one linear search over the Dijkstra heap. None of it is XiangShan:
OpenROAD's GCell is 15 track pitches of metals 2 to 4, 0.54 µm on asap7,
so that die is a 6 700 by 6 700 grid, and every phase and most of the
router's memory scale with the grid.

This directory measures that at tens of seconds so the fixes can be
designed with a person in the loop, and drives the hours-long runs on the
real design unattended.

## The design: wirebound with anchors

`flow/designs/asap7/wirebound` already has the netlist property this
needs: every group's fan-in is scattered by odd strides, so the
inter-group nets cross the die however the placer folds the design. What
it lacks is a reason to spread on a die far larger than its cells; a
placer collapses it into one blob and the nets shrink with it.
`-D WIREBOUND_IO_ANCHORS` adds one input and one output port per group,
and `io.tcl` pins each group's ports to one edge of the die, round robin.
Die size is then set by hand (`DIE_AREA`, `CORE_AREA`) at a fixed group
count, so grid size and net count vary independently:

| target | die | grid (0.54 µm GCells) |
|---|---|---|
| `wirebound_grid_d500_g32` | 500 µm | 926² |
| `wirebound_grid_d1000_g32` | 1 mm | 1852² |
| `wirebound_grid_d2000_g32` | 2 mm | 3704² |
| `wirebound_grid_d3600_g32` | 3.6 mm | 6667², XiangShan's |
| `wirebound_grid_d2000_g64` | 2 mm, twice the nets | 3704² |

`MAX_ROUTING_LAYER` is M5 here (wirebound's own M9 is for its RC study)
and `ROUTING_LAYER_ADJUSTMENT` 0.7, so demand concentrates enough on an
otherwise empty die for overflow, and with it the maze router, to occur.
Timing repair is off everywhere: the measurement is the router.

## The measurement: `grt_bench.tcl`

One script, run through ORFS's `run` target from a stage's deployed
`_deps` tree, on the wirebound arms and on XiangShan alike:

```sh
bazelisk build //test/grt_scaling:wirebound_grid_d2000_g32_grt_deps
bazelisk run //test/grt_scaling:wirebound_grid_d2000_g32_grt_deps -- --install $PWD/tmp/wb2000
cd tmp/wb2000 && ./make run RUN_SCRIPT=$PWD/../../test/grt_scaling/grt_bench.tcl \
    ODB_FILE=$PWD/_main/test/grt_scaling/results/asap7/wirebound/d2000_g32/4_cts.odb \
    GRT_BENCH_OUT=$PWD/../baseline.json
```

It loads the CTS ODB the way `global_route.tcl` does, times `pin_access`
and `global_route`, and writes one JSON: the two wall times, FastRoute's
own phase timers (`initial_rsmt`, `route_l`, `monotonic`,
`overflow_iterations`, ...), wirelength, the router's overflow report
lines, peak and final resident memory, and the GCell tile and grid
extent. The JSON is rewritten after each step, so a run that is killed is
still a result. Knobs: `GRT_BENCH_ARGS` (appended to `global_route`),
`GRT_BENCH_LAYERS` (`set_routing_layers`), `GRT_BENCH_PIN_ACCESS=0`,
`OPENROAD_EXE` for a bring-your-own binary.

## The matrix: `grt_bench.py` and `report.py`

`grt_bench.py matrix.json results/` runs every (design, arm, repeat)
cell serially in its own systemd scope with a memory cap and a wall-clock
timeout, samples the router's resident and swapped memory every five
seconds to a CSV beside the result, optionally wraps the run in
`perf record`, records how each cell ended (`ok`, `timeout`, `oom`,
`error`), and skips cells already done, so it is resumable and never
prompts. `report.py results/` is the table, each arm against the
baseline arm of its design. `matrix.json`'s shape is in the driver's
docstring.

## Method

Every question is settled on the 2 mm arm first, in the tens of seconds,
with the human choosing the next arm. Only then does the same matrix run
on XiangShan's `4_cts.odb`, overnight, every combination, no input. A
code change to the router is measured on the arm sweep (its curve
against grid size is what an upstream review wants), then on XiangShan,
one concern per patch. See `.claude/commands/no-paint-drying.md`.
