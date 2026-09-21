# XiangShan on OpenROAD: the timing inventory

The project's KPI is the minimum clock period at global route, f from
period minus WNS at a slightly negative WNS, on a floorplan that routes.
The target is congruent with a taped-out core: about 1000 ps at global
route on asap7, so 800 ps at synthesis, and no pathologies. Each entry
below is a well-studied problem that stands between the flow and that
number, with what commercial flows do about it, what OpenROAD or yosys
has, and where it shows in XiangShan. Ranked by how many of the worst
paths it owns; re-ranked after every fix. Data: the flat hierarchical
synthesis `XSCore_hier_synth` at 800 ps, probed through its odb-debug
target (`tmp/probe/`), then the takes.

## 1. Unbuffered high-fanout nets in the synthesis netlist

The worst synthesis-stage path is -7225 ps: two nets of fanout 1410 and
1056 (`enqRob_req_*` into 512 ROB entries) cost 2.6 and 4.5 ns as bare
INVx1 and NAND2x1 drivers. ABC does not buffer; ORFS buffers at the place
stage (`repair_design`), and its floorplan stage only removes buffers. So
synthesis-stage slack ranks nothing until the design is buffered. A
buffer tree for fanout 1400 is 5 to 6 levels, 150 to 200 ps of an 800 ps
budget, which is the real cost that stays.
Commercial: buffering and logic duplication during synthesis, fanout
limits driving restructuring. Here: run `repair_design` before judging;
measure the tree depth these nets end up with; broadcast nets with a
thousand loads are an RTL articulation question (duplicated valid bits,
staged enables) as much as a tool one.

## 2. Generated register files' timing models

`RenameBufferFile` (a structured memory, `tools/structured_gen`) shows a
library setup time of 292 ps at its write port, over a third of the
period, on the worst register-to-register path after the fanout net.
The .lib the generator writes is the question: whether that number is the
generator's model or the array's real requirement.

## 3. (placeholder) Clock gating and clock-as-data

To be confirmed from the buffered timing: whether any path timed against
the ideal clock starts at the `clock` port through gating logic.

## 4. `repair_design` on the whole core's synthesis netlist does not return

The time table wants the flat 138-module synthesis (`XSCore_hier_synth`,
about 8 M cells) buffered before its slacks are read (entry 1). In the
odb-debug session `repair_design` ran 6 h 34 min at 2.5 cores and was
killed unfinished on 2026-09-20; its memory fell from 34 to 19 GB over the
last two hours, so it was progressing, not stuck. A stage that the blocks
finish in minutes each (the planned blocks, 1 to 3 M cells, placed in 20
to 60 min including their own `repair_design`) takes the whole core past
a working day. The time table therefore comes from the blocks' own flows
(boundary slacks at their place stage, where the buffering has been done
by the flow) and from the parent's place, not from one flat session; a
flat `repair_design` on a core of this size is itself an entry for the
tool: which of its passes scales worse than linearly here.

Measured the same day on one block: `repair_design -pre_placement` (the
resizer's fanout-and-slew round without parasitics, under the SDC's
`set_max_fanout 32`) on the Frontend synthesis netlist, 1.5 M cells, took
575 s in the odb-debug session and moved WNS from -492 to -468 ps at
800 ps; the worst path stayed the same input-to-register crossing, from
the backend's redirect port through Ftq into the uBTB hit compare, 100
pins before and 140 after. A block synthesised alone has no fanout
phantom (no stage past 32 on any of its 11 391 worst path ends); the
phantom belonged to the whole-core netlist. So the per-block pass is
minutes and the whole-core full repair is the outlier; whether the
pre-placement pass alone scales to the core is untested and not needed.

## 5. The legaliser after CTS is the parent's budget breaker

