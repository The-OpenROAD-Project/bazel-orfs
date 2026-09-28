# XiangShan Frontend's worst path against the FO4 in its Chisel

A deep dive into one path: Frontend's worst `reg2reg` path,
`bpu/mbtb.t1_startPcVec_0_addr[13]` to a main-BTB internal bank's
write-buffer `setIdx_r[6]`. Frontend alone at its place stage is
6,186 ps, **430 FO4** at the library's 14.37 ps. Read at the source it
is 6 to 8 gate levels, 9 to 12 FO4 plus a fanout tree
(`xiangshan-timing.md`, entry 27). The question is how far down the
path can be ground against the FO4 inherent in the Chisel, and what the
remainder is made of.

Out of scope: Frontend's and every other block's build settings. Knobs
are turned inside the analogue below only, and what wins is reported,
not applied. Every iteration is seconds to minutes; a long run is an
overnight job, not a step here.

## The path in the RTL

At the V3 head, paths relative to `src/main/scala/xiangshan/frontend/bpu/mbtb/`:

- `MainBtb.scala:126`: `t1_startPcVec = RegEnable(...)` drives each align
  bank's `write.req.startPc`.
- `MainBtbAlignBank.scala:213-216`: `getSetIndex`, `getInternalBankIndex`
  into `UIntToOH`, `internalBankMask`; `:248`: `writeEntry.req.valid =
  t1_fire && t1_entryNeedWrite && internalBankMask(i)`.
- `MainBtbInternalBank.scala:162-189`: `conflict`, an 8-bit `setIdx`
  equality and a 16-bit `tag === 0`; per way `valid = writeValid ||
  (flushValid && !conflict)` is the enable of the `setIdx_r` and `entry`
  `RegEnable`s, in 4 ways by 4 internal banks by 2 align banks.

A cycle at 41 FO4 is 591 ps at global route, leaving about 38 FO4 of
logic after clock-to-output and setup.

## 1. An analogue, built up from the RTL

From the generated Verilog, through slang and `constraints_473ps.sdc`,
each rung a manual flow that runs in seconds to minutes and adds one
piece of reality:

| rung | contents | measures |
|---|---|---|
| R0 | the cone in `MainBtbInternalBank`, SRAM arrays blackboxed, synthesis only | the floor: gate levels and ideal-wire delay, delay and area scripts |
| R1 | R0 through place with `repair_design` | real loads and slews |
| R2 | `MainBtbAlignBank`: 4 internal banks and the replacer | the PC bit's and the enables' fanout |
| R3 | `MainBtb`: 2 align banks and the start register | the whole path on a compact die |
| R4 | R3 with the SRAM arrays as area placeholders, the die at MainBtb's share of Frontend | Frontend's wire distances |

Each rung: the path stage by stage (cell, arc, slew, load, fanout, wire
versus cell), bucketed into logic at FO4, fanout and load, slew, wire and
repeaters. The rung where the measurement leaves the floor names the
mechanism; if R4 falls short of 430 FO4, the missing piece is the next
rung. R0 also names the cone exactly, which the seam in step 3 needs.

## 2. The grind with yosys and OpenROAD

On the rung that shows the mechanism, one concern at a time: ABC delay
against area script and the cone's depth; `repair_design`,
`repair_timing` on the cone, buffer trees for the enables and the PC
bit, `set_max_fanout`; timing-driven placement and where the start
register sits; tool code where no knob gets there, carried here as a
patch. No RTL edits, no multicycle or false-path exceptions, no added
registers.

## 3. A module seam in the Chisel

The cone is not a module: it runs from `MainBtb` through the align bank
into the internal bank, interleaved with SRAMs, a queue and counters.
There is nothing to generate, prove or dissolve until it is one.

`test/coremark_joule/xiangshan/patches/0010-xiangshan-mbtb-write-seam.patch`,
in the `xiangshan` archive's patch list beside 0002 to 0008 (the archive
is a dev dependency; no consumer sees it). Candidate:
`MainBtbWriteBufferEnq`, one per internal bank, holding `conflict`, the
ways' `valid` and the flops feeding `bufWrite`; it grows to the align
bank's write-request logic if R0's cone starts there. The start register
stays outside. Same registers, same write conditions, same timing.

LEC of the unpatched against the patched module, both mapped to asap7
and flattened, the moved flops renamed to drop the seam's instance
prefix (kepler-formal needs identical sequential names). A bazel test;
a mutant must fail.

