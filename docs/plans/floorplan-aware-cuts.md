# Floorplan-aware macro cuts: a synthesis-speed loop

A plan, not done. Written to be picked up on its own, on a machine with
the memory for XiangShan's XSTile (one parent run at a time, about 90 GB
at global route).

## The use case

A macro is usually an RTL module hardened as it was written. A module
boundary was drawn for code organisation, not timing, so it often cuts
through combinational logic. Logic on the wrong side of a hardened
boundary is stuck there: synthesis cannot optimise it with its
neighbours, and placement cannot move it next to them.

The loop moves boundaries to where timing wants them, without editing
the RTL:

- **Analysis.** On a timed result, the keep census
  (`tools/macro_select/keep_census.tcl`, in its own pull request) lists the macro pins and kept
  modules that the paths over the target cross in the middle of a cone.
  In yosys, measure the logic between each such port and the first
  register behind it.
- **Surgery.** A yosys script before synthesis, carried as
  `SYNTH_VERILOG_SURGERY`:
  - *split*: the logic between the registers becomes `<name>_core`, the
    macro; the boundary logic stays in a wrapper with the original name,
    which dissolves into the parent. It is the shape OpenROAD's RAM
    generator already produces for memories (`generate_ram_netlist
    -periphery verilog`), so the flow treats it the same way;
  - *regroup*: where instances that belong together sit in different
    modules, flatten the levels between them (`keep_hierarchy`), then
    gather them into one new module as the macro's top (`submod`).
- **Keep lists** are part of the same search. They were a first pass,
  chosen by size to split synthesis into partitions; each keep is a
  candidate, dropped or added.

Nothing here dominates: flattening everything does not, in synthesis,
global placement or macros, and the reason is not known
(`.claude/skills/macro-selection`). Every candidate is an A/B in both
directions, and a surprise is shrunk until it is understood: a yosys or
ABC bug to report, or a mechanism to write down.

## The cost

The mass over the target, as every XSTile A/B is judged:

    cost = sum over reg2reg endpoints of max(0, P_e - T)

T is the target period (2,000 ps for XSTile), P_e an endpoint's period
(clock period minus slack). The count of endpoints over T is reported
beside it and breaks ties. Not the worst slack: one path decides it, and
a cut that fixes thousands of endpoints while moving the worst by a
picosecond would read as nothing.

Without placement, P_e is estimated from the synthesis result and the
candidate's own plan:

    P_e = cell delay at zero wire
        + w * sum over boundaries crossed of d(pin, partner)

d is the planned distance from a macro pin to its partner, from the
candidate's floorplan (below), so a cut that moves pins is judged by the
distances it creates. w is a delay per micron, fitted on a placed
result's long-wire repeaters. w = 0 is the plain synthesis loop; the
calibration says whether it is enough.

A candidate is accepted when the cost falls by more than 2 % and every
constraint holds. The zero-wire numbers are deterministic; the margin is
for the error of the distance estimate.

## Floorplan awareness: the tallies and the constraints

Per candidate, from its synthesis result:

| Tally | Source | Feeds |
|---|---|---|
| Memories per macro | `AUTO_MEMORIES` / `generate_ram`: which memories become macros, their count and size, and which side of a cut each lands on | the macro's area and its internal floorplan |
| Macro size | standard-cell area plus memory macros, at the block's density | the outline (`plan_floorplan.py`) |
| Pins | `probe_pin_partners.tcl`: each pin's partner, another block, parent logic or a top port | pins per side, partner segments |
| Macro placement | `plan_floorplan.py`'s annealer on the outlines and partners | block positions, planned pin positions, d |

Constraints; any one failing rejects the candidate whatever its cost:

- **The macros fit:** every outline in the die at its density, the
  annealer's channel check passing.
- **The pins fit:** no side over its limit (about 13.9 pins per micron
  measured, with the logic facing the pin side; a block whose pins want
  two regions is two macros or none: macro-selection skill).
- **Every memory accounted for:** a memory macro inside some outline, or
  standard cells counted in an area.
- **Each macro closes alone:** its own reg2reg period no worse, so the
  gain is not moved into a block.
- **Function unchanged:** the wrapper and core flattened back equal the
  original module structurally, cell for cell and net for net up to
  renaming; a copy with one connection broken must fail the same check.
  Exact for a pure move, and cheap at any size, which matters because
  kepler-formal is used on small designs only.
- **Synthesis time and memory in budget:** the loop has to stay fast.

Recorded, not optimised, until they start to get worse: feedthroughs,
area, pins per micron.

## The loop

1. Census on the current result.
2. Propose a cut or a keep change, in either direction.
3. Re-synthesize the affected parts only.
4. Tally memories, areas and pins; run the planner.
5. Cost; accept or revert.
6. Every few accepted changes, one run to global route, ranked there:
   the loop is a filter, global route decides.

## Calibration, the first gate

Does zero-wire synthesis predict global route at all? Two points:

- the XSTile parent's synthesis with its keep list as is, at zero wire,
  against the same design at global route (the B0 baseline: 5,259
  endpoints over 2,000 ps, 733 ns excess);
- the same with `Dispatch`, `DecodeStage` and `Rename` no longer kept,
  synthesis against its own global route.

If the two disagree in direction, the loop is not usable as is and the
distance term comes first.

## Where to start: XSTile's numbers

The keep census on XSTile at global route (the parent placed without
`set_max_fanout`, otherwise the baseline), 6,204 endpoints at or above
2,000 ps, 901 ns excess, worst 2,521.7 ps:

| Boundary | Paths cutting it mid-cone, or at its pins | Their excess |
|---|---:|---:|
| `Dispatch` (kept) | 3,569 | 545 ns |
| `FltRegionModule` pins (hardened) | 3,545 | 542 ns |
| `DecodeStage` (kept) | 1,991 | 501 ns |
| `Rename` (kept) | 1,921 | 421 ns |
| `UopBufferCtrlDecoder` (kept) | 992 | 146 ns |

Shares overlap: a path crosses several boundaries. The floating-point
region's pins and `Dispatch` carry nearly the same paths: that corridor
is the first candidate for a split. The worst path launches 876 ps
inside `Frontend` before its pin and spends 952 ps of 2,284 in the
parent in buffers (444 ps long-wire repeaters, 356 ps fanout, 152 ps
slew), so distance is real and the w term will be needed there.

An earlier attempt at the split, on `FltRegionModule` before the
baseline moved to `generate_ram`, measured 16.5 % of the block in its
interface cones, with 83 feedthroughs.

## What exists and what is missing

Exists: the keep census; `probe_pin_partners.tcl`,
`probe_boundaries.tcl`, `keep_under.py` and `plan_floorplan.py` in
`tools/macro_select`; `generate_ram -periphery verilog` as the shape to
copy; `SYNTH_VERILOG_SURGERY` as the hook.

Missing:

- the split and regroup script, with the structural identity check and
  its negative control, tested on a small design;
- the planner as a fast step, seconds to minutes, on a candidate's
  tallies;
- the memory tally per side of a cut;
- d from planned pin positions, and w fitted on a placed result;
- re-synthesis of only the changed parts: today a parent synthesis
  redoes every kept module.

## Rules

One heavy XSTile job at a time. No register added and no RTL edited:
moving existing logic, flops included, across a boundary adds none. No
timing exceptions. Nothing upstream without the human's order; a yosys
or ABC bug found on the way is carried here as a reproducer.
