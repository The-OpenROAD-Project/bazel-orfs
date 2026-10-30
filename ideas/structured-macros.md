# The big regular structures become generated macros

*Plan, 2026-09-21, for the record in PR #1055.*

*2026-10-06: STRUCTURED_MEMORIES and STRUCTURED_PLACEMENT (ORFS patches
0071, 0078, 0082, 0084) are replaced by AUTO_MEMORIES_REGFILES (ORFS patch
0089 on OpenROAD patch 0010): a register file is a macro through
synthesis and macro placement and dissolves into its cells after it.*

*2026-10-27: `tools/structured_gen` was retired on 2026-10-15 (278cb810);
`generate_ram` with the carried ram patches builds the register files,
and the sections below that name structured_gen describe what it did.
Next is `generate_array`: one spec of row select, cell op and reduction,
`generate_ram` its simplest front end, every structure LEC-checked. It
is taken breadth first, every rung through synthesis, then placement,
then global route.*

![The parent with its generated macros, and the tile structure of one generated array](structured-macros.png)

## Why

Take 21's placed parent, read through odb-debug: 3.85 M cells in a
1.2 x 1.1 mm blob between the four hardened blocks, bins up to 87 %, and
the 18 densest bins owned half by the reorder buffer, a quarter by
dispatch's tables and a quarter by the memory-control tables. The ROB is
256 copies of `RobEntryCell(idx[8:0], in[3618:0]) -> entry[51:0]`: every
entry receives the same 3 619-bit bus and decodes locally, 926 000
broadcast pin-bits and 4 000 cells to hold 52 bits of state. Yosys cannot
share that decode across entries, global placement cannot spread it, CTS
drops its buffers into it, and the legaliser after CTS ran five hours
(negotiation) and past two (diamond) re-seating it.

These are not jobs for general synthesis and placement. A real core of
this class has its reorder buffer, register files, rename and busy tables
and issue-queue arrays as compiled structures. The literature has said so
since the reorder buffer was invented: Smith and Pleszkun (IEEE TC 1988),
Sohi's RUU (1990), the R10000 active list (Yeager, IEEE Micro 1996) are
circular buffers with decoded, indexed updates; Palacharla, Jouppi and
Smith (ISCA 1997) give the wire-delay reason the issue window and the
register file are the structures that set the clock; Rixner et al. (HPCA
2000) and Zyuban and Kogge (ISLPED 1998) the port-count scaling that
makes a many-ported file a macro everywhere.

