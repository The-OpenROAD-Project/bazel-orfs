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

- OpenROAD patch: `dissolve_instance -inst <macro> <file.odb>`. Reads
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

Not yet measured.
