# structured_gen

Placed register files as standard-cell macros, written with OpenROAD's
own libraries.

## Why

A many-port register file synthesised to flops is a flop per bit, a
W-way write mux on every flop's D and an R-way read mux tree per bit.
Global placement puts it where its consumers are and the legaliser then
cannot spread it: on XiangShan, the four floating-point register-file
parts (256 × 16, 14 read and 7 write ports) stopped the fp region's
detailed placement twice, at 17 k misaligned cells after hours, and the
integer register file (224 × 64, 12R 9W) did the same to the parent. A
core in that class has these as compiled multi-port bitcells; they are
macros in the design and absent from its gate count.

This tool builds the same function the way a bitcell array is built:
word rows by bit columns, every cell placed by construction, nothing
left to a placer. OpenROAD's own `ram` generator is the precedent; it
allows one write port, and this one exists for the many-write case.

## What it writes

- an ODB with the block's rows, every instance placed FIRM, power and
  ground nets, and every port as a placed pin box on the die edge, with
  the RTL module's own pin names so the macro drops in for the module
  it replaces;
- a structural Verilog netlist of the same block, ports declared as the
  RTL's buses, for simulation and for the flow's netlist view.

The ODB enters the flow as a placed design: CTS, global route, detailed
route and the abstract run unchanged on it.

## The layout

```
        header          bit 0        bit 1   ...   tap   ...
word 0  [decode R+W]   [tile]       [tile]         [tap]
word 1  [decode R+W]   [tile]       [tile]         [tap]
...
        address inverters, one band above the array
```

A tile is one (word, bit): the flop, an inverter giving Q from QN, the
write mux as AO22 pairs and an OR2 tree, one AND2 per read port, and
that bit's share of the read OR trees. The read wordline of a port is
one-hot over the words and decoded once per word in the header column;
the read bitline of a port is a balanced OR tree whose nodes are dropped
into the tiles of the words they cover, so the tree runs down the column
instead of piling up in a footer. A tile is as many standard rows tall
as it takes to stay about 40 sites wide. A tap column stands every
`tap_columns` bit columns.

Read path: address inverters, an AND2 tree over the literals, the tile's
AND2, and log2(words) OR2 levels. For 256 words that is about twelve
gate levels.

## The spec

A small `key value` file. A spec is complete or refused with the line
that is wrong; there is no default for a cell.

```
module          FpRegFilePart0
words           256
bits            16
clock           clock
read            io_readPorts_0_addr  io_readPorts_0_data
read            io_readPorts_1_addr  io_readPorts_1_data
write           io_writePorts_0_addr io_writePorts_0_data io_writePorts_0_wen
cell flop       DFFHQNx1_ASAP7_75t_R
cell and2       AND2x2_ASAP7_75t_R
cell or2        OR2x2_ASAP7_75t_R
cell ao22       AO22x2_ASAP7_75t_R
cell inv        INVx1_ASAP7_75t_R
cell tap        TAPCELL_ASAP7_75t_R
pin_layer       M4
tap_columns     8
```

Cell pins default to asap7's (`D CLK QN`, `A B Y`, `A1 A2 B1 B2 Y`,
`A Y`); another library gives its own with `pins flop D CK Q` and
`flop_output Q`.

```
bazel run //tools/structured_gen -- --spec rf.spec \
    --lef asap7_tech_1x_201209.lef --lef asap7sc7p5t_28_R_1x_220121a.lef \
    --odb FpRegFilePart0.odb --verilog FpRegFilePart0.v
```

## What it refuses

A cell or pin the LEF does not have. A spec line it does not understand.
A layout whose header or tile overflows the width it was given, which
would mean two cells on one site. Fewer than two words, one bit, one
read or one write port. More ports than the die edge holds at the pin
layer's pitch.

## Known limits, stated

- Two write ports hitting the same word in one cycle OR their data; a
  Chisel `Reg(Vec)` gives the last port priority. XiangShan's rename
  never issues that, and the simulation model is the RTL, so it is a
  documented difference rather than a hidden one.
- No reset. Register files in XiangShan have none.
- The pins sit on one layer at the die edge in port order; a parent
  that wants them on particular sides gets a `pin_side` key when it
  needs one.
- One flop kind, no latch option, no column mux ratio.

## Tests

`regfile_test` builds an 8 × 4 file with two read and two write ports
against the real asap7 LEF and checks: one flop per bit, every cell FIRM
and inside the die, no two cells sharing a site on a row, every port
pinned, every signal pin connected, and the Verilog's port declarations.
