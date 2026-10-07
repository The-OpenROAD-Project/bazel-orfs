# Measured: riscv32i vs riscv32i-regfile to global route

950 ps clock. Minimum period = period - WNS with global-route parasitics
on `5_1_grt.odb` (`histogram.tcl`); core and standard-cell area without
taps or fill (`area.tcl`). The same scripts for every row.

| configuration | min period | failing | core um2 | std cells um2 |
|---|---|---|---|---|
| **riscv32i, flip-flops (the gate)** | **954** | 79 | **4012** | 1284 |
| riscv32i, flip-flops, CORE_UTILIZATION 45 (control) | 951 | 13 | 5533 | 1273 |
| regfile at PR head 568df695 (AND2/OR2 read tree, folds 2, 45 %) | 998 | 992 | 7573 | 1413 |
| same, array unfixed: no FIRM, no dont_touch, placed and sized freely (control) | 999 | 986 | 7573 | 1411 |
| + AOI22/NAND2/NOR2 read tree (52b09b95..6a699616), folds 2, 45 % | 977 | 934 | 7353 | 1190 |
| + 30-site tiles (e5dcafd8), flat, 62 % (9967f888) | 1003 | 992 | 4466 | 1161 |
| + 30-site tiles, flat, 45 % | 982 | 920 | 6156 | 1116 |
| + 30-site tiles, folds 2, 35 % | 973 | 792 | 8055 | 1170 |
| word groups of 2 (`word-groups.diff`), geometry only | - | - | - | - |
| predecode (`predecode.diff`), flat, 45 % | 1000 | 1002 | 6106 | 1112 |
| dissolved, then unplaced and placed freely (`unplace.tcl`), flat, 62 % | 1012 | 992 | 4466 | 1171 |
| never a macro: the generated netlist in place of `regfile.v` (`never_macro.sh`), 62 % | 994 | 918 | 3770 | 1144 |
| write clock gate per word (`write-gate.diff`), flat, 45 % | **951** | 7 | 5687 | 962 |
| write clock gate, flat, 50 % | 961 | 698 | 5104 | 962 |
| write clock gate, flat, 55 % | 959 | 28 | 4644 | 980 |
| write clock gate, flat, 62 % | MPL-0003 | - | - | - |
| **never a macro + write clock gate, 62 %** | **955** | 69 | **3544** | **973** |

Word groups: tiles 30 -> 26 sites (-12 %), legal, no overflow; under the
15 % gate set for them, so not taken. With 30-site tiles, folds 2 fails
macro placement (MPL-0003) at 40-55 % and places at 35 % and below.

Array density at 62 % flat (`density.tcl`, `fill.tcl`): cells fill 70 %
of the array's 896 um2 box; global placement fills a third of the rest
(85 um2: buffers, the array's own decode, other logic), 184 um2 stays
empty after place.

The write clock gate (2026-10-07) is the first structure at the gate.
One `ICGx1` per word, enabled by its write select, replaces the per-bit
AO22 hold mux: with one write port a flop's D is the write data bit, so
every array endpoint loses the mux, and the array loses 992 AO22s
(standard cells 13 % under the mux version's, 25 % under the flops').
At 45 % it matches the flip-flops at the same utilisation (951, the
control above). As a macro it does not fit riscv32i's 62 %: the smaller
netlist sizes a smaller core, and the 47 x 19 um array, the four
FakeRAMs and their 8 um channels have no tiling (MPL-0003); 55 % is the
smallest core where it places, 959 ps on 4644 um2.

Never a macro is the shape that wins on area: the generated netlist
read in synthesis in place of `regfile.v`, its cells placed, sized and
buffered with the rest. With the write clock gate it is 955 ps, 1 ps
over the flops' 954, on a core 12 % smaller (3544 against 4012 um2)
and 24 % fewer standard-cell um2. The macro's tiling and the dissolve
cost area without buying timing: the free placement of the dissolved
array (`unplace.tcl`) is no faster than the fixed one (1012 against
1003).

Predecode is a negative: its NAND3xp33 and NOR2xp33 select drivers need
three buffers on a flat array's 53 um select line, 1000 against 982.

Every row is one run. The flow is deterministic, so a repeat gives the
same number; a 1 ps difference is within what any change to the
placement moves, so 955 against 954 is parity, not a loss.

## The clock-period campaign (2026-10-07, after the clock gate)

From here on the register file is inlined (ORFS patch 0091,
`AUTO_MEMORIES_MACRO_PLACE` naming nothing) at riscv32i's 62 %, and
every generator change is checked first by `//test/regfile/sim`: the
generated netlist simulated beside riscv32i's `regfile.v`. Gate: better
than the current best by more than 5 ps, core no more than 5 % bigger.

| arm | min period | failing | core um2 | std cells um2 | verdict |
|---|---|---|---|---|---|
| C0: inlined by the flow (0091), clock gate | **955** | 69 | **3544** | **973** | the baseline, the hand-swapped run reproduced |
| C3: predecode | 960 | 313 | 3516 | 983 | negative |
| C1: mux-tree read (`read_style mux_tree`) | 959 | 285 | 3480 | 928 | negative on period, the smallest |
| C2b: AOI22-NAND4-OR4 read tree | 954 | 51 | 3548 | 981 | within noise |
| C2a: AOI22x1, NAND2x1, NOR2x1, AND2x4, OR2x4 | 950 | 1 | 3674 | 1060 | at the gate, 4 % more core: not dominating |
| C4: C2a + C2b | 953 | 15 | 3642 | 1052 | within noise |

C1, why the mux tree loses: each address bit steers its level directly,
and level 1 is 16 cells for each of 32 bits, 512 loads a port; the
resizer drives them through four buffers (BUFx12f, CKINVDCx20, BUFx6f,
BUFx10), 142 ps before the first mux, and read data is ready at 605 ps
against 524 with the one-hot decode, which buffers the same fanout
through logic.

The read path is near its floor: a port's five address bits drive about
a thousand gate inputs whichever structure decodes them, and what is
left is a few levels of the read tree, 10 to 15 ps, at the edge of what
one run resolves. The rest of the period is riscv32i's single-cycle
ALU, data memory and write back.

C5, the clock gate's cost, against the flops at global route
(`clock_cost.tcl`, `hold_cells.tcl`; power at STA's default activity):

| | register file | flops |
|---|---|---|
| hold worst slack | +85.8 ps | +35.7 ps |
| hold-failing endpoints, hold buffers | 0, 0 | 0, 0 |
| clock-tree buffers and inverters | 179 (58.1 um2) | 122 (52.5 um2) |
| clock gates | 31 | 0 |
| power, total | 23.9 mW | 31.4 mW |
| power, clock-tree buffers | 0.53 mW | 2.63 mW |

riscv32i's input delay applies to hold as well as setup (no `-min`),
and its virtual clock carries the real one's latency: inputs arrive
late for hold, and no hold repair runs in either design.