`tools/structured_gen` already builds XiangShan's six register files that
way: a C++ generator linked against OpenROAD's own database, a `key
value` spec naming the RTL module and its ports, and out come a placed
ODB (every cell FIRM, by construction), a structural Verilog netlist, a
model Liberty and an abstract LEF; the flow runs CTS, global route,
detailed route and the abstract on the ODB unchanged, and swaps the macro
in for the RTL module by name.

## The plan

1. **Generator: entry arrays.** Two new port kinds in the spec and two
   gates in the tile: `set <valid> <idx> <bit>`, a writeback channel that
   decodes a 9-bit index once in the header and sets one flag bit in that
   word; `clear_after <valid> <idx>`, the redirect, one 9-bit comparator
   per word. The 52-bit entry is the word, the six enqueue channels are
   the write ports, commit and walk the read ports. Tiling, decoders,
   banking and views are reused as they are.
2. **RTL: the ROB's array as a module.** A Chisel patch in the XiangShan
   fork extracts the entry array from `Rob` into a module with the
   generator's port shape (payload write ports, flag set ports,
   clear-after, read ports), leaving pointers, commit and exception logic
   in RTL. The update rules per field come from `Rob.scala`; the
   generated array reproduces them exactly.
3. **Correctness: one-off equivalence.** The generated netlist and the
   extracted RTL module have the same state bits (one flop per entry
   bit, same reset), so the check is combinational equivalence under a
   register correspondence: a logic equivalence check between the RTL
   module and the generated structural Verilog, run once per generator or
   RTL change, plus the study's CoreMark simulation as the end-to-end
   check.
4. **Flow: the macros in the parent.** `STRUCTURED_MEMORIES` in the
   planned parent for the ROB array, `IntRegFile` and `RenameBufferFile`
   (the plan variant had dropped them; they are flops in the blob today).
   The parent's plan re-derived from its measured cells (about 1.5 M
   after the arrays leave) at density 0.5, with the partner pin segments
   and an 80 um channel floor.
5. **Then the next arrays, by the same measure**, cell area and port
   shape: dispatch's busy tables and rename tables (flag matrices and
   small register files), the memory-control tables, the LSQ's queue
   payloads inside MemBlock, and, as a third tile kind, the issue-queue
   entries' CAM match.

## What it costs and returns

| step | effort | returns |
|---|---|---|
| 1 generator ports | a day | ROB array as a macro: 1.04 M cells out of the parent, the broadcast gone |
| 2 Chisel patch | half a day, plus the read of `Rob.scala` | the module the flow swaps by name |
| 3 equivalence | hours once the netlists exist | the correctness argument, reusable per change |
| 4 parent take | one flow day | the first global route of a parent whose clock tree is small and even |
| 5 next arrays | one to two days each | the parent shrinks toward control and muxes |

## Rules

- A structure goes to the generator when it is regular (words x bits,
  ports), large (100 k cells or more), and flop-dense; the tangled
  control logic stays synthesised.
- The RTL patch extracts, it does not redesign: the same state, the same
  update rules, a module boundary where the generator's ports are.
- Every generated macro is equivalence-checked against the module it
  replaces before a take uses it.

## Progress

- **2026-09-21, step 1 and 2 as one patch.** The ROB's entry payload did
  not need a new generator: the fields written once at enqueue are a
  plain multi-port register file, so XiangShan patch 0008 extracts them
  into `RobEntryFile`, a `utils.RegVecFile` (8 write ports at the allocate
  pointers, 16 read ports for the eight banks' two lines, 352 x 21 bits),
  and `RobEntryFile.regfile` hands it to `structured_gen` as it stands.
  The cell keeps its read-modify-write state and a shared bus of a few
  dozen bits per enqueue port instead of the whole uop. The planned
  flows now harden the generated register files of every module they
  keep (the parent: `IntRegFile`, `RenameBufferFile`, `RobEntryFile`;
  Frontend: the Ftq queues), and the plan's macro placement marks the
  planned blocks FIRM and lets `rtl_macro_placer` place the parent's own
  macros around them. Take 22 runs it. The `set` and `clear_after` ports
  of the plan's step 1 are still wanted, for the flag matrices (the ROB's
  remaining state, the busy tables) in step 5.
- **2026-09-21, placed netlists.** A macro is right only for a terminal
  block at an edge with a narrow, registered interface; an array in the
  middle of the logic as a macro costs the parent its cross-boundary
  placement, clock tree and routing and a wall of pins to route around.
  ORFS patch 0078 adds `mode netlist` to a STRUCTURED_MEMORIES spec: the
  module stays blackboxed in synthesis (no abc on it), the generator's
  structural netlist is linked when the design loads, and at floorplan
  its placed cells are dropped FIRM onto the parent's rows where
  `STRUCTURED_PLACEMENT` says, site- and row-snapped with the row
  orientation matched; tapcell, global placement and the legaliser treat
  them as fixed, the clock tree and the router as ordinary cells. Proven
  on `test/structured_netlist` (a 16 x 8 two-port file inside a parent:
  1 440 cells FIRM at the planned corner, parent cells placed around).
  The planner emits `netlists.txt`, the parent's arrays in a row along
  the top of its logic region. The table's macro/netlist column is now:
  the four planned blocks are macros; every generated array is a placed
  netlist inside its block or the parent.

## Generator depth backlog (2026-09-21)

What take 23's first synthesis on slang still spent ABC time on, per
module, and whether a generator should own it. Two thirds of every
session below is one single-threaded ABC call.

| module | synth | what ABC chews | generator |
|---|---|---|---|
| Rob | 995 s | 6 417 nine-bit pointer compares, 352-wide and/or trees, 16 x 352-way one-hot muxes over the 352 `RobEntryCell` (30 bits each); the 21-bit file is generated (xiangshan-timing.md entry 9) | flag matrix for the cells' state; pointer-window read (eight consecutive entries at a rotating pointer); fork patch 0009 shares the decode |
| Region_1 (fp) | 727 s, 8.4 GB | `DataPath_1`, `BypassNetwork_6` wide muxes; four fp issue queues | bypass network as a generated mux tile; issue queues as CAM tile plus payload |
| PhysicalStoreQueue | > 5 min | 64 `SqEntryCell` x 249 bits (vaddr 50, paddrHigh 36, data 128, mask); `ForwardModule` 3 086 lines and no registers, the store-to-load compare of a query address against all 64 entries with byte masks; `DeqModule` window read | payload file + address CAM + window read; the RTL keeps the pointers |
| SqForwardPipe | 447 s | the age-ordered 64-entry x 16-byte forward select over 685 register bits | the same CAM and priority tile |
| LoadQueueReplay | 430 s | per-entry replay state and selection | flag matrix + payload file |
| MissQueue, L2TLBWrapper | 227 s each | entry match, TLB compare | CAM tile |
| Rename | 217 s | RAT with snapshots | snapshot-copy file |
| Region (int) | 185 s | `DataPath`, `BypassNetwork` over the generated IntRegFile | bypass mux tile |
| SSIT | 176 s | a table | plain extraction |
| IBuffer, Sbuffer | not reached (15 k and 39 k lines) | instruction buffer; store buffer with masked writes | plain extraction; masked-write port |
| VecRegionModule's four IQs | not reached (26 k lines each) | vector issue queues | CAM tile + payload |
| Bpu 547 s+, Ifu 328 s, DecodeStage 180 s, NewCSR 179 s, DCacheWrapper 241 s, Tage 208 s | | predictor, fetch and predecode, decoders, CSRs, cache control, table logic around blackboxed SRAMs | nothing for it: real logic |

**Identical cells synthesised once per instance.** Under slang's
`--keep-hierarchy` every instance of `RobEntryCell` is its own module,
`RobEntryCell$...robEntryCells_N`, and because `RobEntryCell` is a kept
module all 352 copies keep their hierarchy inside Rob's partition, where
`abc` runs on each one in turn ("Extracting gate netlist of module
RobEntryCell$...robEntryCells_225 ... 226 ... 227"): the same 2 683-cell
module through ABC 352 times. That is a large share of Rob's 995 s, and
the same happens to every per-entry cell that is a kept module
(`SqEntryCell` x 64 in the store queue). A generated entry array is the
fix that removes the synthesis entirely; until a cell is generated, the
flow should synthesise one elaboration of an identical, parameterless
cell and instantiate it 352 times, which neither slang nor yosys does
today (yosys has `uniquify`, not its inverse).

The store queue is the clearest case for going deeper: one payload file
with 64 entries, one address CAM feeding the forward select, one window
read, and the RTL keeps only the pointers, the way Rob should end up.
Order of work is execution optimisation only; all of the "generator"
rows are wanted before the parent is asked to route.

## Correctness: kepler-formal, wired in bazel

yosys equivalence (eqy) does not scale to a 224 x 64 file with 21 ports
and is not the tool. The check per generated structure is kepler-formal
(github keplertech/kepler-formal), LEC on Verilog with a liberty library,
which requires the same sequential boundaries and the same names for
sequential instances and top terminals in both designs. So
`structured_gen` names its flops after the RTL registers it replaces,
bit by bit, and the check runs per module against the RTL side mapped
to the same liberty cells. Wire it up here in bazel, as a dev dependency
on the latest upstream (the tool is being fixed rapidly; never pin an old
release or a local checkout). Not started.

## yosys's memory passes on per-entry-updated arrays (2026-10-27)

An array whose every entry is updated in place (a counter, a flag, a
ROB entry), written as an unpacked array, becomes a `$mem_v2` with one
write port per entry, and `opt_mem_priority` orders every pair of them:
on `test/array_toys`'s counter, `memory -nomap` took 1.0 s at 64 x 8,
7.5 s at 128 x 8 and 74 s at 256 x 8, 96 % of it in that pass. Written
as a packed vector the same counter is one `$dff` per word and no
memory. So structures are recognised on the packed form, and a rewrite
of packed register vectors to unpacked arrays ahead of yosys is not
used. Ports at distinct constant addresses never collide; a yosys fix
that skips them is a carried-patch candidate.

## The front end: entries found and extracted (2026-10-28)

`test/coremark_joule/designs/asap7/xiangshan/arrays` finds a module's
entries and makes them one cell, instanced per entry, with no
per-design code: yosys JSON after `proc` (`proc_json.py`); entries are
word i of arrays of equal length (`entries.py`); each entry's private
cone is walked to a structural signature, with constants, shared-bit
references and comparison forms (x == K, x != K over up to 12 bits of
one net) decided across entries (the same, affine in the entry, or
affine in a bank's number or the entry's place in its bank); duplicate
cells are merged; arrays whose structure differs between entries stay
inline. `extract.py` writes the template entry as `<Module>Entry`
and decodes index comparisons once in the parent. `check.py` proves
each extraction: registers and blackboxes as cut points, a yosys
miter, ABC `iprove`, a negative control (one register's D-mux swapped)
that must differ, and the decode-once lemma `(1 << x)[i] == (x == i)`.

| Block | Entries | Coverage | Read side | To global route | Period (ps) |
|---|---|---|---|---|---|
| Rob | 352 | 81% | no | 23.5 min (surgered + hand generator: ~33) | 1,913.9 (1,712.8) |
| LoadQueueReplay | 120 | 87% | yes | ~9.5 min (PR: 28.9) | 1,469.7 ³ |
| PhysicalStoreQueue | 64 | 85% | yes | 8.6 min (decode_once: 27.2), top 137 s | 1,905.1 |
| VirtualStoreQueue | 128 | 96% | no | ≤ 6 min ¹ (PR: 6.6) | 1,485.0 |
| LoadQueueRAR | 96 | 87% | no | ≤ 6 min ¹ (PR: 4.5) | 997.7 ³ |
| TLBFA / TLBFA_1 | 48 | 99% / 98% | yes | ≤ 6 min ¹ | 285.9 / 349.5 |
| LoadQueueRAW | 56 | 69% | yes, the common part | below the 70% gate | |
| Uncache | 16 | 92% | yes | 4.0 min ² (PR: 3.4) | 1,255.7 |
| VirtualLoadQueue | 120 | 96% (7% without thresholds) | no | 3.2 min ² (PR: 3.2) | 963.9 |

All extracted from the surgered core XSTile's flows read. ¹ The four
side by side in under 6 min. ² Alone, from the Bazel profile: synthesis
76 s (the top 61 s), floorplan through global route 114 s (grt 63 s);
the extraction itself 22 s more. Single run. Uncache: synthesis 90 s
(the top 77 s), floorplan through global route 149 s (place 55 s, grt
78 s); slower than the carve. ³ Each gained one array with firtool's
vector names (LoadQueueRAR's REG, LoadQueueReplay's
l2HintLastBeatUnblock); on slang and the fold, side by side, single
runs: LoadQueueRAR 969.8 ps (was 961.1), synthesis 75 s, floorplan
through global route 152 s; LoadQueueReplay 1,435.1 ps (was 1,289.9),
synthesis 313 s, floorplan through global route 521 s.

Every extraction is proven twice, with the index kept and decoded, each
with its negative control (`<top>_check_test`, `<top>_control_test`). The Rob's decoded
form, 80 comparisons in eight per-bank decoders, proves directly in
97 min (5,839 s) on the current extraction.
Every flow is the block's
with setup repair off (XSTile's ~2,000 ps), no pin access, and
floorplan's repair_timing skipped.

What is not covered yet:

- **The read side** is in the cell where entries agree on it: each
  entry's cone from its registers to the reductions across entries
  (PhysicalStoreQueue's forwarding compares: its top's synthesis 978 s
  to 137 s). Where the read cones differ between entries, the part of
  them every entry has, by signature, goes in the cell
  (`Entries._common_read`): LoadQueueRAW's priority select within each
  bank of eight reads entry j's select bit through j inverters of its
  own, and the two select bits are common. LoadQueueRAR's and the Rob's
  read cones have no common part that follows one rule; they stay in the
  parent.
- **Firtool's vector names and per-port arrays** (2026-10-29): a vector
  of registers is `x`, `x_1`, `x_2`, ..., word 0 without a number, and an
  array of k·N words may be k arrays of the group of N
  (`entries.plan`, word p·N + i or i·k + p). Uncache's 42 % was not its
  read side, which every entry agreed on, but its per-entry pipeline
  registers: `f1_fwdDataCandidates_r` (16 words, word 0 unnumbered) and
  `f1_ptagMatches_r` (48 words: 16 entries by three load ports); with
  them, 92 %.
- **Threshold compares** are covered (2026-10-29): VirtualLoadQueue's
  `entryHitBound` is `x >= i + 1` and `x < i + 1`, which firtool folds
  differently for each i (`x > 2`, `|x[6:2]`, `x[6]` alone, `x == 0`).
  `entries.py` reads them as GE/LT forms on a net where some entry has a
  threshold that is no `x == K`, a lone top bit through a buffer it puts
  in front of it; `extract.py` decodes `x >= i + o` once as bit
  `i + o - 1` of `(1 << x) - 1`. Tried only where the plain reading
  leaves entries off the rule: PhysicalStoreQueue's dequeue pointer is
  compared both with the entry's number and against a threshold, and
  read as thresholds its entries 0 and 63 (`x == 0` is `x < 1`) fell
  off; the six blocks above extract byte-identically.

### What the flow alone buys (2026-10-28)

`flow_only/` builds Bpu and VecRegionModule from their RTL as it is,
with the knobs above (setup repair at and after CTS off, floorplan's
repair off, no pin access, route-0 global route) and the die from
utilization rather than the carve's plan. Side by side, 39.1 min to
global route; floorplan through global route took 15.2 min (Bpu) and
27.2 min (VecRegionModule), CTS 2.3 and 3.0 min against the carve's 15.0
and 21.2. With setup repair off the periods were 3,495.9 ps (Bpu) and
2,355.3 ps (VecRegionModule), over XSTile's ~2,000 ps. With repair at CTS
and global route aimed at 2,000 ps instead of the SDC's 473
(`SETUP_SLACK_MARGIN` 473 - 2,000), side by side in 38 min:
VecRegionModule 2,012.4 ps, Bpu 3,175.5 ps. Repair does not close Bpu.

## QoR inventory (2026-10-29)

Every extraction against the module as it is: arrays
`<Block>_grt_qor` (B, the extraction) and `<Block>_rtl_grt_qor` (A,
the same proc JSON written back as Verilog: no entry cell, nothing
folded), every other flow setting shared by construction. Single runs
on one machine, each pair side by side; PhysicalStoreQueue and
LoadQueueReplay alone with their pair in a 10 GB memory scope (swap in
use), so compare seconds within a row, not across rows. Synthesis is
canonicalisation, synthesis and the synth ODB from the Bazel profile
(the entry cell's partition runs beside the top); floorplan through
global route is the tool time in the stages' logs. Cells and area are
the standard cells at global route (CORE masters, no tap or fill), what
setup repair would have added included (it is off here; CTS buffers and
place's repair_design are in).

| Block | Arm | synth s | floorplan s | place s | CTS s | grt s | total min | period at grt ps | stdcells | stdcell area µm² |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PhysicalStoreQueue ⁴ | A: RTL | 1,909.2 | 26.1 | 327.9 | 30.9 | 156.9 | 40.85 | 1,582.9 | 252,148 | 32,126.6 |
| | B: extracted | 327.2 | 23.7 | 324.3 | 40.8 | 156.4 | 14.54 | 1,905.1 | 256,511 | 31,409.7 |
| LoadQueueReplay | A: RTL | 1,504.8 | 49.5 | 496.1 | 33.4 | 160.0 | 37.40 | 1,664.5 | 368,658 | 45,109.3 |
| | B: extracted | 432.4 | 35.8 | 549.4 | 49.5 | 274.7 | 22.36 | 1,289.9 | 388,365 | 45,860.8 |
| VirtualStoreQueue ⁴ | A: RTL | 260.4 | 5.5 | 58.7 | 7.5 | 30.3 | 6.04 | 1,014.1 | 62,041 | 7,605.0 |
| | B: extracted | 78.3 | 5.7 | 68.0 | 7.6 | 38.9 | 3.31 | 1,485.0 | 64,645 | 7,813.4 |
| LoadQueueRAR | A: RTL | 266.8 | 6.0 | 58.7 | 5.0 | 58.8 | 6.59 | 902.0 | 53,430 | 7,024.2 |
| | B: extracted | 85.8 | 11.5 | 70.0 | 6.3 | 106.4 | 4.67 | 961.1 | 64,639 | 8,169.5 |
| TLBFA | A: RTL | 75.6 | 6.4 | 46.9 | 4.6 | 28.0 | 2.69 | 439.0 | 47,411 | 6,578.3 |
| | B: extracted | 34.3 | 6.6 | 49.0 | 4.8 | 36.9 | 2.19 | 272.0 | 49,982 | 6,648.4 |
| TLBFA_1 ⁴ | A: RTL | 166.0 | 16.6 | 136.2 | 7.0 | 31.4 | 5.95 | 460.8 | 83,636 | 10,707.2 |
| | B: extracted | 44.2 | 10.5 | 81.6 | 11.4 | 36.0 | 3.06 | 349.5 | 97,630 | 11,759.7 |
| VirtualLoadQueue | A: RTL | 173.5 | 5.1 | 34.9 | 3.2 | 94.9 | 5.19 | 962.5 | 38,203 | 4,267.1 |
| | B: extracted | 83.9 | 5.0 | 41.4 | 4.2 | 70.4 | 3.41 | 963.9 | 42,521 | 4,945.0 |
| Uncache ⁵ | A: RTL | 115.1 | 13.3 | 49.0 | 5.4 | 17.2 | 3.33 | 1,020.3 | 56,458 | 7,449.8 |
| | B: extracted | 81.8 | 6.6 | 68.4 | 5.4 | 84.0 | 4.10 | 1,255.7 | 71,343 | 8,545.2 |
| Rob ⁶ | A: RTL | 969.3 | 365.3 | 1,078.6 | 37.2 | 147.9 | 43.30 | 2,038.9 | 341,506 | 40,836.6 |
| | B: extracted | 408.7 | 143.9 | 1,925.8 | 43.3 | 925.1 | 57.45 | 1,759.3 | 432,737 | 48,740.8 |

⁴ On yosys's frontend in both arms (`YOSYS_FRONTEND`). ⁵ The study
extraction (`--firtool-vectors`, off by default; #1430), its RTL arm
built with the same settings. ⁶ `rob_array:RobEntries_rtl_grt_qor`
against `rob_array:RobEntries_grt_qor`: the Rob's own flow (timing- and
routability-driven global placement, its register files macros), the
arms one after the other, alone on the machine.

| Block | A total min | B total min | A period ps | B period ps | verdict | reason for a loss, measured |
|---|---:|---:|---:|---:|---|---|
| PhysicalStoreQueue | 40.85 | 14.54 | 1,582.9 | 1,905.1 | trades | the forwarding query reaches the 64 entry cells through fanout-32 buffers (slew 287 ps), compares inside, and the select comes back out: arrival 2,164 ps against 1,833 |
| LoadQueueReplay | 37.40 | 22.36 | 1,664.5 | 1,289.9 | dominates | |
| VirtualStoreQueue | 6.04 | 3.31 | 1,014.1 | 1,485.0 | trades | the dequeue pointer reaches the 128 entry cells through ten levels of fanout buffers before the entry's logic: arrival 1,624 ps against 1,142 |
| LoadQueueRAR | 6.59 | 4.67 | 902.0 | 961.1 | dominates | period +6.5 %, within the resolution |
| TLBFA | 2.69 | 2.19 | 439.0 | 272.0 | dominates | |
| TLBFA_1 | 5.95 | 3.06 | 460.8 | 349.5 | dominates | |
| VirtualLoadQueue | 5.19 | 3.41 | 962.5 | 963.9 | dominates | |
| Rob | 43.30 | 57.45 | 2,038.9 | 1,759.3 | trades | 27 % more cells (432,737 against 341,506): routability-driven global placement needs 21 passes against 7 (1,591 against 757 s), and global route takes 835 s where the RTL arm stops at congestion after 79 s |
| Uncache | 3.33 | 4.10 | 1,020.3 | 1,255.7 | study only | 27 % more cells: the 435-bit read side mapped inside the kept entry cell, nothing optimised across its boundary; global route 84 against 17 s |

The verdict: B dominates when it is no worse on both, a time within
15 % or a period within 10 % counting as no worse (the flow is
deterministic, but one register per entry moved into LoadQueueReplay's
cell moved its period 11 %: placement, the same gates on the worst
path); it trades when it is better on one and worse on the other;
otherwise it loses and stays a study. Every extraction cuts synthesis
(PhysicalStoreQueue 1,909 to 327 s). The Rob trades the other way:
14 % better period, but its 352 kept cells add 27 % cells and its
placement and route take longer than synthesis saves.
PhysicalStoreQueue and VirtualStoreQueue lose period where a shared
operand is broadcast into every entry cell. To win
there, the broadcast has to stop being one net into N kept cells: the
comparison against it decoded once in the block where it can be
(VirtualStoreQueue's dequeue pointer), or the cell's boundary placed so
the buffer tree is the compare's own.

### The toys (2026-10-29)

`test/array_toys`, the generated arm against yosys's, depth 32. Dirty
lanes from synthesis through global route on one machine, each kind's
two arms side by side stage by stage; seconds are the step logs summed,
period is 300 ps minus the worst slack at global route, cells and area
the standard cells without taps. Single runs; agematrix is 32 entries
(a 32 x 32 age matrix and 32 valid bits). Verdict as above.

| Kind | Size | Generator | gen total s | yosys total s | gen period ps | yosys period ps | gen stdcells | yosys stdcells | verdict | reason for a loss, measured |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| counter | 32x8 | structgen | 25 | 60 | 295 | 344 | 2,847 | 2,600 | dominates | |
| counter | 32x128 | structgen | 492 | 599 | 347 | 481 | 46,054 | 39,474 | dominates | arms in different pairs |
| agematrix | 32 | structgen | 59 | 64 | 266 | 299 | 5,678 | 4,934 | dominates | |
| flags | 32x128 | structgen | 505 | 656 | 496 | 394 | 60,435 | 30,769 | trades | `head_q` to array flop: a 5-level OR2 thermometer prefix and the flush-window select fanned out to 128 bits through a buffer chain, 28 cells and 481 ps against 20 and 390; 2.0x the cells |
| flags | 32x8 | structgen | 92 | 66 | 425 | 335 | 4,887 | 2,572 | loses | the same path, 23 cells and 414 ps against yosys's adder compare, 14 and 328; repair at CTS 20 s and grt 41 s against 0 and 21 |
| cam | 32x8 | structgen | 24 | 20 | 334 | 271 | 1,689 | 1,458 | loses | priority encoder: 5 OR2 prefix levels, an inverter, a NOR3/NAND3/NOR2 tree, 19 cells and 323 ps against OR4/OR5, 10 and 268 |
| cam | 32x128 | structgen | 252 | 276 | 448 | 431 | 20,770 | 21,438 | dominates (period +4 %, inside 10 %; time a tie) | 17 ps left: the match tree's single-fanout NAND3/NOR3 at xp33 drive 4-5 fF of wire: 20 of the 26 ps |
| rf1r1w | 32x8 | generate_ram | 12 | 13 | 236 | 231 | 1,612 | 1,501 | dominates (period +2 %, inside 10 %; time a tie) | 5 ps left: the data paths are equal, 225 ps from the address register in both; the 5 ps are the capture flop's setup, a rising D against yosys's falling one. 7 % more cells, 1.4 % more area |
| rf1r1w | 32x128 | generate_ram | 89 | 144 | 300 | 310 | 19,655 | 22,149 | dominates | |
| rf4r2w | 32x8 | generate_ram | 17 | 18 | 270 | 253 | 3,622 | 3,363 | dominates (period +7 %, inside 10 %; time a tie) | 17 ps left: a write: the two ports' enable OR, then 0163's group buffer, which in an 8-bit word serves the whole word (21 ps), the hold inverter and the hold mux: 264 ps from the address register against 249 |
| rf4r2w | 32x128 | generate_ram | 567 | 521 | 372 | 357 | 40,404 | 53,096 | dominates (period +4 %, time +9 %, both inside the tie; 24 % fewer cells) | 15 ps left: a write: a port's enable into every bit's data mux, which 0163 does not group, drives 128 pins; repair_design chains BUFx4f/BUFx6f at fanout 33 and 50 and the data mux takes 114 ps; repair at CTS 93 s against 60, grt 314 against 234 |

The generate_ram rows are re-measured (2026-10-30) with carried
patches 0163 (a word's write enable and hold per eight bits) and 0164
(address literals per eight words, read selects per eight bits) on
main's OpenROAD (bf0feec with 0156 and 0159), the same method, each
kind's two arms side by side again (load 1-13). Before them, at 2026-10-29,
generate_ram left its word selects unbuffered and its decoder inverters
at the smallest size: rf1r1w 32x8 was 288 ps against 231, rf1r1w 32x128
476 s against 264 and 344 ps against 310, rf4r2w 32x8 299 ps against 253,
rf4r2w 32x128 1,103 s against 978 and 453 ps against 357. With 0163 and
0164 every register-file row dominates by the rule above; what is left of
their period is measured in the table: a multi-port word's per-port write
enable into the data mux, ungrouped, and 0163's group buffer where a word
is one group. structgen's remaining losses are depth and sizing in the
CAM's priority encoder (32x8) and the flags' flush-window select.

## XSTile uses the arrays (2026-10-29)

MemBlock and the parent read `arrays:xiangshan_extracted`, the surgered
core with the six blocks inside them swapped for their extractions
(`XS_EXTRACTED`, `substitute.py`); the other parts read the surgered
core. What it took, each a trap for the next such change:

- **Slang makes one module per instance**, `RobEntry$<path>`. The fold
  (`fold_entries.tcl`) renames one copy to the bare name and retypes
  every instance onto it. It must run as `SYNTH_CANONICALIZE_TCL`, before
  the canonical checkpoint: bazel-orfs's partitioned synthesis resolves a
  kept module to its first copy in that checkpoint
  (`synth_partition.sh`), and a fold after it (as
  `SYNTH_POST_HIERARCHY_SCRIPTS`) disagrees with the partition about
  which module is the cell. Folded, each entry cell is one partition:
  MemBlock's 1,353 modules become 902, its synthesis 535 s.
- **An extraction absorbs what it flattens.** A kept module inside an
  extracted block (SqForwardPipe in PhysicalStoreQueue, RobEntryCell in
  the Rob) no longer exists, and partitioned synthesis stops on a keep
  list that names it; `XS_EXTRACTED`'s `absorbed` takes them off.
- **Flattening renames instance paths.** The plan's macro placement names
  the register file inside RenameBuffer `rob/rab/renameBuffer`; with
  RenameBuffer flattened into the extracted Rob it became
  `rab.renameBuffer` and would not be found. The Rob's extraction keeps
  RenameBuffer and VTypeBuffer as blackboxes. Before extracting a block,
  check `plan/place_macros.tcl` for paths through it.
- **Slang and the fold are not free for every block.** On the array
  flows, global-route periods (ps, yosys frontend against slang):
  PhysicalStoreQueue 1,905.1 against 2,304.9, VirtualStoreQueue 1,485.0
  against 1,849.1, TLBFA_1 349.5 against 364.7; better on slang:
  LoadQueueRAR 997.7 to 961.1, LoadQueueReplay 1,469.7 to 1,289.9, TLBFA
  285.9 to 272.0, the Rob 1,913.9 to 1,781.7 (its buffers also kept). Single runs; the worse three
  stay on yosys's frontend (`YOSYS_FRONTEND`).
- **A survey of the five macros' modules** (entries.py on each candidate
  a text scan and the synthesis-time backlog named) found no other large
  array the front end fits: RenameTable_1 and PrefetchReqBuffer pass the
  70 % bar at ~2,000 register bits; SSIT 51 %, Sbuffer 49 %, MissQueue
  36 %; the busy tables, PMP and SyncDataModuleTemplate 0 %; the age
  detectors are triangular, one row length per array. BankedDataArray, Sc
  and PtwCache were not read (the survey's input step, not the front end).
- **Under Bazel, Python tests run with `PYTHONSAFEPATH`**: a script run as
  a child does not see the modules beside it; `features_test` and
  `regress.py` pass `PYTHONPATH`.

The debugging loop for a front-end change is `arrays:regress` (index-kept
proof and control, the decoded extraction's Verilog read back, the direct
proof with `--direct`) and `arrays:localise` (which output groups differ
when a proof says NOT equivalent); `arrays/README.md`.

## Tasks, for agents (2026-10-29)

Rules for all of them, from the human: no giant rebuilds (XSTile,
MemBlock, the parent: other jobs own large-scale rebuilding and timing);
baseline numbers do not matter, the arrays' own speed-up does; test small
(`features_test`, a block's `_grt_qor`, at most three small flows side by
side); proofs (the miter) are polish for now, the long ones wait.

1. **Threshold compares.** Done: VirtualLoadQueue 7 % to 96 %, in
   `TOPS` with its `_grt_qor` (963.9 ps, 3.2 min synthesis to global
   route, as in the carve). Its extraction proven with the index kept,
   its control, and decoded directly (118 s).
2. **Read cones that differ between entries.** Done: the common part of
   the read side goes in the cell (LoadQueueRAW: its two select bits, the
   per-bank priority inverters left in the block), and Uncache's
   uncovered registers turned out to be firtool's vector names and
   per-port arrays, now read (42 % to 92 %, in `TOPS`, 1,255.7 ps).
   LoadQueueRAW stays at 69 % (8,134 of 11,687 bits): the rest is
   pipeline and select-tree registers, no entries; it is not in `TOPS`.
3. **Why slang and the fold cost PhysicalStoreQueue and
   VirtualStoreQueue period** (above). Compare the two synthesised
   netlists' entry cells and the worst paths at global route (odb-debug's
   `worst_paths`) before changing anything; a block's flow is minutes.
4. **The Rob's decoded extraction, proven directly** since it kept its
   buffers (`arrays:regress -- ... Rob ... --direct`, about 100 min;
   the index-kept proof and control passed). Polish: when the machine is
   otherwise idle.
5. **Bpu's 3,175.5 ps** with repair aimed at 2,000 ps (`flow_only`).
   Not an array: find whether it is logic or placement first
   (`repair-headroom` skill), on the flow_only flow.
6. **Generated arrays slower than yosys in CTS and global route** on the
   toys (`test/array_toys`). Settled on the CAM at 32 x 128 (2026-10-29);
   both arms run with the same settings. The clock trees were alike
   (4,364 sinks, 271 against 235 buffers); CTS's time was its
   `repair_timing`. Two causes, both in structgen's netlist:
   - *No buffering.* A word's decoded write enable drove 256 pins (128
     muxes and 128 copies of its complement) from one AND2;
     repair_design chained BUFx2s at fanout 25-50, and 3,055 of 4,096
     array flops missed 300 ps by up to 168 ps (yosys's ABC netlist: buffer
     trees at fanout 10, 1,072 flops, 28 ps). structgen now buffers every
     net above 32 sinks, shares each net's complement and sizes cells by
     fanout, as `test/rob_toy/rob_gen.py` already did.
   - *Depth of the cone that cannot close.* With the array paths closed,
     repair ground on the match into the priority encoder (`idx`, `hit`,
     about 430 ps in both arms): 1,161 iterations at 107 ms each, each
     move retimed over a 16.7k-cell cone of 2-input gates. With those
     endpoints set false as a diagnostic, CTS took 15-17 s in either arm:
     the whole gap was that cone. The trees are now 3-input NAND/NOR by
     turns, and a compare reads the flop's QN directly (an XOR in place of
     inverter and XNOR).
   Lanes side by side, single runs on a shared machine, seconds
   (before → after; yosys): CTS 126 → 65; 40-43. grt 149 → 106; 116-121.
   Period at grt 422 → 448 ps; yosys 431. The worst path at grt is
   `idx[1]` in both netlists; of its 25.7 ps, 20.2 are in the word's
   128-bit match tree (148.2 → 168.4 ps), the encoder within 2.3 ps.
   structgen sizes by fanout alone, so the tree's single-fanout NAND3 and
   NOR3 are xp33 driving 4-5 fF of wire; repair put a BUFx3 after three
   of them, 32-38 ps a level against 15-21 ps for the old AND2x2. Repair
   did more on the new path, not less: 4 buffers inserted and 6 cells
   resized, against 2 and 2.
   Counter 32 x 128: CTS 121 → 70, grt 288 → 244, period 388 → 347 ps.
   The hermetic build reproduces the grt WNS of each lane exactly. Tried
   and dropped: 3-input gates one size up (CTS 104 s, period worse).
   Open: sizing the tree's gates for their wire load, not their fanout,
   is the lever for the 26 ps; the priority encoder's depth (prefix OR2s,
   a polarity inverter at each tree's end) is where the rest of CTS's
   time is; flags, agematrix and the larger sizes are not re-measured.

