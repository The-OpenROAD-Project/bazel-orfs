# XiangShan on OpenROAD: the timing inventory

The project's KPI is the minimum clock period at global route, f from
period minus WNS at a slightly negative WNS, on a floorplan that routes.
The target is congruent with a taped-out core: XiangShan's 333 ps on
7 nm is 41.1 fanouts of four, which is 591 ps at global route on the
asap7 library the flow times with, so 473 ps at synthesis, and no
pathologies (`constraints_473ps.sdc`, `period_fo4_test`). Entries up to
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
