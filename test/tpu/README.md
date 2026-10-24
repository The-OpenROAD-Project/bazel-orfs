# tpu: abutted tiles, the parent a macro too

ORFS's tpu, a systolic array of 8 x 8 processing elements on asap7, built
as 17 macros and no standard cell at the top:

- **16 identical tiles** of 2 x 2 elements, carved out of the flat design
  by yosys (`//tools/carve`): the design's own cells regrouped, the RTL
  untouched, the result proven equivalent by kepler-formal with a
  negative control that must be refuted.
- **the parent as a macro**: everything else of tpu (the skew and deskew
  registers, the clock root, the weights in) is one C-shaped macro whose
  notch holds the tiles (`//test/abutment:io_notch.tcl`).
- **abutment**: every tile meets its neighbours and the C pin on pin;
  every pin is placed by rule before anything is built
  (`//tools/carve:pin_plan`), so no macro waits for another.

![placement density across the C and its 16 tiles](floorplan.svg)

Placement density at global route, each tile's own cells drawn in place:
the tiles are 80 % full, the C's arms around them hold its 676 um2 of
skew and deskew registers in a sparse 5.6 %.

## Why

QoR is the best result within a build budget, and no budget is infinite.
In a hierarchical flow the parent places, repairs and routes around its
macros' abstracts: it waits for every macro, and every macro change
re-places it. Here the parent is a macro like the tiles, built from the
same pin plan, so

- every macro, the parent included, builds side by side;
- the top level is placement and a timing read: seconds;
- an RTL edit in a tile rebuilds that tile, nothing else.

Faster round trips buy more exploration within the same budget, and
exploration is what QoR is made of.

## Results

At global route; the period is the reg2reg minimum period stitched
across the C and its 16 tiles, each with its own cells and wires
(`tpu_stitched`), against flat built the same way from ORFS's RTL
(`tpu_flat_stitched`). Both arms' settings are their best from the same
search (ORFS AutoTuner's knobs, flat given five times the CPU); the
periods are means of three placement seeds (the flows here are the
first seed: 665.2 ps and 724.0 ps).

| | tiles in a C | flat |
|---|---|---|
| reg2reg minimum period | **672.6 ps (92 %)** | 729.3 ps |
| a fresh build, critical path | **76 s**: the tile 66 s beside the C's 23 s, then the top level 10 s | 436 s |
| an RTL edit in the processing element | **99 s** | 487 s |
| search CPU until it beat flat's best | **about 300 s**, its first trial | never, in 80,545 s |
| die | 1.39 x | 1 x |

![best period against CPU spent](period_vs_cpu.svg)

The carve's first sensible floorplan already beats everything flat
reaches; tuning either arm moves its period by less than a seed does.

![an RTL edit's round trip](round_trip.svg)

## The rules of the game

tpu is **mesochronous** with its surroundings: the same clock frequency,
a fixed but unknown phase. The clock reaches each tile through the tiles
before it (below), so the phase at tpu's registers is not the clock
root's, and nothing outside should depend on it. Data crosses tpu's
boundary through mesochronous FIFOs, one on its inputs and one on its
outputs, which are assumed to exist outside tpu and are not part of this
design. So:

- **Only reg2reg paths are judged.** The quality of results is the
  reg2reg minimum period, stitched across every macro: the clock period
  minus the worst reg2reg slack.
- **The boundary is a budget, not a constraint**: inputs to registers
  and registers to outputs are `set_max_delay` targets for repair
  (`flow/platforms/asap7/constraints.sdc`), with no input or output
  delay, since the phase they would be measured against is unknown.
- **tpu has every pin on its bottom edge**: it is itself a macro that
  abuts its parent, where the FIFOs are. Inside, each macro has its pins
  on the sides its neighbours are on.
- **Every macro routes on M2-M8**; M9 carries power from the level above.

## How it is clocked

The clock, reset and load enable enter each row of tiles from the C at
its west end and run east through the tiles with the activations, one
buffer per tile; north-south neighbours enter at the same time. Only
neighbours' skew matters, as Fisher and Kung showed for pipelined
clocks in systolic arrays. The bottom row passes its clock down to the
deskew registers in the C.

![clocking](clocking.svg)

Measured on the stitched design (`tpu_stitched_clock`, drawn by
`clock_plot.py`): each tile sees the clock 77 ps after its west
neighbour, so data flowing east is captured later than it is launched,
which setup gains and hold pays for; rows enter together, so data
flowing south sees a few ps either way. No clock tree is balanced across
the array: the skew follows the data instead. tpu's worst path starts
and ends inside one tile, so this does not shorten its period; it is
what lets the clock run through the tiles without a tree over them.

![clock arrival per tile](clock_skew.svg)

## Build

```sh
bazelisk build //test/tpu:tpu_stitched       # the period across every macro
bazelisk build //test/tpu:tpu_flat_stitched  # flat, read the same way
bazelisk test //test/tpu:tpu_2x2_lec_test    # the carve, proven equivalent
```

`tpu_block_grt`, `tpu_rest_grt` and `tpu_grt` are the tile, the C and the
top level; `tpu_2x2_negative_control_test` checks that the proof refutes
a tile with one port broken (it takes the better part of an hour).

## Limits

- **Area**: 1.39 x flat's die; small macros keep margins and will not
  place as densely as flat.
- **The parent's repair does not see inside the tiles**: it times the
  tile pins as ports with budgets. On tpu that costs nothing, its worst
  path is inside a tile; where critical paths cross the parent, it is
  untested.
- **Global route**: the flows stop there. The top level's power reaches
  the C only: pdngen takes the C's whole box as occupied and draws
  nothing over the tiles.
- **One buffer a hop** is optional (`BUFFER_PORTS_ARGS=-outputs` on the
  tiles and the C): on tpu the worst path never crosses a boundary, so it
  does not move the period.
