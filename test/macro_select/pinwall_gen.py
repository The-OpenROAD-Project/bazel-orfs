#!/usr/bin/env python3
"""Generate the pin-wall block and its parent for a given interface width.

    pinwall_gen.py --pins N --block block.sv --top top.sv

The block has N pins in all, N/2 in and N/2 out, registered on both sides
of the boundary: the cut the macro selection looks for. The parent
instantiates it and answers every output with a register of its own that
feeds an input back, so every pin has one wire to one flop in the parent,
and the router's demand across the block's pin side is N wires. Plain
Verilog-2005 so either frontend reads it.
"""

import argparse
import sys


def block(n):
    n = n // 2
    return """// {n} pins in, {n} out, registered on both sides.
module pinwall_block (
    input wire clock,
    input wire [{h}:0] din,
    output wire [{h}:0] dout
);
  reg [{h}:0] din_r;
  reg [{h}:0] dout_r;
  always @(posedge clock) begin
    din_r <= din;
    dout_r <= {{din_r[{h2}:0], din_r[{h}]}} ^ din_r;
  end
  assign dout = dout_r;
endmodule
""".format(n=n, h=n - 1, h2=n - 2)


def top(n):
    n = n // 2
    return """// The parent: one register per block pin, each answering the block.
module pinwall_top (
    input wire clock,
    input wire [63:0] seed,
    output wire [63:0] sum
);
  wire [{h}:0] to_block;
  wire [{h}:0] from_block;
  reg [{h}:0] parent_r;
  pinwall_block block (.clock(clock), .din(to_block), .dout(from_block));
  always @(posedge clock) begin
    parent_r <= from_block ^ {{{reps}{{seed}}}};
  end
  assign to_block = parent_r;
  assign sum = ^parent_r ? seed : ~seed;
endmodule
""".format(h=n - 1, reps=(n + 63) // 64)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pins", type=int, required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--top", required=True)
    a = ap.parse_args(argv[1:])
    with open(a.block, "w") as f:
        f.write(block(a.pins))
    with open(a.top, "w") as f:
        f.write(top(a.pins))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
