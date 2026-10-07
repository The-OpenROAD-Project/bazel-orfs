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

Word groups: tiles 30 -> 26 sites (-12 %), legal, no overflow; under the
15 % gate set for them, so not taken. With 30-site tiles, folds 2 fails
macro placement (MPL-0003) at 40-55 % and places at 35 % and below.

Array density at 62 % flat (`density.tcl`, `fill.tcl`): cells fill 70 %
of the array's 896 um2 box; global placement fills a third of the rest
(85 um2: buffers, the array's own decode, other logic), 184 um2 stays
empty after place.

Not measured (stopped): predecode (`predecode.diff`) at flat 45 %; the
array dissolved and then left unplaced at 62 %; the register file never
a macro (its generated netlist in place of `regfile.v` in riscv32i).
