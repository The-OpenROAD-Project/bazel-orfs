# XiangShan on OpenROAD: the timing inventory

The project's KPI is the minimum clock period at global route, f from
period minus WNS at a slightly negative WNS, on a floorplan that routes.
The target is congruent with a taped-out core: XiangShan's 333 ps on
7 nm is 41.1 fanouts of four, which is 591 ps at global route on the
asap7 library the flow times with, so 473 ps at synthesis, and no
pathologies (`constraints.sdc`, `period_fo4_test`). Entries up to
25 were measured with the SDC at 800 ps. Each entry
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

**Amendment, take 23 (2026-09-22).** With the four blocks blackboxed and
the three arrays FIRM, `repair_design` on the planned parent returned:
1 714 s, 21 GB, 261 860 buffers into 57 541 nets, 29 453 instances
resized, against 56 301 slew, 23 081 fanout and 16 385 capacitance
violations. The netlist that did not return in a day was the flat core
with the blocks' logic in it. Entry 4 stands for that netlist only.

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

**Take 23 (2026-09-22), pre-CTS.** `detailed_placement` on the planned
parent, 4.56 M one-row cells at 47 % utilisation, negotiation legaliser:
5 394 s, ending in "violations stuck at 8, diamond search for 4
remaining illegal cells". Then `improve_placement` ran because the
deploy tree of the floorplan stage does not carry the place stage's
`ENABLE_DPO=0`, and the two-hour budget went there. The legaliser's
90 minutes are the number to plan with; the arrays being FIRM took
1.28 M cells out of it.

## 6. Hierarchical `link_design` of the parent is string-keyed and serial

Building the parent's synthesis ODB (`link_design` with hierarchy kept,
3.7 M instances, 3.6 M nets, four macros) takes minutes: 7 on take 22
(10:05 to 10:12), single-threaded at 20 GB. An eight-second system-wide
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

## 7. Canonicalisation on yosys's Verilog frontend: seven minutes per synthesis

`Canonicalizing RTL for XSCore` took 400 s (take 22) and 457 s (take 23's
first attempt): yosys's own frontend reading the flat core, all 2 181
modules, single-threaded at a few MB/s, before `hierarchy`, `proc` and the
RTLIL write the partitions are cut from, and again after any change to a
synthesis input (the memories views included). None of XiangShan's flows
had set `SYNTH_HDL_FRONTEND`; only the pin-wall harness ran slang. Fixed
at the root on 2026-09-21: `orfs_flow` forces slang (a flow on another
frontend has to say why), so every design in the repo parses with slang
from here on. Take 23 is the first XiangShan synthesis on it.

## 8. Memory extraction: yosys indexes every module before asking if it has a memory

`Canonicalizing RTL for XSCore` on slang still took 15 minutes on take 23,
and 12 of them were `memory -nomap` in `extract_memories.tcl`. Each of
its passes walks every module: `memory_dff` builds its per-bit driver and
consumer index (`ModWalker::setup`, memory_dff.cc:225) for a module in
the worker's constructor and asks whether the module has a memory only in
`run()`; `opt_mem_priority` and `opt_mem_feedback` scan every module's
cells the same way. The flat core has 1 870 modules and 407 of them hold a
memory cell, each a small firtool `ram_*` module; the large modules are
the logic, and the index over them is the cost. Measured on the flat
XSCore read through slang (yosys 0.68), the memory passes alone:

| run | memory passes | memory_dff | `$mem_v2` |
|---|---|---|---|
| unscoped (`memory -nomap` as shipped) | 721 s | 462 s | 407 |
| scoped to the 407 modules with memory cells | 64 s | 24 s | 407 |

Carried as ORFS patch 0079: `memory_bmux2rom` first and unscoped (it is
what turns constant muxes into a memory), then the module list from the
memory cells' names and `memory -nomap` on those modules, and
`write_json -selected` for the detector, which reads nothing across
modules. The selection's own `%m` expansion is not usable here: with a
`$` in the module name, slang's uniquified names, it leaves the module
partially selected and every pass skips it. The proper fix is an early
return in yosys's `memory_dff` before the index is built; there is no
yosys patch channel in this repo, so it is a note for upstream.

## 9. Rob after the entry file: 6 417 pointer comparators in the glue

With `RobEntryFile` generated (352 × 21 bits) and `RobEntryCell` a kept
module (30 bits of state each, one 1 251-bit broadcast input, synthesised
once in three seconds), Rob's own body still took 995 s in take 23's
first launch, 724 s of it one ABC call. Its cells after `proc`
(`stat -width` on the module alone, tmp/take23/rob_stat_proc.txt):

| cell | count | what it is |
|---|---|---|
| `$eq` 9 bit | 6 417 | every entry's index against the deq, walk and enqueue pointers, about 18 compares per entry |
| `$and` / `$or` 1 bit | 5 475 / 3 911 | the 352-wide hit and select trees over those compares |
| `$mux` 4 to 6 bit | 3 574 | per-entry field selects |
| `$pmux` 352-way | 16 | eight commit ports, one 1-bit and one 5-bit read each |
| registers | 1 524 bits | pointers, commit state, perf counters |

The comparators are the duplication fork patch 0009 (`RobEntryCellHits`,
shared one-hot decode) removes; it is on the fork branch and not yet
registered in MODULE.bazel. The 352-wide trees and the eight-entry read
at a rotating pointer are the pointer-window read the generator should
own next, alongside the flag matrix (set, clear, clear-range) for the
per-entry state that the cells keep.

## 10. Re-canonicalisation: one whole-design read per kept module

47 sessions for the parent and 62 for the blocks, each reading the
4.9 GB checkpoint (84 s, 4.9 GB) to write one module's slice: 2.5 CPU
hours per synthesis and the memory wave that caps `--jobs` at 8 to 10
on 62 GB. The fence (per-partition byte-stable inputs, commit f3c52546)
survives a one-session slicer; plan and verified primitives in
`ideas/canonicalize-slicer.md`. Before the next synthesis from the top.

## 11. CTS on the planned parent: 50 k delay buffers for four macros

Take 23, the first CTS of the parent with the four blocks as macros and
the three arrays FIRM: `clock_tree_synthesis -sink_clustering_enable
-repair_clock_nets` took 982 s at 52 GB for 12 clock nets and 179 280
sinks, 8 383 leaf buffers and 308 clock-net repair buffers, and then
**49 736 delay buffers** for "Balancing latency for clock clk": every
parent path padded to the clock insertion delay of the four block macros'
liberty models. Six times the leaf buffers, and 86 percent of the cells
the post-CTS legaliser then had to seat: 66 k violations at its ninth
iteration, still 1.4 k at the 590th, an hour and a half in. Two knobs
follow: `-no_insertion_delay` in `CTS_ARGS` for a flow not yet asked for
skew against the blocks, and clock columns in the generator so the arrays'
27 712 flops are cheap sinks (their leaf buffers today compete for the
service columns). The legaliser is the CTS stage's floor, twice the
parent's 90 minutes when the buffer count is this high.

## 12. Global route stops in pin access on one pin per block