## 4. A generator, checked by LEC

That the path is not limited by what yosys and OpenROAD placement make:

- kepler-formal wired into bazel from its latest upstream commit (it
  ships bazel files), in place of the mock for this use.
- A domain specification in `.json`, extracted from the seam's Chisel by
  Claude: register groups with their RTL names bit by bit, the compares,
  the enables and their fanout, the placement intent (compare and enable
  trees in columns beside the flops they drive, buffer trees sized by
  construction).
- A JSON spec kind in `tools/structured_gen` that writes a placed
  `.odb`, a `.v` for LEC and `.lef`/`.lib` for macro placement.
- An LEC bazel test: the yosys-mapped seam module against the generated
  `.v`, and a mutant that must fail. An error in the specification is
  caught by the check, not by a review of gates.

## 5. ADDITIONAL_ODB_FILES: generated macros dissolved into the parent

Macro placement places the generated block by its LEF; then the macro is
dissolved: its ODB's cells and nets replace the instance at the placed
location and orientation. No boundary is left: the parent's tapcells,
power grid, clock tree, repair and router run across the region and
timing is flat, while the generated cells arrive placed and FIRM.

Carried patch 0078 already drops generated cells FIRM onto the parent's
rows before tapcell and PDN, snapped with row parity, but from Verilog
linked at load, a DEF and `STRUCTURED_PLACEMENT`, not from the macro
placer. OpenROAD refuses a second `read_db` on a populated database
(ORD-47), and its multi-database support (3DBlox chip instances) is for
stacking chiplets, not for flattening one design into another.

- OpenROAD patch (planned; not needed, see Results: odb Tcl reads the
  second database): `dissolve_instance -inst <macro> <file.odb>`. Reads
  the file into a scratch `dbDatabase`; tech and masters must match by
  name; copies instances as `<inst>/<name>` with the instance's
  transform, snapped to the parent's site and row grid with row parity
  (shift reported, under a site and a row), FIRM and `dont_touch` as
  0084 does; internal nets as `<inst>/<net>`, block terminals onto the
  parent nets at the macro's pins, supplies onto the parent's; deletes
  the macro; drops the generator's power grid and wires. Flat netlists
  only.
- ORFS patch: `ADDITIONAL_ODB_FILES` beside `ADDITIONAL_LEFS` and
  `ADDITIONAL_LIBS`, dissolved at the end of macro placement, before
  tapcell and PDN.
- bazel-orfs plumbing on `orfs_flow`.

Both patches ship to consumers, so both are no-ops unless
`ADDITIONAL_ODB_FILES` is set. Both are carried here, not upstreamed,
and retire on a bump onto an upstream that has the mechanism.

A test of tens of seconds, of intended behaviour: a tiny generated block
in a tiny parent through macro place, dissolve, place, cts, grt and
route; cell counts, no macro or halo left, every generated cell FIRM on
a row at its transformed place for R0, MX, MY and R180, power grid,
tapcells and global route over the region, detailed route clean, and
LEC of the dissolved parent's netlist against the parent with the
synthesised module.

## 6. Measured on the analogue

R3 and R4 with the seam modules three ways: synthesised flat after the
grind, generated as a hard macro, generated and dissolved. The path in
FO4 against R0's floor, runtime per stage, worst slack, wirelength and
route DRCs.

## Results

### The analogue and the grind (2026-09-28)

`test/coremark_joule/mbtb_path`: MainBtb's 18 modules from the generated
Verilog, the Frontend block's synthesis settings (`ABC_AREA=1`,
`AUTO_MEMORIES=1`, the ICG map), `constraints_473ps.sdc`, the 40 SRAM
arrays as FakeRAM macros. Every number is the path's arrival plus setup
against an ideal clock, in FO4 at 14.37 ps; `path.tcl`, `focus.tcl` and
`split.tcl` beside the BUILD are the session code. Since MainBtb holds
both ends, R0 to R3 collapsed into one design: R0 is it at synthesis,
R1 placed.

