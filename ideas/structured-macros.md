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
| LoadQueueReplay | 120 | 87% | yes | ~9.5 min (PR: 28.9) | 1,469.7 |
| PhysicalStoreQueue | 64 | 85% | yes | 8.6 min (decode_once: 27.2), top 137 s | 1,905.1 |
| VirtualStoreQueue | 128 | 96% | no | ≤ 6 min ¹ (PR: 6.6) | 1,485.0 |
| LoadQueueRAR | 96 | 86% | no | ≤ 6 min ¹ (PR: 4.5) | 997.7 |
| TLBFA / TLBFA_1 | 48 | 99% / 98% | yes | ≤ 6 min ¹ | 285.9 / 349.5 |
| LoadQueueRAW | 56 | 69% | | below the 70% gate | |
| Uncache | 16 | 42% | | below the gate | |
| VirtualLoadQueue | 120 | 7% | | x >= K compares | |

All extracted from the surgered core XSTile's flows read. ¹ The four
side by side in under 6 min.

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
  to 137 s). LoadQueueRAW's and LoadQueueRAR's read cones still differ
  between entries, and stay in the parent.
- **Threshold compares.** VirtualLoadQueue's `entryHitBound` is x >= K,
  which yosys folds differently for each K (a buffer at 2^k - 1, an
  OR reduction elsewhere); a GE/LT form, like the EQ/NE one, would cover
  it, for 1,734 bits.

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

1. **Threshold compares.** VirtualLoadQueue's `entryHitBound` is
   `x >= K`, folded differently by yosys for each K (a buffer at 2^k - 1,
   an OR reduction elsewhere). Add a GE/LT form beside EQ/NE in
   `entries.py` (`_eq_form`) and its decode in `extract.py`; then
   VirtualLoadQueue's coverage (7 % today) and a `_grt_qor`. Test: a
   threshold case in `features_test`.
2. **Read cones that differ between entries.** LoadQueueRAW (69 %) and
   Uncache (42 %) fall back to the write side alone because their read
   cones differ (`best()` in `entries.py`). Find what differs (entries.py
   prints the off-rule entries) and whether a narrower read side is
   uniform. Test: a CAM variant in `features_test`.
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
   toys (`test/array_toys`; the CAM at 32 x 128: CTS 409 against 101 s).
   Settle it on one toy in a dirty lane before any scan.

