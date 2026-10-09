# What did not make riscv32i's register file faster

*Measured 2026-10-06..07 on riscv32i, for the record of the closed PR
#1187, whose branch (`regfile/auto-memories`) has the scripts, the
generator diffs and every row in `test/regfile/campaign/results.md`.*

generate_regfile's riscv32i register file reached parity with the
flip-flops it replaces: 955 against 954 ps at a 950 ps clock, on a 12 %
smaller core. Two changes did it: a clock gate per word on the write
side (`write_style clock_gate`) and inlining, with the generated netlist
in the module's place rather than a macro (`AUTO_MEMORIES_MACRO_PLACE`
naming nothing). ORFS patch 0091's AutoMemories.md has that result. This
page keeps what else was tried and why it lost, so it is not tried again
without a new reason.

## How it was measured

riscv32i against riscv32i-regfile, both to global route, 950 ps clock.
Minimum period is the clock period minus WNS, with global-route
parasitics. Core and standard-cell area exclude taps and fill. Every row
is one run of a deterministic flow, and a change of a few picoseconds is
inside what any placement change moves: 955 against 954 is parity. After
the clock gate, the gate for a change was better than the best by more
than 5 ps, on a core no more than 5 % bigger.

## The negatives

| tried | min period | against | why it lost |
|---|---:|---:|---|
| predecode: NAND3/NOR2 select drivers in front of the one-hot decode | 1,000 ps; then 960 | 982; then 955 | Its small drivers need three buffers on a flat array's 53 um select line. Retried after the clock gate, still slower. |
| mux-tree read (an experimental `read_style`, not kept) | 959 ps | 955 | Each address bit steers a level directly: level 1 is 16 cells for each of 32 bits, 512 loads per port. The resizer drives them through four buffers, 142 ps before the first mux; read data is ready at 605 ps against 524 with the one-hot decode, which buffers the same fanout through logic. The smallest arm, 5 % fewer cell um2. |
| AOI22-NAND4-OR4 read tree | 954 ps | 955 | Within noise. |
| stronger cells (AOI22x1, NAND2x1, NOR2x1, AND2x4, OR2x4) | 950 ps | 955 | At the gate on period but 4 % more core: not dominating. With the tree above, 953 ps on 3 % more. |
| word groups of two (shared tiles) | not run | | Tiles 30 to 26 sites, 12 %, under the 15 % set to justify a flow run. |
| two-way bit folds (as a macro) | 973 ps at 35 % | 982 flat at 45 %, same tiles | A few ps faster only on a core twice the flops' (8,055 against 4,012 um2); it fails macro placement (MPL-0003) at 40-55 %. |
| the array placed freely: no FIRM, no dont_touch | 999; 1,012 ps | 998; 1,003 | No faster than the fixed array, both before and after the dissolve: the generator's placement is not what costs time. |
| a macro at all | 959 ps at 55 % | 955 inlined | Where it places it is close, but on a bigger core: the macro's tiling, halo and channels against the FakeRAMs cost area, and at riscv32i's 62 % it does not place (MPL-0003). |

## What sets the period now

A read port's five address bits drive about a thousand gate inputs
whichever structure decodes them; what is left of the read path is a few
levels of the read tree, 10 to 15 ps, at the edge of what one run
resolves. The rest of the period is riscv32i's single-cycle ALU, data
memory and write back. A register-file change worth measuring again has
to move that fanout, not the tree behind it.

## The clock gate's cost

Against the flops at global route, power at STA's default activity:

| | register file | flops |
|---|---:|---:|
| hold worst slack | +85.8 ps | +35.7 ps |
| clock-tree buffers and inverters | 179 (58.1 um2) | 122 (52.5 um2) |
| clock gates | 31 | 0 |
| power, total | 23.9 mW | 31.4 mW |
| power, clock-tree buffers | 0.53 mW | 2.63 mW |

No hold repair runs in either design. One caveat: riscv32i's input delay
has no `-min`, so inputs arrive late for hold as well.

## Where it does not carry

On XSTile (ideas/xiangshan-timing.md, entry 49), inlining lost: the
parent with its three register files inlined was 7.7 % slower than with
them placed as macros that dissolve, with global-route congestion 21.5
to 29.2 %. Inlining wins on a small design and loses on a parent with
1.3 M register-file cells, where keeping each array in one place is
worth more than anything inlining saves.
