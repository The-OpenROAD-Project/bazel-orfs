# A tile generator beside generate_ram

An idea for later in the register-file campaign, not started. The user
injects a repeating netlist, a tile, and a generic engine lays out the
array of it: the tile's cells placed once by a solver (OR-tools CP-SAT),
the array tiled by construction, the periphery built by hooks. It would
sit *beside* generate_ram, not replace it. generate_ram covers storage
with one word per row, decoders and read trees; the engine would cover
the repeating structures generate_ram cannot express:

- CAMs: a compare cell per bit, a match line per row reduced across it;
- systolic and multiply-accumulate arrays: a 2-D tile wired to its
  neighbours, no decoder;
- FIFOs and shift or delay lines: a pointer ring as the periphery;
- datapath bit-slices (adders, shifters, muxes): a bit per row, the
  carry chain a net between neighbouring tiles.

## What the user injects

1. The tile netlist, of liberty cells, each port declared row-shared,
   column-shared, wired to a neighbour (N, E, S, W) or periphery.
2. Tiling rules: the tile's height in rows, its column pitch, mirroring
   per row and column.
3. Periphery hooks: a generator per row or column edge (decoder, driver,
   reduction tree, pointer), each matched to the tile's pitch.
4. Optionally, hints for the tile's solve: fixed cells, pin sides.

Exact solvers handle tens to a few hundred objects, so CP-SAT fits the
tile and the small choices around it (fold, aspect ratio, pin sides),
not the array.

## Prior art

A literature search (2026-10-13) found the pieces but not the
combination, and no published placement work that uses CP-SAT.

- Injected cells, tiled: OpenRAM (https://github.com/VLSIDA/OpenRAM),
  its bitcell and periphery modules overridable per technology; SRAM22
  on Substrate, typed composable generators (Berkeley EECS-2023-137).
  Both are custom-layout SRAMs only.
- Standard-cell RAMs of fixed cells: DFFRAM, whose density came from a
  placer that knew its structure (https://github.com/AUCOHL/DFFRAM);
  OpenROAD's ram module, arXiv 2607.12244 (Louie, Nguyen, Liberty,
  Rovinski).
- Bit-slice alignment in a general placer: Ward et al., SAPT, IEEE
  TCAD 32(2), 2013; regularity extraction, Chowdhary et al., ICCAD 1998.
- Exact solvers for small layouts: SMTCell (UCSD), BonnCell (Bonn); ILP
  detailed placement under array constraints in ALIGN, arXiv 2008.10682.

Read first: arXiv 2607.12244, OpenRAM's override design with
EECS-2023-137, then SAPT and ALIGN.
