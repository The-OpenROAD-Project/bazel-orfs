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

## Method notes

- Synthesis-stage numbers are read after `repair_design`, never before;
  on the whole core that means the blocks' and the parent's place stages
  (entry 4), not a flat session.
- Retiming (`SYNTH_RETIME_MODULES`) is applied per module where the idiom
  is present, measured per module on its own synthesis; unverified for
  equivalence by ORFS, so the list stays short and named.
