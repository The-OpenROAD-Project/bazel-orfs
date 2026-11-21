# Global floorplan from synthesis

Screen a macro cut for a floorplan before any block is built, cheapest
check first, and plan the floorplan when it fits. Three stages, all Bazel
actions keyed on their inputs, so a changed block reruns only its own
extract and a changed constraint only the plan.

```
block synthesis ──floorplan_extract──► <block>.block.json ─┐
parent synthesis ─floorplan_parent───► <parent>.parent.json ├─floorplan_plan──► verdict.json, verdict.md,
any synthesis ────floorplan_pdk──────► <platform>.pdk.json ─┘                   floorplan.json
cut.json, constraints.json ─────────────────────────────────┘        │
                                                floorplan_consume ◄──┘ ──► each flow from its floorplan stage on
```

## Mock the blocks, iterate on the top

Without mocks, every floorplan iteration waits for each block's
synthesis, place and global route before the parent can start: a loop
of days. With a mock `.lib` and `.lef` per block, made from synthesis
and the plan (ports, outline, pins), the parent runs with no block
built. The rungs then climb in cost: seconds (pin fit, Rent, wire
demand), about a minute (cone escape, pin-layer cost), minutes (tangled
clusters), tens of minutes (the parent's route-0, in the dirty lane),
hours (real blocks and global route, once a plan survives). That fast
dirty-lane loop, from synthesis data alone, is what an AI or human
triage loop needs; the slow truth comes only at the end.

## Extract

- `floorplan_extract(name, src, arguments)`: `extract_block.tcl` on a
  block's `_synth`. Area and `die_rule`, the outline the block's own flow
  draws (pass the flow's floorplan variables: a synthesis stage does not
  carry them); every port bus with its width and its boundary timing,
  the netlist's own delay (`in2reg`, `reg2out`, `in2out` per bus, worst
  bit named); every hard object with its pins by side and the port buses
  they reach through the block's cells and at most one register.
- `floorplan_parent(name, src, blocks)`: `extract_parent.tcl` on the
  parent's hierarchical synthesis (`OPENROAD_HIERARCHICAL=1`, the blocks
  kept modules, anywhere below the top). Every crossing between block
  buses, the glue (every cell in no block) and the top's ports, with the
  bits of each end, how they connect (wire, combinational, a glue
  register) and the glue's own delay.
- `floorplan_pdk(name, src)`: `extract_pdk.tcl`. Per routing layer the
  unit RC `setRC.tcl` installs, track density, pins per micron of one
  pin layer, and the optimally repeated wire's ps/um from the resizer's
  own buffer-into-wire delay.

## Plan

`plan.py` (stdlib; `pin_plan.py` is its placer and router) lays the
macros and the glue out (pin_plan's analytic placer, or the constraints'
places), sides every bus toward its partner, and runs the rungs. Each
rung measures (track spacing per side and pin layer, demand against
capacity, path budgets) and fails only against a limit the design's
calibration file supplies (`floorplan_plan(calibration = ...)`, each
limit with the run it was read off); without one it reports and ranks.
The first rung that fails stops the plan:

| rung | finding |
|---|---|
| a `pins_per_um` | a side facing its partners under the track spacing the design has seen route; a side turning to a partner beside it is reported, not judged |
| b `area` | a slot under the block flow's own outline; the die under the macros, glue and channels |
| c `aspect` | an outline outside its range or under its largest hard object |
| d `internal_arrangement` | `side_blocked`: hard objects wall a pin side; `no_internal_arrangement`: they do not fit |
| e `channel_capacity` | `no_channel`, `over_capacity`: a channel's demand over its tracks, per layer at the constraints' share |
| f `path_budget` | a cross-macro chain no layer pair closes; `layer_capacity`: the upper pair's tracks |

Every failure names its block, side, bus or channel and its excess;
`remedies.py` runs each remedy as a what-if (the plan again on the edited
inputs) and ranks them by effect. `--all` runs every rung.
`floorplan.json` (feasible plans only) holds the die, each macro's
place, outline and per-bus pin ranges, ORFS coordinates.

## Consume

`floorplan_consume(name, plan, macros)` writes, per block, an
`extra_arguments` JSON for its floorplan stage (DIE_AREA, CORE_AREA) and
an IO_CONSTRAINTS script (`set_io_pin_constraint` per bus), optionally
`set_macro_guidance_region` per hard object; for the parent, its die and
a MACRO_PLACEMENT_TCL. Synthesis never reads the plan.

## Where it is proven

- `test/floorplan_toy`: every rung's seeded fault is the first stop with
  the right block, side and bus, the clean cut plans feasible and routes
  through the flow (`//test:local`); the planner's own tests run on its
  frozen extracts (`testdata/toy`) in CI.
- `test/macro_select`, `test/auto_memories`: real asap7 numbers against
  the pin-wall arms; `test/macro_select/floorplan_calibration.json` holds
  the facts its runs measured.