Take 23's first `do-grt` on the planned parent (2026-09-22) failed in
`pin_access`, before any routing, with DRT-0073 "No access point" on
exactly one pin per block: Frontend's `auto_inner_icache_client_out_a_
bits_address[0]`, VecRegionModule's `clock`, Region_1's
`cg_bore_10_cgen`, MemBlock's `auto_inner_beu_local_int_sink_in_0`. The
miniature planned parent (`test/planned_parent`) had shown the same an
hour earlier, one pin per block (`u_blockd/din[0]`), and its CTS ODB is
a five-second reproducer: read it, run `pin_access`. Probing it: the
failing pin fails wherever its shape is moved (one track left or right,
eight tracks right, into a gap between working pins), with the block's
obstruction rectangles moved off its edge, and with no power shape or
parent geometry near it; the pin next to it passes at the same spot. So
it is the pin object, not its geometry, and not the parent. Open; the
grt build_test of the miniature is manual until it is understood, and
ORFS's `global_route.tcl` runs `pin_access` unconditionally, so the
route cannot start until it is.

## 13. Route-0: the wall is the channel between Frontend and MemBlock

The zero-iteration global route on take 23's CTS ODB stopped on
FastRoute's capacity guard, GRT-0228 "Horizontal edge usage exceeds the
maximum allowed (1820, 1775) usage=3313 limit=3300": 3 313 wires on one
gcell edge at about (977, 953) um, which is inside the 11 um channel
between Frontend (x 10..965, top at 1037) and MemBlock (x 976..1972, top
at 1009), 60 um below the blocks' tops. The blocks' abstracts obstruct
M1 to M5, so between two blocks a wire either crosses on M6 and M7 or
runs the channel, and the Frontend-to-MemBlock traffic (1 198 pins, both
sides' pins on their top edges) took the channel. The plan's block gap
(`gap_um` 10.8) is a placement gap, not a routing channel. The route
map the campaign wanted is one number so far, and it names the
interface the planner should give adjacent sides, or the channel it
should widen to a routing channel, before the next raid.

## 14. Timing on the parent's CTS ODB needs more than the machine has

A timing daemon (`tools/odb_debug/daemon.tcl`, GUI_TIMING=1) on take 23's
`4_cts.odb` (4.3 M cells plus 49 736 CTS buffers, 51 GB peak in the CTS
stage itself) was OOM-killed after 25 min at 56 GB resident and 118 GB of
swap, so the parent's post-CTS worst slack has no measurement yet. The
CTS stage runs with `SKIP_CTS_REPAIR_TIMING=1` and reports no timing
metrics of its own. Chain 4 measures it with one short-lived openroad
(`tmp/take23/wns_once.tcl`: open.tcl, `report_wns`, `report_tns`,
`report_clock_min_period`, one path) under a 1 h budget; if that is
killed too, the flow-side answer is a `report_wns` in the CTS stage
itself, which already holds the timing graph. Fix candidates if the
one-shot also blows the machine: what `od_wns` or the daemon adds on top
of the stage's own footprint (a second `estimate_parasitics`?), or a
`report_checks -group_path_count` on a sample of endpoints instead of the
full sort.

## 15. The deployed tree's inputs are links into the bazel output tree

`XSCore_floorplan_deps --install` hands out a tree whose input files
(`1_synth.odb`, `1_2_yosys.v`, the structured memories directory, the
blocks' `.lib`/`.lef`) are symlinks into `bazel-out`, read-only. Writing
through one of them (chain 4's regenerated `.place` files: chmod, cp)
edits a bazel action output in place; bazel notices the changed output
metadata on the next build and re-runs the action, and until then the
build tree carries a hand-edited file. That is also a live hypothesis for
take 23's unexplained 15:05 churn (block canonicalise actions re-run with
"action changed since cached execution" and no input change): an earlier
workbench edit through such a link. Rule for the workbench: replace a
linked directory with a real copy before changing anything under it
(chain 4's `memories/` and `2_floorplan.analysis.json` are copies now);
a deploy option that copies instead of linking, or refuses a write
through the link, is the flow-side fix.

## 16. repair_design buffers an array's internal net and meets a dont_touch load

Chain 4 (2026-09-22, 14:22) failed 3_4 after 306 000 nets repaired:
`[WARNING ODB-1211] InsertBufferBeforeLoads: Load pin
.../renameBuffer/rd7_b9_f_o1_g/B is dont_touch. Cannot insert a buffer.`
then `[ERROR RSZ-3006] Failed to insert buffer before loads for net
.../renameBuffer/rd7_b9_k3_o86`. Both cells are RenameBufferFile's own
(read port 7, bit 9: the k3 mux stage's output into the final mux), so
0084's boundary-cell exception does not apply; the net is a read-mux
wire that runs across a 305 um array and the resizer wanted a buffer on
it. The resizer skips a dont_touch *net* outright
(`RepairDesign.cc`, `!resizer_->dontTouch(net)`), so 0084 now marks
every net whose terminals are all the array's own cells; nets that leave
the array (ports, clock) stay repairable, and a violation left inside is
the generator's to fix with a buffer of its own (structured_gen backlog).

Battery gap this exposed: the miniature's files are 30 um wide and never
grow a net the resizer wants to buffer. A real-size scaffold per spec
(RenameBufferFile, IntRegFile, RobEntryFile in a parent of flops, through
place) reproduces the parent's arrays in minutes and is the missing rung
below the parent for anything the resizer does to them.

## 17. Blocks abstracted at place hand the parent their whole clock net as pin capacitance

Chain 4c (2026-09-22, the first parent through CTS with `-no_insertion_delay`
and a measured post-CTS timing): worst slack **-46 601 ps** at the 800 ps
period, `period_min` 47 401 ps, TNS -949 ms. The worst path is one clock
leaf buffer, `clkbuf_leaf_7313_clock`, driving MemBlock's `clock` pin:
145 072 fF, 19 173 ps of delay, 82 061 ps of slew. The abstracts' liberty
files say why: the blocks are abstracted at their place stage, before
their own CTS, so the clock pin's capacitance is the block's entire
unbuffered clock net (MemBlock 145 pF, Frontend 61 pF, VecRegionModule
33 pF, Region_1 7 pF), and every clock-to-output arc inside is timed
through that net. The in2reg and reg2out paths through the blocks show
the same model: `io_outer_l2_flush_en` leaves MemBlock 3 522 ps after
its input with an 11 165 ps transition, so the parent's in2reg and
reg2out groups are thousands of ps negative as well. Chain 3's 49 736
delay buffers (entry 11) were CTS balancing to the insertion delay of
these same unbuffered nets. Fix: abstract the blocks at cts (or later),
so the clock pin is one buffer input and the internal arcs are timed on a
buffered tree; the parent's CTS then has real insertion delays to balance
and `-no_insertion_delay` becomes a choice rather than a bypass. The cost
is the blocks' own CTS legalisation, the miniature's block flows measure
it first (test/planned_parent, abstract_stage). Secondary: the unbuffered
feed-through inside MemBlock says the block's repair_design left it, to
be read from the block's own place log.

## 18. Route-0 on the 60 um channel: no guard trip, a third of the die's capacity, M6 the wall

Chain 4c's route-0 gate ran to its report in 22 min at 44 GB: usage
31 %, total congestion 100.8 M, max horizontal overflow 1 101 and
vertical 176. Per layer: M2 52 % used, max H overflow 225; M4 238; **M6
629**; the vertical layers 117 (M3), 27, 23. The 60 um channel removed
GRT-0228 (entry 13): FastRoute's guard did not trip, and the wall is now
where the abstracts predict it, on M6, the one horizontal layer over the
blocks, with M2 and M4 saturated where the parent's logic is. Wirelength
151 m on a 3.6 x 2.1 mm die. The five-iteration global route that
followed (`-congestion_iterations 5 -allow_congestion`) finished its
initial pass and was killed 3 h in during extra iteration 1 of 5 (entry
in [[xs-grt-matrix-take16]]: maze iterations on this grid are hours
each; the fix is code, not knobs). The flow is flushed to the route and
the route does not converge in hours; the campaign's central number is
unchanged, now on the planned parent with every earlier stopper fixed.

## 19. Chain 4 as run: the night's numbers

| stage | time | peak | note |
|---|---|---|---|
| floorplan (60 um plan) | 19 min | 16 GB | |
| 3_1 global placement | 38 min | 27 GB | 3_3 skipped by ORFS (pins placed in 3_1) |
| 3_4 repair_design | 33 min | 21 GB | 250 197 buffers, 29 998 resizes; first run RSZ-3006 (entry 16), second run a full disk at write_db |
| 3_5 legaliser | 2 h 13 | 40 GB | phase 2 stalled at 46, diamond seated 14 |
| CTS `-no_insertion_delay` | 2 h 19 | 37 GB | 0 delay buffers (chain 3: 49 736); legaliser still all 1 400 iterations, 35 left to the diamond |
| post-CTS timing, one-shot | 10 min | 33 GB | entry 17 |
| route-0 gate | 22 min | 44 GB | entry 18 |
| global route, 5 iterations | killed at 3 h | | in extra iteration 1 |

The CTS legaliser's 2.6 h in chain 3 were not the delay buffers' alone:
without them it still ran every iteration of both phases, on 21 k added
cells. The deterministic handover rule (entry 5's proposal) stands.

## 20. The floorplan deploy tree runs later stages on platform defaults

Chain 4 ran the parent's CTS, both routes and its pin placement from the
floorplan stage's deploy tree, whose `config.mk` is scoped to the
floorplan stage (the fence in docs/local-flow.md). Everything the bazel
flow sets for later stages was therefore the platform default:
`MAX_ROUTING_LAYER` M7 instead of M9, `ROUTING_LAYER_ADJUSTMENT` 0.25,
`PLACE_PINS_ARGS` without the annealer, `IO_PLACER_H/V` defaults,
`PLACE_DENSITY` the platform's. Route-0 on the same CTS checkpoint at M9
takes a fifth off the total congestion (100.8 M -> 81.4 M, worst edge
1 101 -> 971), so the chain 4 numbers in entry 18 are M7 numbers. The
workbench fix is `tmp/take23/stage_env.sh`, sourced by every chain: the
parent's later-stage arguments as exports. The flow-side fix is the
per-stage config as a bazel artefact the workbench can source, which the
fence allows when the arguments are static.

Related, seen when re-installing the tree for take 24: the regenerated
arrays (structured_gen with spare sites) are an input of the parent's
partition synthesis, so `--install` of the floorplan deps re-ran two hours
of synthesis before it reached the floorplan inputs. Copying the previous
tree and dropping the new plan files into it took two minutes and is the
right move when only floorplan inputs changed; the arrays' Verilog was
byte-identical, so the netlist is the same. Whether the synthesis stage
needs the .place and .netlist.json files at all (or only the .v) is a
bazel-orfs question worth a look: it is the difference between a
two-minute and a two-hour turnaround on a generator change.

## 21. Rows removed without a blockage: the legaliser carries every stray cell a millimetre

Take 24, chain 5 (2026-09-23): the plan removed the rows in the blocks'
band (entry 18's pockets and channels) and nothing else. Global
placement ignores rows, so it seated the parent's 4 309 port buffers
next to their ports on the die's bottom edge, in the band, and 624 other
cells with them; `detailed_placement` then sat 25 minutes in
`NegotiationLegalizer::initialSnap` with no output and no end in sight.
initialSnap moves every movable cell whose initial position is not
placeable to the nearest placeable site by an expanding ring search over
sites and rows: for a cell 1 000 um from the nearest row that is tens of
millions of `placeable()` checks, times 4 309. Killed by decision;
`tmp/take24/band_count.tcl` counted the strays in three minutes.

Fix (planner, commit e4dca003): the band is a placement blockage as well,
so the placer stays out, and a 20 um strip of rows stays between the
block row and the die edge for the port buffers.

Hard stops this asked for, on both sides of the fence:
- flow: after global placement, count the movable cells with no row
  under them and refuse above zero (or above a small number with the
  farthest distance printed); seconds, and it names the cause.
- OpenROAD dpl: initialSnap should count the cells with invalid initial
  positions and the farthest nearest-site distance before it searches,
  report both, and refuse (or fall back to a row index) beyond a
  threshold, instead of an unbounded ring walk with no message. A
  synthetic test: a design whose placement leaves a few thousand cells a
  millimetre from any row.
- the miniature did not catch it because its port buffers had rows within
  a few um; the battery needs a case where a block row sits on the die
  edge that carries the ports.

## 22. A block row should be one height, its widths from the areas (planner, for later)

The band of entry 21 exists because the blocks of a row are shaped
independently: each is about square, so their heights differ by up to
330 um and the shorter ones leave pockets under them. Fixing one height H
for the row and taking each width from the area removes the pockets
entirely; what is left of the band is the channels, which have rows
anyway (row cutting only removes what sits under a macro), so a stray
buffer always lands on a site and initialSnap has nothing to search.

| block | pins | today | at H = 950 um | pin side needs |
|---|---|---|---|---|
| Frontend | 3 294 | 955 x 955 | 958 x 950 | 237 um |
| MemBlock | 10 508 | 996 x 996 | 1042 x 950 | 757 um |
| VecRegionModule | 9 253 | 808 x 808 | 684 x 950 | 666 um |
| Region_1 | 5 099 | 665 x 665 | 463 x 950 | 367 um |

The row plus its three 60 um channels is 3 327 um, inside the present
3 624 um die. Pins on the bottom side are not the constraint: with H
fixed both sides of a block are the same length, so the binding side is
whichever carries more pins (MemBlock's top at 6 199, not its bottom at
4 309). The constraint is the block with the most pins per unit area:
VecRegionModule binds at H <= 976 um, and at 950 it has 684 um of side
for 666 um of pins, three percent of headroom. Take H from that block
with a margin (about 880 um) and refuse rather than squeeze. Costs:
Region_1 becomes 463 x 950, aspect 2.05 (cap 3), a different internal
shape to re-measure, and any outline change re-hardens all four blocks.

## 23. Take 24: the floorplan raid halves the route-0 congestion

Chain 5c (2026-09-23), the first raid with the band handled and the
parent's own later-stage arguments in force. Against chain 4c's M9
route-0 on the same design:

| route-0 at M9 | chain 4c | chain 5c |
|---|---|---|
| total congestion | 81 353 428 | 41 781 243 |
| worst horizontal edge | 971 | 426 |
| worst vertical edge | 181 | 120 |
| capacity used | 23.7 % | 20.6 % |
| wirelength | 151.9 m | 143.7 m |
| M6 / M8 worst edge | 460 / 196 | 166 / 35 |

Three changes together: the blocks' band as a soft placement blockage
with the rows kept (entry 21), PLACE_DENSITY 0.5, and
ROUTING_LAYER_ADJUSTMENT 0.18 with M9 actually in force (entry 20; the
0.18 is the value the asap7 tile flows settled on and adds the 8 percent
of resources in the table). The predictions written before launch were
40 to 60 M and 400 to 700; both held.

The stages came down with it: legaliser 2 h 13 -> 39 min (phase 1 stuck
at 6, phase 2 converged at its first iteration), CTS 2 h 19 -> 57 min,
the whole chain floorplan to route-0 in 3 h 45. Post-CTS worst slack
-44 807 ps against -46 601, a 4 percent move, which is all a floorplan
change can do while the abstracts still export an unbuffered clock net
(entry 17).

The gate for a five-iteration route (total under 10 M, no edge over 100)
did not open, as predicted. The worst edges are now M4 at 150 and M6 at
166, the two horizontal layers over the blocks, with M2 at 65: the
parent's own wiring above the block row, which entry 18 already named
and which the ROB glue's fanout-256 nets drive (entry 5). That is a
generator question, not a floorplan one.

## 24. Blocks abstracted at cts: the clock pin is a buffer, the tree is a period deep

Entry 17's fix, made (2026-09-24): the planned blocks are abstracted at
cts, and the flow's place-stage abstract beside it still feeds the
parent's synthesis, floorplan and place. The miniature
(`test/planned_parent`) first, with the same change:

| miniature block | clock pin at place | at cts | insertion delay |
|---|---|---|---|
| BlockA | 125.3 fF | 3.84 fF | 55 ps |
| BlockB | 175.4 fF | 7.15 fF | 69 ps |
| BlockC | 104.4 fF | 4.00 fF | 59 ps |
| BlockD | 83.5 fF | 4.14 fF | 59 ps |

The parent's CTS with insertion-delay balancing went from 7 delay
buffers to 0; with blocks a real tree deep there is nothing to pad. The
blocks' LEFs and the place-stage libs the parent's early stages read are
byte-identical to the place abstracts they replace, so only the parent's
CTS and later see a difference. `clock_pin_test` and
`cts_delay_buffers_test` pin both; same numbers on the batched
`write_timing_model` binary.

The four XSCore blocks, each through its own CTS (`SKIP_CTS_REPAIR_TIMING`,
as the parent):

| block | clock pin at place | at cts | insertion delay | register sinks | depth | block CTS |
|---|---|---|---|---|---|---|
| MemBlock | 145,071 fF | 21.2 fF | 944 ps | 285,964 | 24-27 | 14.7 min, 19.5 GB |
| Frontend | 60,906 fF | 21.2 fF | 871 ps | 123,283 | 23-25 | 16 min, 13.5 GB |
| VecRegionModule | 32,823 fF | 12.6 fF | 799 ps | 65,714 | 20-21 | 4 min, 9.5 GB |
| Region_1 | 7,186 fF | 22.3 fF | 477 ps | 14,460 | 10-11 | 1.4 min, 4.2 GB |

No block legaliser stalled; block CTS costs minutes against the hours of
the parent's. The clock pin fell by 300 to 6,800 times, which removes the
modelling artefact that owned 43,715 of the 45,985 ps.

What it exposes is the next entry's subject: the blocks' own trees are
20-27 levels deep and their insertion delays are 60 to 118 percent of the
800 ps period. With `-no_insertion_delay` the parent clocks its flops that
much earlier than the blocks', so every block-to-parent path loses it and
every parent-to-block path gains it; with balancing on, the parent pads
its own flops by up to 944 ps of delay buffers, entry 11's 49,736 again,
now against a real tree. A commercial flow would put a mesh or a spine
here. Which of the two the parent's `reg2reg` prefers is the measurement
still to make.

The parent was first unmeasurable: `MODULE.bazel` had lost XiangShan
patch `0008-xiangshan-rob-entry-file.patch` from its list while the
parent's STRUCTURED_MEMORIES names `RobEntryFile.regfile`, so synthesis
stopped in `gen_memories`. Listed again, the flattened Verilog is a
remote-cache hit, the one the baseline was built from.

**The parent, measured (2026-09-24, main's tree, cold build on the
batched `write_timing_model` binary):** `reg2reg` worst slack -12 727 ps
at 800 ps, a minimum period of **13 527 ps**, from the baseline's
45 985. The worst path is no longer the clock: it launches in the
parent's ctrlBlock (clock network delay 2 093 ps; the parent's own tree
is 55 levels at its deepest), crosses the parent in 804 ps, 410 of them
on one wire into the pin, and ends at a Frontend input whose library
setup is 12 534 ps to a **falling** clock edge. That is Frontend's own
worst path, the TAGE SRAM bank's clock-gate enable latch, which Frontend
alone measures at 14 114 ps: the top level now sits where the per block
series said it would.

| parent stage | time | peak |
|---|---|---|
| floorplan | ~50 min, 29+ of them in `pdn.tcl` single-threaded | |
| placement | ~80 min | 22 GB when sampled |
| CTS (`-no_insertion_delay`) | 18 min 55 | 47 GB |
| route-0 | 49 min 37 (`global_route`), 74 min the stage | 55.7 GB |

Route-0 against take 24's (entry 23), same floorplan, new clock trees:

| route-0 at M9 | take 24 | blocks at cts |
|---|---|---|
| total congestion | 41,781,243 | 41,923,366 |
| worst horizontal / vertical edge | 426 / 120 | 465 / 125 |
| capacity used | 20.6 % | 20.58 % |
| wirelength | 143.7 m | 144.1 m |
| M6 / M8 worst edge | 166 / 35 | 210 / 111 |

Within a percent, as it should be: the change moves clock trees, not the
floorplan, and the wall is still the horizontal layers over the blocks.
`global_route` took 49 min against take 24's 22; not chased here.

The grt stage then failed after the route, and this is why `XSCore_grt`
has never finished in bazel: with no diode cell on asap7, antenna repair
finds 0 violations and still leaves no route, and the next
`estimate_parasitics -global_routing` stops on EST-0005. The workbench
chains set `SKIP_ANTENNA_REPAIR=1` by hand; the flow never did.

The floorplan's power grid is new: chain 4's whole floorplan stage took
19 min. Not chased here.

`write_timing_model` before and after the batched model (#1078), the
place-stage abstract of each block from the same ODB: MemBlock 399 s
then 489 s, Frontend 289 s then 227 s, Region_1 61 s then 59 s. Not an
A/B: the two ran on different machine loads (two and three concurrent
jobs), so the numbers say only that the batched model is not a clear win
on the largest block; a controlled comparison is a study of its own.

## 25. Frontend at cts and at grt: 28 percent pessimistic, same worst paths

The question (2026-09-25): the blocks are abstracted at `cts`, before the
global-route stage's `repair_design`; how wrong is a block's timing there,
and does the `cts` checkpoint still rank the paths the way a route does?

Method: one odb-debug session on Frontend's `4_cts.odb`, with XiangShan's
`ClockGate` mapped onto the ICG cell and patches 0087 and 0007 (ORFS #4563,
OpenROAD #11525) in. Measured as it stands, then in the same session a
route-0 global route with the block's grt settings (signals M2-M9, clocks
M4-M9, adjustment 0.25, resistance-aware, `-congestion_iterations 0
-allow_congestion`), `estimate_parasitics -global_routing`, `repair_design`,
ORFS's incremental legalisation bracket, and measured again. `repair_timing`
is on neither side: the blocks skip it at `cts`, so the comparison skips it
at `grt`. About 25 minutes for the route and repair.

| Frontend | at `cts` | after route-0 grt + `repair_design` |
|---|---|---|
| `reg2reg` worst slack at 800 ps | -4,217 ps | -2,803 ps |
| minimum period | 5,017 ps | 3,603 ps |
| in2reg / reg2out / in2out | -4,017 / -1,854 / -1,664 | -2,477 / -1,380 / -763 |
| slew-violating pins (worst) | 59,407 (4.3 ns) | 1,159 (548 ps) |
| clock latency launch / capture, setup skew | 1,124 / 847, 269 ps | 813 / 681, 127 ps |
| cells | 1,566,983 | 1,570,694 |

Ranking, top 200 `reg2reg` endpoints: overlap 5/10, 14/20, 25/50, 69/100,
104/200; Spearman 0.59 over the shared endpoints. The worst endpoint is the
same (`bpu/ubtb.t1_hitTargetSame`) and the route's top ten sit at `cts`
ranks 0-16. Route-0 congestion: a worst gcell edge of 30; the congestion
markers stop at 20,000, so their total (126,983) is a lower bound.

Reading. The `cts` checkpoint is 28 percent pessimistic on the block's
period and ranks the worst paths correctly; it degrades further down the
list. The clock tree is not the difference: latency and skew fall only
because the clock nets get global-route parasitics. The pessimism is the
slew the global-route stage's `repair_design` repairs (59 k violating pins
to 1 k). The earlier 14.1 ns at `place` was mostly the behavioural clock
gate's latch, which the ICG mapping removes.

Decision: keep the blocks' abstract at `cts`. Revisit when absolute block
periods drive a decision (budgeting the top level, closing to a target);
`Frontend_grt_probe_grt` is the probe, and the flow's own grt stage with
`repair_timing` is a separate, longer measurement.

## 26. The parent's worst paths are bare wires between blocks

At 473 ps (2026-09-26, `XSTile_grt`, 5,543 ps), the top 3,000 `reg2reg`
endpoints come from 25 startpoints, 19 of them MemBlock pins. The worst
path breaks down like this:

| segment | ps |
|---|---|
| clock to MemBlock's pin | 1,238 |
| MemBlock's clock-to-output arc (its tree and load s3 logic) | 2,251 |
| one net, MemBlock pin to Region_1 pin, fanout 1, 244 fF, slew 6,088 ps | 1,938 |
| Region_1 through (the write-back arbiter) | 419 |
| parent: repeaters and the busy table's decode | ~900 |

Across the 25 distinct paths, wire is 60 percent of the data delay, 17
of them violate the library's 320 ps slew limit (up to 6.2 ns), and the
median path has no parent logic at all: block pin, wire, block pin. The
parent's own nets beside them got their repeaters. The pins of the worst
net are 2.4 mm apart (1,322 by 1,124 um); repeated, that is a few
hundred picoseconds.

The net is not `dont_touch`; it has no violation to repair. The cts
abstracts `write_timing_model` writes carry a capacitance per port and
no `max_transition` or `max_capacitance`, not even a library default
(checked on the miniature's BlockB: none of 353 ports), and the output
arcs are tabled only to 92 fF. A net whose only driver and load are
block ports therefore never shows the parent's `repair_design` a limit.
A commercial ETM or ILM carries the boundary cells' design-rule limits.

Fixed in the model writer: OpenSTA patch 0008, the source of
parallaxsw/OpenSTA#518, gives an input the tightest `max_transition` of
its loads and an output its driver's `max_capacitance`, the cells' own
limits; `LibertyWriter` already writes both. A version that backed the
limits off by the internal wire's slew and load gave some ports 0 and
stopped XSTile's placement on RSZ-0090 and RSZ-0169: estimates are not
facts. A design-wide `set_max_transition` / `set_max_capacitance` in
the parent's SDC checks the same nets without any change to OpenSTA.
`test/planned_parent:drv_limits_test` checks every signal port of the
miniature's abstracts.

Measured (2026-09-27, `XSTile_grt` from source): 5,543 to 5,143 ps. The
old worst path went from -5,070 to -3,615 ps and its net now drives a
repeater; across the distinct worst paths wire fell from 60 to 23
percent of the data delay and slew violations from 17 of 25 paths to 2
of 11. What leads now is repeater chains (36 percent), the long
crossings themselves, and logic (33 percent, 30 FO4 at the median).

Behind it on the same path: the block's own clock-to-output, 2,251 ps,
which is the blocks' synthesis and their unrepaired netlists (entry 25;
`ABC_AREA=1` came in as a turnaround setting and was never flipped), and
the 1.2 ns capture latency on the parent's side (entry 24).

## 27. The worst paths in the Chisel source

The worst `reg2reg` path of each block at its place stage and of the top
level at global route (2026-09-27, 473 ps), read at the source of the
V3 head. Gate levels are a reading, not a measurement. Paths relative to
the archives' `src/main/scala`: `xiangshan/`, `coupledL2/` (xs_cache),
`yunsuan/` (xs_yunsuan).

1. Frontend, `mbtb.t1_startPcVec_0_addr[13]` to a bank's write
   `setIdx_r[6]`: `t1_startPcVec = RegEnable(...)` at
   `xiangshan/frontend/bpu/mbtb/MainBtb.scala:126` drives the write request; the
   end is `MainBtbInternalBank.scala:174`, enabled by
   `writeValid || (flush && wayMask && !conflict)` with `conflict` an
   8-bit set compare and a 16-bit zero detect (`:164-167`). 6 to 8
   levels; one PC bit feeds 4 internal banks of 4 ways. Single cycle.
2. MemBlock, redirect `robIdx` to `loadQueueReplay` vaddr:
   `xiangshan/mem/MemBlock.scala:495` registers the redirect;
   `xiangshan/mem/lsqueue/LoadQueueReplay.scala:356` `needFlush` (a 10-bit age
   compare, `xiangshan/backend/rob/RobBundles.scala:383`), `:821` pop count and
   free-slot mux, `:823` a 7-to-120 one-hot, `:888` the write into
   `Reg(Vec(120, UInt(50.W)))` (`:284`). About 15 levels. Single cycle,
   no timing comment.
3. CoupledL2, `directory/metaAll_s3` to the L1 hint queue:
   `coupledL2/Directory.scala:252`, hit and `Mux1H` at `:271-311`,
   `MainPipe.scala:245-262` into `CustomL1Hint.scala:91-126`, an
   `Arbiter`, a `chisel3.util.Queue` of 16 (flops). 15 to 20 levels.
   `Directory.scala:209` computes the hit in s3 "Cuz SRAM latency is high".
4. VecRegionModule, `Vfma` `isWiden` to `s0ToS1` CSA:
   `xiangshan/backend/fu/wrapper/VFMacWrapper.scala:31`;
   `yunsuan/vector/VectorFMA/VectorFMAS0.scala:40-393`,
   operand muxes, radix-4 Booth (53 bits, 27 partial products), a
   27-to-4 carry-save tree; the end is `VectorFMA.scala:16`. 16 to 20
   levels; stage 0 of a 3-cycle unit.
5. Region_1, FMA `is_fp64_reg0` to `lshift_mask_valid_reg`:
   `yunsuan/fpu/FloatFMA.scala:57` to `:437`, a 107-bit add with carry select
   (`:305-334`), a 110-bit invert (`:354`) and an AND-reduce compare
   (`:433`). About 20 levels; stage 2 of 3.
6. XSTile, `out_toIntRegion_vstdCanAccept_1_0` to `decodeBufBits_7`:
   `xiangshan/backend/vector/VecIssueQueue.scala:503`, through
   `Region.scala:277`, `Backend.scala:286`, `dispatch/Dispatch.scala:634`,
   `PipeGroupConnect.scala:136` and `rename/Rename.scala:114`, to
   `CtrlBlock.scala:511-560`, a priority mux, an adder and an 8-to-1
   index into `Reg(Vec(8, DecodeInUop))`. 20 to 30 levels.
   `CtrlBlock.scala:488` adds the decode buffer "for in.ready better
   timing", and `PipeGroupConnect.scala:134` and `Dispatch.scala:622`
   note the same concern.

None of the six passes through a memory XiangShan builds as SRAM.

## 28. The design is as fast as its slowest part; the parent is one part

The parent's period is its `reg2reg` group at global route. The paths
inside a block live in its abstract and are not in that group. Each block alone
at its place stage, ideal clock (2026-09-27, 473 ps, #1101's tree):
Frontend 6,186 ps, MemBlock 5,527, CoupledL2 2,820, VecRegionModule
2,471, Region_1 1,990, against the parent's 5,143. The design's minimum
period is the largest of these, 6,186 ps, and today it is a block's, not
the parent's. That largest is the KPI; `kpi.py` draws it red, the parent
and each block dashed beneath it.

## 29. The SDC declares no design rule limits

`constraints.sdc` sets `set_max_fanout 32` and no
`set_max_transition` or `set_max_capacitance`. A signoff SDC sets both
for the design. On an unpatched OpenSTA, a model whose ports carry no
limits and a parent with 200 fF on the net between two instances: with
`set_max_transition 0.1985 [current_design]` both model pins report the
0.46 ns slew, with `set_max_capacitance 60.65` the driving pin reports
201 fF. `repair_design` honours SDC limits, so a design-wide limit would
have had the 2.4 mm bare net of entry 26 buffered without patch 0008.
Not measured on XSTile yet.

## 30. What OpenROAD does with limits, and where it stops

- `repair_design` repairs a long wire only with `-max_wire_length`;
  `rsz::check_max_wire_length` is called with `use_default false` for
  it (only `repair_clock_nets` computes a default), and ORFS passes none.
  Buffering on this flow is driven by slew and capacitance limits alone.
- A limit no cell can meet stops `repair_design`: RSZ-0090 (a
  `max_transition` of 1.562 ps, "best achievable 3.691 ps") and RSZ-0169
  (a `max_capacitance` of 0.246 fF). Both came from a version of patch
  0008 that backed port limits off by the block's internal wire and load
  (#1104, closed); the cells' own limits (#1105) meet neither.
- OpenSTA checks a library's `default_max_transition` on driver pins and
  not on input pins; `set_max_transition [current_design]` checks both.
- `write_timing_model`'s output arcs are tabled to 92 fF on asap7; a
  parent load of 244 fF (entry 26) is extrapolated.
- Global route peaked at 55.7 GB on the parent in entry 24. Two XSTile
  variants took it to 112 GB resident and were killed on the 122 GB
  machine: the parent's CTS with
  insertion-delay balancing (`-no_insertion_delay` removed), and entry
  31's first floorplan. The delay buffers of the first were not counted.

## 31. The tile's ports on one edge, and blocks next to their partners

XiangShan's own SoC top (`XSNoCTop` around `XSTileWrap`) makes the tile a
single NoC node: CHI, the interrupts, CLINT time, MSI, the trace port,
the reset vector and the hart id all go to one place. The flow placed
1,099 of the 1,640 ports on the bottom and 540 on the right (trace 375,
CLINT time 65, reset vector 48, the rest a few each).

Pin partners from the parent's synthesis (30,943 block pins): every block
talks mostly to the parent's logic, 60 to 92 percent of its pins.
MemBlock is the hub of the block-to-block traffic (Frontend 1,193,
VecRegionModule about 1,006, CoupledL2 372, Region_1 198); only CoupledL2
talks to the ports (1,118, CHI).

The planner learned a port side and a partner cost, pins times distance
to each partner block and to the parent's logic, within 10 percent of
the smallest die. On `test/planned_parent` it put the four blocks in one
row with the cross-traffic pair side by side (their nets from 150 to
20 um) and every port on the bottom. On XSTile it failed its gate:

| placed XSTile | #1101's floorplan | partner layout |
|---|---|---|
| ports on the bottom | 1,099 of 1,640 | 1,640 of 1,640 |
| 11 worst crossings, pin to pin | 11,749 um | 9,307 um |
| longest crossing | 1,849 um | 2,350 um |
| half-perimeter wirelength | 103.8 m | 128.4 m |
| global route | completes | killed at 112 GB resident |

Frontend's crossings shortened from 1.3-1.5 mm to 0.4-0.5 mm; the parent's
own paths lengthened (the ROB's 986 to 1,600 um, MemBlock into the busy
table 748 to 1,752 um). The region became a 2,552 by 889 um strip, and
the cost models the parent's logic as one point at its centre, which a
strip is not. Today's arrangement with every port on the bottom is the
candidate being measured.

## 32. Synthesis maps for area

`ABC_AREA=1` came in with the first full synthesis as a turnaround
setting, "flip back for the measured run" (727bef1f), and was never
flipped. Region_1 at its place stage: 2,020 ps with the area script,
1,624 ps with the speed script, and 369,873 cells instead of 408,706.
XSTile on PR 0's tree: 5,543 to 5,462 ps, a gain the bare net of entry
26 hid; not yet measured on #1101's.

## 33. Not measured yet

The logic floor and the wire floor of each block and of XSTile, ideal
clock with and without placement parasitics, and the best-effort delay
mapping of each worst cone: the measurements that would say whether any
path's logic alone exceeds 41 FO4 (#1103).

## 34. Which cut on kunminghu-v3: five blocks stay

After the re-plan onto aa6b520 (#1118), a selection by the macro
selection skill's own rule, every macro's period its own KPI. Space
table on the flat RTL, interface bits:

| module | bits | note |
|---|---|---|
| Backend | 7,086 | its four children sum to 42,868: CtrlBlock 13,349, Region 12,315, VecRegionModule 9,908, FltRegionModule 7,296 |
| MemBlock | 10,493 | no narrower cut inside: LsqWrapper 7,257, DCacheWrapper 5,495, three NewLoadUnit 4,743 each |
| Frontend, CoupledL2 | 3,291, 2,810 | 0.86 and 0.82 pins per um of perimeter |
| VecRegionModule, FltRegionModule, MemBlock | | 3.07, 2.74, 2.63 pins per um: past the skill's 2 |

Candidates, each one XSTile build to global route and every macro
measured (parent at grt, blocks alone at place, 473 ps SDC):

| candidate | parent | Frontend | MemBlock | CoupledL2 | Vec | Flt | Backend | grt |
|---|---|---|---|---|---|---|---|---|
| today (five blocks) | 5,188 | 5,681 | 3,741 | 3,464 | 2,301 | 1,826 | | 108 GiB, 37 min, congestion 42,570 |
| today, pins from the regenerated partner dump | 5,661 | 5,681 | 3,730 | 2,848 | 2,664 | 2,372 | | 107 GiB, 35 min, congestion 49,348, wire -7 % |
| Backend hardened whole | 6,866 | 5,756 | 4,728 | 2,848 | | | 9,038 | 54 GiB, 3 min, congestion 759 |
| both regions flattened | | | | | | | | killed at 119 GB resident |
| MemBlock flattened too | | | | | | | | not built |

No candidate qualified (no macro more than 2 percent worse, grt under
115 GB, parent congestion within 10 percent), so the five blocks stay.

- Backend is the narrow cut the architecture drew, and hardening it is
  still wrong: its worst path is the rename buffer's enqueue register
  back to itself, 9,038 ps alone at place, a loop the flat parent closes
  inside 5,188. The tangled core packaged whole spreads, and its own
  loops get long wires. What it buys is the tool cost: the parent routes
  in 3 minutes at half the memory.
- Flattening the regions does not fit the machine: the parent's global
  route passes 119 GB.
- MemBlock flattened would put its generated SRAMs in the parent, where
  the plan does not place them and rtl_macro_placer refuses to run beside
  the parent's FIRM netlist-mode register files (MPL-0050). The regions'
  first build hit the same refusal with their register files, fixed by
  putting those in netlist mode too; SRAMs have no netlist mode.
- Pin order moves a block's own period by up to 30 percent either way.
  With the regenerated partner dump CoupledL2 went from 3,464 to 2,848 ps
  in both builds that used it, while the regions got worse. Per block,
  CoupledL2's new pins are a candidate on their own.
- The block pins' partners are 57 percent the parent's logic, 24 percent
  another block (each connection counted twice), 16 percent unconnected,
  3 percent ports: a hub, not abutment. The planner aims every
  logic-facing pin at one point, the region's centre.
- A block with a generated memory needs an explicit keep list: without
  one ORFS keeps modules by size, and yosys stops with "Missing cost
  information on instanced blackbox FpRegFile".

## 35. Pin order on XSTile: shorter wire, more overflow

Three single-variable pin experiments on today's five blocks (#1120's
baseline, the same tools), each one XSTile build with every macro
measured (parent at grt, blocks alone at place, 473 ps SDC):

| run | parent | Frontend | MemBlock | CoupledL2 | Vec | Flt | wire | congestion |
|---|---|---|---|---|---|---|---|---|
| baseline | 5,188 | 5,681 | 3,741 | 3,464 | 2,301 | 1,826 | 136.2 m | 42,570 |
| partner dump regenerated on aa6b520 | 5,661 | 5,681 | 3,730 | 2,848 | 2,664 | 2,372 | 126.2 m | 49,348 |
| CoupledL2's CHI port pins moved along its outer side, nothing else | 5,205 | 5,681 | 3,741 | 2,848 | 2,301 | 1,826 | 123.9 m | 50,056 |
| logic-facing pins ordered by where their logic is | 5,278 | 5,711 | 3,794 | 3,640 | 2,534 | 1,826 | 113.3 m | 104,731 |

Global route peaked at 106 to 107 GiB in 34 to 35 minutes in every run.

- Every pin order that shortens the parent's wire raises its overflow.
  Putting each logic-facing pin in front of its logic (the planner's
  logic segment was in name order) cut the wire by 17 percent and more
  than doubled the overflow: the wires now meet where the logic is
  dense, which is where the router has the fewest tracks left. At a
  fixed floorplan the pin order trades wire for overflow, and the
  period does not follow the wire.
- CoupledL2's 1,117 CHI port pins at other positions along its outer
  side make CoupledL2 alone 17.8 percent faster (3,464 to 2,848 ps, the
  same in three builds), change no other period, and raise the parent's
  overflow by 17.6 percent. It failed its gate on the overflow bound
  alone (at most 10 percent); whether that bound should hold against a
  per-macro gain with no period regression is an open decision.
- Pin order moves a block's own period by up to 30 percent either way:
  the block's placement follows its pins even when measured alone.
- The macro step's refusal (MPL-0050) beside the plan's netlists is
  fixed in the planner (#1121). The regions' flattened candidate in
  entry 34 got past it before that, by putting its register files in
  netlist mode, and then failed on memory.

Not worth retrying without new data:

- Ordering the logic segment by logic position, as is: +146 percent
  overflow, no macro better.
- A regenerated partner dump for today's five blocks: the parent 9 percent
  and the regions 16 and 30 percent worse.
- Backend hardened whole (entry 34): its own loops at 9,038 ps.
- Flattening a region or MemBlock into the parent on a 122 GB machine
  (entry 34): the parent's global route passes 119 GB.
- A block with a generated memory and no keep list: yosys cannot cost
  the blackbox (entry 34).

## 36. Where global route's time and memory go, and each macro's floor

On the 5,118 ps baseline (0a0228b4), XSTile's global-route stage alone
from its cts checkpoint, sampled every 5 s with timestamped log lines:

| step | s | resident at its end | note |
|---|---|---|---|
| load, liberty, database | 65 | 28 GiB | |
| global_route | 1,224 | 89 GiB | under 2 cores; 942 of its 3,294 CPU-seconds in the kernel |
| estimate_parasitics | 131 | 101 GiB | |
| repair_antennas and check_antennas | 311 | 105 GiB | 0 violations, no diode cell, about 15 cores |
| estimate_parasitics again | 130 | 108.5 GiB | the peak |
| reports and writes | about 100 | | |

- Nothing is returned between steps: the peak is the sum.
- The allocator never gets huge pages: AnonHugePages stayed 0 with the
  host at madvise, 37 million minor faults, 1,861 CPU-seconds in the
  kernel over the stage. Whether THP=always removes them is a host
  setting, not measured.
- In the route, 26.6 percent of samples are Graph2D::insertUsedGrid, a
  std::set<std::pair<int, int>> insert per used edge, and 29 percent
  routeMonotonic. In the antenna phase about 22 percent are linear
  layer lookups (dbTech::findRoutingLayer and its iterator), the
  pattern OpenROAD #11549 fixed in est.

Each macro at its place checkpoint, ideal clock, reg2reg period with the
flow's wire parasitics and with every routing, cut and wire RC at 1e-6
(an RC of 0 is taken as unset by set_layer_rc and set_wire_rc, and the
period does not move):

| macro | with wires | wire RC 1e-6 | wire share | floor in FO4 |
|---|---|---|---|---|
| Frontend | 4,912 | 1,133 | 77 % | 79 |
| MemBlock | 2,725 | 1,094 | 60 % | 76 |
| CoupledL2 | 2,053 | 835 | 59 % | 58 |
| VecRegionModule | 2,375 | 1,136 | 52 % | 79 |
| FltRegionModule | 1,374 | 887 | 35 % | 62 |
| XSTile (parent, at place) | 6,751 | 4,740 | 30 % | 330 |

With timing-driven placement on, the floors are entry 38's.

- Wires are most of every block's period, 77 percent of Frontend's, the
  macro that sets the design's.
- Without wires every block is 58 to 79 FO4, above the 41 FO4 of the
  333 ps goal. That is the mapped netlist with its pin loads, so it
  counts yosys and ABC as well as the RTL; entry 27 read the RTL's worst
  paths at 9 to 45 FO4, and the difference between the two is the next
  measurement that says whether the gap is the RTL's or the mapping's.
- The parent's floor keeps the blocks' timing models, which carry each
  block's own wires; it is not a logic floor.

## 37. Timing-driven placement was off, and ABC's chains do not matter once it is on

A study of Frontend's buffer trees from synthesis to CTS (#1125, a
closed reference; 473 ps SDC, `reg2reg` with placement parasitics and an
ideal clock at place, the README's block measure):

| Frontend at place | period | endpoints over 1,000 ps |
|---|---:|---:|
| the flow before #1128 | 5,118 | 69,636 |
| the flow's own netlist, timing- and routability-driven placement | 2,266 | 50,514 |
| ABC without `buffer -c`, same placement | 2,865 | 55,301 |
| the same, balanced trees built before floorplan | 2,143 | 57,368 |
| the same, OpenROAD's `repair_design -pre_placement` before floorplan | 2,395 | 52,050 |

- The XiangShan flows set `GPL_TIMING_DRIVEN=0` and
  `GPL_ROUTABILITY_DRIVEN=0` for turnaround. ORFS's defaults, back in
  #1128, take the period 56 percent down at twice the place stage's
  time (28 to 56 minutes on Frontend). The KPI after it needs the
  parent rebuilt on a machine with more than 128 GB.
- At synthesis ABC's `buffer -c` builds chains up to 18 buffers deep
  (470 to 690 ps on the worst paths); balanced trees take the endpoints
  over 1,000 ps from 16,382 to 566. None of that survives timing-driven
  placement: the flow's own netlist is the best arm on the endpoint
  count, and the trees built beforehand trade the bulk for the worst
  path. With the clock tree the order holds (+30 to 70 ps).
- ABC gets no delay target: ORFS passes the period as `-D` with a
  script file, which Yosys drops (ORFS #4585).
- `repair_design -pre_placement` on a hierarchical netlist crashed on a
  top-level port with more than `max_fanout` loads (its early sizing
  round took the top module's `dbModNet`); fixed upstream as OpenROAD
  #11590. A profile of its 56 minutes on Frontend puts about 80 percent
  in OpenSTA propagating timing.
- Open: `tools/structured_gen`'s model liberty is a formula. On
  `FtqMetaQueueResolve` it says 358 ps for the read that the array's
  own gates take 3,625 ps over, with its wide nets unbuffered; the
  study's generator changes (buffer trees, pins at their columns, 813
  ps) stay on its branch until a measurement in the parent justifies
  them.

## 38. The floors with timing-driven placement

Entry 36's measurement repeated on the first full build with timing-
and routability-driven placement and RVT, LVT and SLVT from synthesis
(e6c482e3 with #1133 and #1134, the KPI of #1139): each macro at its
place checkpoint, ideal clock, reg2reg period with the flow's wire
parasitics and with every routing, cut and wire RC at 1e-6. FO4 as in
entry 36, 14.4 ps.

| macro | with wires | wire RC 1e-6 | wire share | floor in FO4 | entry 36: with wires, floor |
|---|---|---|---|---|---|
| Frontend | 2,259 | 856 | 62 % | 60 | 4,912, 1,133 |
| CoupledL2 | 2,222 | 767 | 65 % | 53 | 2,053, 835 |
| MemBlock | 2,057 | 906 | 56 % | 63 | 2,725, 1,094 |
| VecRegionModule | 1,247 | 836 | 33 % | 58 | 2,375, 1,136 |
| FltRegionModule | 814 | 667 | 18 % | 46 | 1,374, 887 |
| XSTile (parent, at place) | 10,855 | 2,418 | 78 % | 168 | 6,751, 4,740 |

- Every block's floor fell, by 8 (CoupledL2) to 26 percent, and
  Frontend's period with wires by more than half. Two things changed
  between the runs, placement and the threshold voltages; this does not
  separate them.
- Wire is still more than half of Frontend's, CoupledL2's and
  MemBlock's period.
- The parent at place is 10,855 ps with placement parasitics, twice
  its 5,402 ps at global route, on the same worst path (the int
  region's `pipeToALU0` into `ctrlBlock`). Without wire it is 2,418 ps
  on another path, the int region's `pipeToBJU2` into Frontend's FTQ
  resolve; the blocks' timing models still carry their own wires, so it
  is not a logic floor. Its global route is the most congested yet
  (#1139: 698,703 total, 30.5 percent of the routing resources).

## 39. A delay target for ABC makes Frontend slower

ABC gets no delay target: ORFS passes the SDC period as `abc -D` with a
script file, and Yosys hands `-D` to ABC only through the `{D}`
placeholder of its own scripts (ORFS #4585). The script file came in for
wireload support (b9c1485f9) with `-D` kept beside it, so the loss was
not a decision; upstream #4586 now makes it one and drops `-D`.

The experiment gives ABC the target: a copy of `abc_speed.script` with
`-D <period>` on the commands that take one (`&nf`, `map`, `upsize`,
`dnsize`; `buffer` has none), 473 ps. Frontend at place on main
c8ca8d30, the README's block measure:

| Frontend at place | period | instances | worst `reg2reg` path |
|---|---:|---:|---|
| ABC with no delay target, the flow | 1,541 ps | 1,516,968 | a TAGE SRAM's reset state into `sramResetDone` |
| ABC with a 473 ps target | 1,652 ps | 1,537,751 | the ITLB's hit into the ICache's way lookup |

- The target makes the netlist 1.4 percent larger and the period 7
  percent longer, against a gate of 2 percent better; it is not carried.
  The target, 473 ps, is far below any block's period; why the mapping
  it asks for places worse is not measured.
- The flow's Frontend on this main is 1,541 ps against #1139's 2,259
  ps; the ORFS bump to ecb3cfdeb1ca and the halo-to-channel change came
  between them. The next full KPI run says what the parent and the other
  blocks did.

## 40. The parent's worst paths were global placement's buffer chains

On the KPI tree of #1139 (5,402 ps), a census of the parent's 200 worst
`reg2reg` paths at global route, each split from OpenSTA's JSON path
report into launch and capture clock latency, repeater cells (BUF, INV,
CKINV), other cells, arcs through a block abstract and wire, with the
Manhattan length of its net hops against the distance from its first
point to its last:

| per path, mean of 200 | KPI tree | `GPL_KEEP_OVERFLOW=0` (#1143) |
|---|---:|---:|
| period range | 5,402 to 4,615 ps | 4,226 to 4,105 ps |
| repeaters | 77.6 cells, 1,612 ps | 28.7 cells, 1,188 ps |
| other cells | 1,285 ps | 1,130 ps |
| wire | 902 ps | 393 ps |
| clock skew | 40 ps | 49 ps |
| net hops / first-to-last span | 10.9 mm / 1.65 mm | 2.5 mm / 0.79 mm |

- Repeaters were the largest component of 198 of the 200 paths. On the
  worst, about 90 of its 117 were the rebuffer's `place<N>` BUFx6f
  (`Rebuffer::fullyRebuffer`, called by `findResizeSlacks` from
  timing-driven global placement), one net's chain jumping 50 to 150 um
  back and forth at each hop: the chains were made at the first
  timing-driven iteration, at overflow 0.63, and kept
  (`keep_resize_below_overflow` defaults to 1), and the cells moved
  after.
- On the same checkpoint: placement parasitics give 10,899 ps against the
  route's 5,402, an ideal clock 5,381, and every RC at 1e-6 2,376 (on
  another path). `repair_timing -setup -repair_tns 0 -max_passes 50` on
  the cts checkpoint took 421 s for 6.8 percent, nearly all of it
  threshold-voltage swaps.
- OpenROAD #6165, which made the repair non-virtual, chose 0.3 by its
  experiments; XSTile has two timing-driven iterations (0.63, 0.19), and
  0.3 against 0 is not measured.

The parent, the blocks unchanged:

| parent | reg2reg | global route: congestion, wire, peak |
|---|---:|---|
| KPI tree | 5,402 ps | 698,703, 189.6 m, 100.5 GiB |
| `GPL_KEEP_OVERFLOW=0` (#1143) | 4,226 ps | 76,033, 107.9 m, 88.8 GiB |
| and repair after CTS (#1144) | 3,785 ps | 72,760, 107.9 m, 88.6 GiB |

With #1143 all 200 of the worst paths start at one Frontend output,
`cfVec_2_bits_instr[16]`, and end in CtrlBlock's decode buffer; with
#1144 the worst is `cfVec_1_bits_instr[12]` into CtrlBlock's store set
table (no census of it yet). `SKIP_INCREMENTAL_REPAIR` is the parent's
remaining turnaround setting that changes the netlist.

## 41. Peeling a block's output flops into the parent: no target once the clock trees balance

#1148 (closed, branch `study/peel-boundary-flops` kept) splits a block at
synthesis: the flops that drive its output ports go to the parent, whose
placer can put them anywhere along the crossing. On its miniatures it
pays: a 32-bit crossing 238 to 198 ps; a 2 x 2 multiplier array 881 to
396 ps with ABC retiming, where retiming or peeling alone do not.

On XiangShan, the branch's probes on main + #1150 (the parent's CTS
balancing the blocks' clock trees, 2,976 ps):

| block | outputs registered at the port | output flops that peel without a new core pin |
|---|---:|---:|
| Frontend | 804 of 1,205 | 539 |
| MemBlock | 1,091 of 5,341 | 1,069 |
| CoupledL2 | 642 of 1,464 | 632 |
| VecRegionModule | 742 of 4,921 | 688 |
| FltRegionModule | 1,059 of 3,566 | 21 |

- None of the parent's 1,000 worst `reg2reg` endpoints at global route is
  launched by a peelable flop: 972 start in the parent's own
  `core/backend` logic, 24 at its L2 TileLink buffer into CoupledL2, 4 at
  a MemBlock output that is not a flop. `peel_bound`: 2,976 ps with the
  peel, 2,976 ps now.
- Before #1150 all of the parent's 200 worst paths launched from
  Frontend's `cfVec` output flops, about 1,030 ps of each in Frontend's
  own clock tree: the unbalanced insertion delay, which balancing
  recovered directly.
- Input peeling is not implemented; the parent's worst path now ends at
  CoupledL2's inputs, of which 8 of 1,346 are registered at the port.

Revisit when the parent's own paths are shorter than its block-launched
ones: the branch's three probes give the bound in about an hour of
sessions (`test/peel/README.md`, "The full run on XiangShan").

## 42. The parent's density and die: main's size is the right one

Branch `xiangshan-parent-density-sweep` (draft) lets the parent place
each block at a footprint mocked to placement density 0.6 (`mock_area`
with the block's own liberty, `mock_sources`), holds each block's side,
and gives every part a `_kpi` build target. The question was whether the
blocks' generous outlines made the parent's floorplan pay for density
the blocks have not been tuned to, and what density and die the parent
wants once they do not.

On main + #1157 (memories timed), the parent at global route; the
blocks' own periods are unchanged throughout (2,170 / 1,870 / 1,591 /
1,386 / 900 ps), since only the parent's floorplan moves:

| parent density | die (um) | parent period (ps) | vs main | grt congestion | grt peak |
|---|---|---:|---:|---:|---:|
| main (blocks unmocked) | 2025 x 2666 | 3,330 | | 17.9 % | 93 GB |
| 0.2 | 2025 x 3085 | 3,302 | -0.8 % | 22.2 % | 92 GB |
| 0.3 | 2025 x 2666 | 3,341 | +0.3 % | 21.2 % | 81 GB |
| 0.45 | 2025 x 2386 | 3,766 | +13 % | 29.4 % | 86 GB |
| 0.6 | 2025 x 2247 | 3,537 | +6 % | 32.4 % | 86 GB |

- More area buys nothing: 16 % more die is inside the 2 % gate.
- At main's die (0.3), mocked footprints change the period by nothing and
  raise congestion: the area they free goes to the parent's cell region,
  not to the channels between the blocks.
- Less area costs: 10 % and 16 % smaller dies are 13 % and 6 % slower.
  The two are not monotonic, so one run of the parent carries several
  percent of noise; neither is close to the gate either way.

The parent's period is not in its floorplan area. At zero wire its own
logic is about 10 FO4 a path (entry 44); the rest is repeaters and the
blocks' arcs. Revisit when the blocks' own densities are tuned up: then
their real outlines shrink, and the question is whether the parent's
channels, not its die, need the freed space.

## 43. CoupledL2's detour was the flow's, and the memories were untimed

CoupledL2 at its own global route (473 ps SDC) measured 1,128 ps; most of
it was one buffer tree, SinkC's 514-bit read-register enable, that walked
1,360 um to a sink 155 um from its root (#1146). An ORFS test design of
the same path (ORFS #4599, closed) found 580-711 ps and no detour. One
change at a time from the flow that made it, each at global route:

| flow | change | worst | into SinkC's register | walk / direct |
|---|---|---:|---:|---:|
| bazel-orfs | as built: the plan's annealer, the plan's pins, kept placement repair | 1,128 ps | 1,128 ps | 8.8 |
| bazel-orfs | RTL-MP instead of the annealer | 743 ps | 737 ps | 1.0 |
| bazel-orfs | default pins instead of the plan's | 780 ps | 776 ps | 1.1 |
| bazel-orfs | `GPL_KEEP_OVERFLOW=0` | 1,374 ps | 1,370 ps | 1.1 |
| plain ORFS | CoupledL2 cut out, as in ORFS #4547 | 1,129 ps | 932 ps | 1.0 |
| plain ORFS | CoupledL2 flattened into a mock XSTile | 1,449 ps | 964 ps | 1.0 |

- The detour needs the annealer, the plan's pins and global placement's
  kept repair (entry 40) together; either of the first two alone removes
  it. Plain ORFS never makes it. There was nothing of CoupledL2's to
  reproduce.
- Every bazel-orfs row above, and the XSTile rows below, timed the
  generated memories as black boxes from floorplan on: 0075 scoped
  `AUTO_MEMORIES` to synthesis, and `load.tcl` reads the memories' views
  only while it is set (fixed in #1157). The plain ORFS rows had their
  memories timed. The detour is geometric; the periods are not the
  design's.
- In XSTile on main d4e62b4f, the same change, memories untimed: CoupledL2
  1,321 to 1,008 ps at its place stage, the parent 3,299 to 3,229 ps, its
  worst path in CtrlBlock (`decodeBufValid` to the store set table) in
  both. With the memories timed (#1157, row 9) CoupledL2 with the annealer
  is 1,591 ps; RTL-MP with the memories timed is not measured yet.
- MemBlock, the annealer's other block, fails its own global-route probe
  at pin access (DRT-0073 on an SRAM's clock pin), the off-lattice
  signature.

What it cost to find out, and what to do first next time:

- Take the flow's own machinery out one piece at a time before writing a
  test design: the annealer, the planned pins and a kept-repair setting
  were each a suspect, and three overnight arms named them.
- Check that every stage loads the memories' `.lib` and `.lef`: a period
  read with a memory untimed is a lower bound, whatever the checkpoint.
- A tool failure on an older pin is first checked against OpenROAD
  master: CTS's `repair_timing` upsized a FIRM register-file cell into
  its neighbour (DPL-0033) on the pin before the bump that carries
  OpenROAD #11493 and #11584, which keep a fixed cell's footprint.
- One output base per arm, or measure an arm before the next builds: an
  arm that changes a block writes its stage outputs at the other arm's
  paths, and the other arm's stages then re-run.
- Measure through a deployed `_deps` tree with plain `make`: running an
  `odb_debug` target after a finished build re-ran synthesis. On #1157's
  branch the `_deps` deploy itself re-ran every block from floorplan to
  CTS after a finished build; the cause is not found yet.
- 62 GB with 126 GB of swap runs the parent's 91 GiB global route; a
  peak above physical memory is not a reason to move machines.

#1146 (draft, closed; branch `ideas/coupledl2-full-design` kept) holds the
write-up, with diagrams, in `test/coremark_joule/xstile_mock/README.md`.
It also holds a method and a plan that were not pursued:

- A block is studied inside a mock of its real parent, flattened into it,
  never cut out, so that its boundary is the tile's. A problem counts as
  reproduced when its signature shows at global route, not when a period
  matches.
- CoupledL2's generated Verilog flattened into a mock XSTile, built with
  plain ORFS. Readable SystemVerilog would be written from the Chisel's
  intent and proven equivalent to the generated Verilog module by module
  by LEC. The folder is a small Bazel module that regenerates the Verilog
  and runs that proof, as a certificate, not a tool.

## 44. With the memories timed: the baseline, and the blocks' only timing repair

KPI row 9 (#1158) is the first row with the generated memories timed in
every stage (#1157, entry 43), on main d4e62b4f; the blocks at their own
place stage, the parent at global route:

| part | row 8 (memories untimed) | row 9 (memories timed) |
|---|---:|---:|
| parent, the design's period | 3,860 ps | 3,330 ps |
| Frontend | 1,541 ps | 2,170 ps |
| MemBlock | 2,057 ps | 1,870 ps |
| CoupledL2 | 2,222 ps | 1,591 ps |
| VecRegionModule | 1,247 ps | 1,386 ps |
| FltRegionModule | 814 ps | 900 ps |

The rows are not like for like: between them came #1150 (the parent's
CTS balancing the blocks' trees) and two bumps, and before row 9 the flow
neither reported nor optimized paths through a memory, so a block can
move either way. Parent global route: 17.5 min, 93 GB, 17.9 % congestion.

Two placement-repair settings, measured against row 9:

| change | result |
|---|---|
| parent `GPL_KEEP_OVERFLOW` 0 to 0.3, OpenROAD #6165's choice | place 3 h 50 min against about 2 h; global route at 118 GB with 1 GB free after 34 min, stopped; no period |
| every planned block's `GPL_KEEP_OVERFLOW` 1 to 0, as the parent (#1143) | at place: Frontend 4,234 ps, CoupledL2 2,433, VecRegionModule 2,129, FltRegionModule 900 to 1,539; stopped before the parent |

- 0.3 does not dominate on the parent: it costs time and memory before
  it can show a period, and the parent stays at 0.
- Kept repair is the blocks' only timing repair: `_planned_block` sets
  `SKIP_CTS_REPAIR_TIMING=1`, so dropping global placement's repair
  leaves a block with none. The parent could drop it because it repairs
  after CTS (#1144). Entry 43's CoupledL2 row (1,128 to 1,374 ps at its
  global route) is the same effect. Before removing a repair, list the
  flow's other repairs.
- The next arm follows from that: the blocks repair after CTS. Their
  abstracts are cut at CTS, so it shows in the parent's period, not in a
  block's place-stage number.

Where the parent's period sits, from a census of its 200 worst paths at
zero wire (every RC at 1e-6) on main fd71f5d1, before #1157, so the
blocks' abstracts timed their memories as black boxes; to be re-run:

- 2,039 ps at zero wire against 3,042 ps routed then: about a third of
  the period is wire and its repeaters.
- The parent's own logic is 149 ps a path, about 10 FO4; repeaters 253 ps.
- The launching block's own arc is 968 ps a path on average. MemBlock
  launches 111 of the 200 paths, with 1,711 ps of each inside its
  abstract, most of them `io_mem_to_ooo_ldCancel` into the integer
  region.

So the parent's floor is inside the blocks' boundary paths, not in its
own logic or floorplan (entry 42).

A single run of the parent carries several percent of noise: the density
sweep's 0.45 and 0.6 points (entry 42) are 3,766 and 3,537 ps, the
smaller die faster. An arm within a few percent of the 2 % gate gets a
second run before it counts.

## 45. The wire campaign (#1153), closed: what it would have asked, and what is kept

#1153 (draft, closed; branch `study/xstile-wire-campaign` kept) planned to
test the claim that the parent's period is set by long wires. It had two
levers upstream of routing. Phase 1 was which modules are hardened (arms
A0 to A4), and Phase 2 was global placement density at a fixed floorplan.
Nothing ran. Since it was written:

- The claim is half of the period. At zero wire the parent was 2,039 of
  3,042 ps; most of the rest of a path is inside the blocks' boundary
  arcs (entry 44). Shorter wires bound the gain at about a third.
- The density question was answered at the floorplan's level: more die is
  flat, less is 6 to 13 % slower (entry 42). `PLACE_DENSITY` at a fixed
  die is not measured, and is bounded by the same third.
- "At least 128 GB" was wrong: the parent's global route peaks at 93 GB
  on a 122 GB machine (row 9), and 62 GB with swap runs it (entry 43).
- Its probe and ledger are covered by each part's `_kpi` target and the
  zero-wire census. Phase 1's flattening arms are the queued dissolves,
  and A2's SRAM placement is their harness.

Kept as ideas, not planned:

- **The hub (A5).** Harden Backend whole: it is the architecture's narrow
  cut, 7,086 interface bits against its children's 42,868. Frontend and
  MemBlock stay flat around it, and CoupledL2 stays hard. Entry 44 says
  the parent's floor is in the blocks' boundary paths, MemBlock's above
  all, which is the case a cut with fewer crossings is for. It is gated
  on Backend's boundary timing, then Backend alone at place, then the
  top level (the branch's plan, "Follow-up").
- **Cut at any module boundary, route by abutment** (the branch's plan,
  last section).

## Method notes

- slang `--keep-hierarchy` names every module `<Definition>$<instance
  path>`. Every by-name interface has to say which it means: blackboxes
  are by definition (`--blackboxed-module`, and the imported black box
  has the definition as its cell type; ORFS patch 0081), kept modules are
  resolved by the flow's three-spellings logic, memory specs name
  definitions, yosys `%m` selection breaks on the `$`. When something by
  name goes missing under slang, this is the first thing to check.

- Synthesis-stage numbers are read after `repair_design`, never before;
  on the whole core that means the blocks' and the parent's place stages
  (entry 4), not a flat session.
- Retiming (`SYNTH_RETIME_MODULES`) is applied per module where the idiom
  is present, measured per module on its own synthesis; unverified for
  equivalence by ORFS, so the list stays short and named.