| step | what | ps | FO4 |
|---|---|---:|---:|
| R0 | synthesis, ideal wires: 10 cells | 253 | 17.6 |
| R1 | placed on a 321 um die, `repair_design` | 654 | 45.5 |
| R4 | the same on a 640 um die | 693 | 48.2 |
| R4 | the same on Frontend's 955 um die | 644 | 44.8 |
| R5 | R1 with Frontend's hierarchy: `SYNTH_HIERARCHICAL`, `OPENROAD_HIERARCHICAL`, `WriteBuffer_4` kept; 16 cells | 698 | 48.6 |
| G1 | R1, `repair_timing -setup` on the block | 654 | 45.5 |
| G2 | R1, `repair_timing` with every other endpoint a false path | 499 | 34.7 |
| G3 | G2, start flop `DFFHQNx1` to x3, `AND5x1` to x2 by hand | 410 | 28.5 |
| G4 | R1, the start flop's 13 other loads behind one `BUFx4` | 586 | 40.8 |
| G6 | G4, then G2 and G3 | 383 | 26.6 |

Reading:

- The Chisel is congruent: 10 cells, 213 ps after clock-to-output, 14.9
  FO4 of logic against 9 to 12 read, the rest the enable's fanout.
- MainBtb alone does not reproduce Frontend's 430 FO4, on any die, with
  or without Frontend's hierarchy: 45 to 49 FO4. The macro placer packs
  MainBtb into a 250 by 380 um corner even of the 955 um die; the
  endpoints sit within 260 um of the start. The other 380 FO4 are in
  Frontend's context, which this analogue does not have. `Frontend_place`
  is a cache miss from synthesis on; its path breakdown is an overnight
  build.
- Placement costs 2.6 times the floor, and the tools leave most of it:
  - `repair_timing` never reaches the path while worse endpoints exist
    (G1): MainBtb's own worst `reg2reg` is 2,258 ps, inside
    `WriteBuffer_4`'s entry array, and a pass on the block took 4 min.
  - Given the path alone (G2, 5 to 8 min on 210 k cells), it resizes
    and rebuffers the enable's fanout tree but leaves the start flop at
    x1 with 14 loads (221 ps slew, 122 ps clock-to-output against 31.5 at
    synthesis) and an `AND5x1` into 25 fF.
  - The flop's loads split behind a buffer, the flop and the AND5
    upsized: 26.6 FO4, 1.5 times the floor. What is left is load and
    slew on the placed nets.
- Two tool faults, not chased: `insert_buffer -net -load_pins` stops
  OpenROAD with signal 11 on this design within 25 s of loading
  (reproducible; `split.tcl` does the same through the odb API), and one
  signal 11 after `find_timing_paths` and `sta::worst_slack -max`, not
  reproduced.
- MainBtb's synthesis alone takes 8.5 min, too slow for the loop; not
  yet broken down.

### Inside Frontend (2026-09-28)

`Frontend_place` built from source at this branch's first commit (46
min), the path read in an odb-debug session with placement parasitics,
ideal clock, 473 ps:

| step | what | ps | FO4 |
|---|---|---:|---:|
| F0 | Frontend placed | 979 | 68.1 |
| F1 | F0, the start flop to x3 and its other loads split | 982 | 68.3 |
| F2 | F0, `repair_timing` with every other endpoint a false path (21 min) | 879 | 61.1 |

- Frontend's worst `reg2reg` today is not this path:
  `utage/MicroTageTable.wbuffer.a1_chosenFirstMask`, 5,132 ps (357 FO4).
  The README's 6,186 ps and its mbtb path were measured on an earlier
  tree; this study does not touch the README.
- The path is 68 FO4, not 430: 23 FO4 more than MainBtb alone, and the
  difference is wire. Six repeaters (`BUFx16f`, the resizer's wire and
  slew repair) take 340 ps. The path zig-zags across the block: start at
  x = 523 um, the compare's XOR at 800, the second AND5 back at 597, then
  736, 797, the endpoints at 874: some 750 um of wire for endpoints 360 um
  from the start. The compare's gates sit where their other inputs pull
  them; Frontend places without timing (`GPL_TIMING_DRIVEN=0`).
- The start flop is already buffered in Frontend, so F1 gains nothing;
  the resizer on the path alone takes 7 FO4 off the enable tree and
  leaves the wire, which no sizing moves.

### The seam, the generator, and the dissolve (steps 3 to 5)

- Seam: XiangShan patch 0010 moves `MainBtbInternalBank.scala:162-189`
  into `MainBtbWriteBufferEnq`, one per internal bank. R0's cone lies
  inside it: the path's inverter drives `internalBanks_*.valid_*`, and
  before it are the set compare and the enable terms; only the start flop
  is outside. Elaboration takes 7 min.