Take 19's planned parent (1.3 M own cells, four real blocks, no legaliser
window set): CTS stage past 2 h at 47 GB when sampled with `perf` for
15 s on 2026-09-20. Every hot frame is the negotiation legaliser: 13 %
`dpl::NegotiationLegalizer::negotiationCost`, then `odb::compare_by_id`
and `dbInst::getMaster` (19 % together: a sorted-set lookup per
candidate location), `Grid::gridEndY`, `PlacementDRC::checkBlockedLayers`,
`getSiteOrientation`, `isValidRow`, `paintPixel`. The place stage's
long single-threaded sub-step at 33 GB had the same profile shape. On
the dissolved die of take 17 the same legaliser finished the CTS stage
in 23 s at margin 1.5 and took 82 min at margin 2 without the channel
floor, so the cost is not the cell count: it is how many cells the
clock-tree insertion drops where there is no room, in channels and along
pin sides. Candidate fixes, cheapest first: keep the clock buffers out
of the channels (a placement blockage per channel at CTS, or wider
channels in the plan); `-use_diamond_legalizer` with the default window
for the CTS stage; the lookup cost in `negotiationCost` as a tool study
(profile saved next to the take). Profile: tmp/take19/cts_perf.txt.

Take 20 (2026-09-21, diamond search at its default 27 um window): the
place stage took 76 min in all, against take 19's 2 h 19 min with the
negotiation legalizer, and failed on one cell of 3 573 552, a repair
buffer (`wire323088`) that neither the diamond move nor rip-up could
seat; patch 0004's supply check did not fire, so the pocket is local, a
single cell with no free site within 27 um. Take 21 runs the diamond
with a 100 um window for that cell.

Take 21 (2026-09-21, diamond at a 100 um window): the place stage passed
in 80 min; the CTS stage's legalisation was at 1 h 30 min in the diamond
search, `perf` showing `diamondSearch`, `canBePlaced`, `checkPixels`,
when the take was stopped by decision. The placement's density map,
from the odb-debug dump at 45 um bins: the parent's 3.85 M cells in a
1.2 x 1.1 mm blob at 60 to 87 % between the blocks, and the 18 bins at
75 % or more owned half by the reorder buffer (256 copies of
`RobEntryCell(idx[8:0], in[3618:0]) -> entry[51:0]`, 3 619 nets of
fanout 256, 1.04 M cells for 13 000 flops of state), a quarter by
dispatch's tables, a quarter by the memory-control tables. That is not a
legaliser problem and not a density problem first: it is a structure
that belongs in a generated macro. The pivot is `ideas/structured-macros.md`.

## 6. Hierarchical `link_design` of the parent is string-keyed and serial

Building the parent's synthesis ODB (`link_design` with hierarchy kept,
3.7 M instances, 3.6 M nets, four macros) takes minutes, 5 to 8 on the
pre-pivot parent, single-threaded at 20 GB. An eight-second system-wide
`perf` sample on 2026-09-21 (tmp/take19/link_design_perf.txt): 13 %
`ord::Verilog2db::constructModNet`, 11 % tcmalloc, 4.7 % `memcmp`, 3.8 %
`Verilog2db::staToDb`, 3.4 % `sta::Network::pathName`, 3.0 %
`dbModule::findModInst(const char*)`, and hash and tree lookups keyed on
`std::string`: the linker resolves module nets through the name space,
building hierarchical names to look up objects it created a moment
before, and allocates and frees the temporaries.

Done right it is tens of seconds: about 20 M small objects, one
allocation and one hash insertion each, at memory bandwidth on one core,
plus the Verilog parse at 100 MB/s or more. The gap is a factor of ten,
and it is pointer identity and arena allocation in the linker, not
threads. A tool item; the study pays it once per parent synthesis.

## Method notes

- Synthesis-stage numbers are read after `repair_design`, never before;
  on the whole core that means the blocks' and the parent's place stages
  (entry 4), not a flat session.
- Retiming (`SYNTH_RETIME_MODULES`) is applied per module where the idiom
  is present, measured per module on its own synthesis; unverified for
  equivalence by ORFS, so the list stays short and named.