- LEC: kepler-formal at its latest upstream commit (f025fa2f) does not
  build here, as a dependency or as its own root: its oneTBB builds with
  CMake through `rules_foreign_cc`, which reaches the host `/usr/include`
  under the zero-sysroot LLVM and fails on `bits/timesize.h`. One hour
  spent, as budgeted; `lec/` is left as it was. **The generated netlist
  is unproven by LEC.** What stands in for it, and says so: a random
  co-simulation, `tools/structured_gen/cosim_tb.py` under `yosys sim`
  with the cells' liberty functions, 2,000 cycles, stimulus biased so the
  set compare matches on half of them and the tag is zero on a quarter
  (`conflict` fires on 131 cycles), and a mutant (the compare's XNOR made
  an XOR) that must fail. It checks the generated seam against its RTL,
  the dissolved parent against its RTL in five placements, and, as a
  one-off, the unpatched `MainBtbInternalBank` against the patched one
  (the seam changes nothing; a zero-tag mutant fails).
- Generator: `tools/structured_gen` reads a JSON domain specification,
  `test/coremark_joule/mbtb_path/MainBtbWriteBufferEnq.json`, written
  from the Chisel: 735 cells, placed by construction, ports equal to the
  RTL module's.
- Dissolve: ORFS patch 0088, `ADDITIONAL_ODB_FILES`. No OpenROAD patch
  was needed: `ord::read_db` refuses a second database (ORD-0047), but
  odb's own `odb::read_db` reads one into a fresh `dbDatabase`, and the
  copy is odb Tcl. Two things only the parent showed:
  - odb's `cut_rows` leaves a row holding a fixed cell uncut (ODB-0386),
    and a row runs the whole core: dissolved cells before tapcell kept
    every row they touched uncut under the SRAMs, and PDN (PDN-0008) and
    the legaliser (DPL-0033) refused. The dissolve now removes the
    generated macros, cuts rows around the ones that stay with the
    platform's own arguments, then places the cells.
  - The macro placer abuts macro outlines; the generator leaves a 2 um
    empty margin inside its outline so a neighbour's power-grid halo
    falls on no row holding a cell.
  - dont_touch follows STRUCTURED_MEMORIES' netlists: interior
    combinational cells and nets, not the flops (CTS rewires their clock
    pins, CTS-0137) and not the cells on a port's net.
- Tests, all manual, tens of seconds each once built:
  `MainBtbWriteBufferEnq_cosim_test` and its mutant, `dissolve_check_test`
  (no macro left, 735 cells FIRM, on rows of their own orientation,
  interior cells dont_touch, `check_placement` clean, in the placer's
  orientation and forced R0, MX, MY, R180), and
  `dissolve_parent_{base,R0,MX,MY,R180}_cosim_test` with a mutant. The
  test parent routes.

### Three ways on the analogue (step 6)

MainBtb with the seam on the compact die, placement parasitics:

| variant | placed | resizer on the path alone |
|---|---:|---:|
| synthesised flat | 593 ps, 41.2 FO4 | 482 ps, 33.6 FO4 |
| generated, dissolved | 636 ps, 44.3 FO4 | 627 ps, 43.7 FO4 |
| generated, hard macro | not measured | |

- Inside the dissolved block, from its input pin to the register, the
  path is 268 ps, **18.7 FO4**: the generated structure is at the Chisel
  floor (R0, 17.6 FO4 for the whole path, start flop included).
- Outside it, the parent takes 367 ps to bring the start bit to the
  block: the flop, an inverter, then one `BUFx2` net of fanout 32 and
  78 fF spread over the eight blocks, which the macro placer put 100 to
  250 um apart; about 200 ps is that one net's wire. `repair_timing`,
  given the path alone, does not rebuffer it.
- The hard-macro variant needs a macro with power pins: the generated
  LEF has none, and the parent's power grid refuses it (PDN-0233). That
  is the generated block's own flow (grid, route, abstract), not built.

Where that leaves the path: the Chisel is 17.6 FO4; a generated
structure holds its part at that; what the tools leave is delivery. In
Frontend it is a zig-zag through the compare's gates, 340 ps of
repeaters; in the dissolved analogue it is one unbuffered broadcast of
the start bit to eight blocks. Both are placement: of the compare's
gates in the first, of the start register and its fanout tree relative
to the blocks in the second. The next lever is the parent's: the start
register's fanout as a planned tree, and the blocks placed around it.
