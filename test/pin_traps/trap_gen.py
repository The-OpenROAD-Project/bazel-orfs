#!/usr/bin/env python3
"""Write one pin trap's Verilog: its blocks and the parent that holds them.

    trap_gen.py --trap NAME --bits N --out FILE

A pin trap is a parent and one or more hardened blocks in which the choice
a block makes on its own, built alone, is the right one for the block and
a pathological one for the parent. Each trap is one concern; traps.bzl
holds the geometry and the two arms (the block's own choice, and the
answer written by hand), and the tests check that the first lands where
the hand-computed bad number says and the second where the good one says.
Modules are prefixed with the trap's name so every trap's netlist can sit
next to every other's.

Plain Verilog-2005 so either frontend reads it.
"""

import argparse
import sys


def face_away(t, n):
    """A block whose contract pins sit on its west side, and whose free
    interface the parent's logic meets on its east side.

    Block <t>_a: a w circuit (w_in to w_out through two register stages,
    tied to the contract on the west), and an e circuit (e_in to e_out
    through one register stage) that touches the w circuit by one net, en.
    Built alone, the e circuit's cells follow en to the west in the first
    global placement (which ignores free pins), and the pin placer puts
    e_in and e_out next to them: the west. The parent's logic answering
    e_out into e_in can only sit east of the block, so every one of the
    2N interface wires crosses the block. The hand-made answer puts the
    e pins on the east side and pays for it with one long net, en.
    """
    return f"""// {t}: pins face away from their partner (pin trap 1).
module {t}_a (
  input clock,
  input [{n - 1}:0] w_in,
  output [{n - 1}:0] w_out,
  input [{n - 1}:0] e_in,
  output [{n - 1}:0] e_out
);
  reg [{n - 1}:0] r1, r2, er;
  reg en;
  always @(posedge clock) begin
    r1 <= w_in ^ {{w_in[0], w_in[{n - 1}:1]}};
    r2 <= r1 ^ {{r1[{n - 2}:0], r1[{n - 1}]}};
    en <= ^r2;
    er <= e_in ^ {{{n}{{en}}}};
  end
  assign w_out = r2;
  assign e_out = er;
endmodule

module {t}_top (
  input clock,
  input [{n - 1}:0] p_in,
  output [{n - 1}:0] p_out
);
  wire [{n - 1}:0] a_e_out;
  reg [{n - 1}:0] q;
  always @(posedge clock)
    q <= a_e_out ^ {{a_e_out[0], a_e_out[{n - 1}:1]}};
  {t}_a u_a (
    .clock(clock),
    .w_in(p_in),
    .w_out(p_out),
    .e_in(q),
    .e_out(a_e_out)
  );
endmodule
"""


TRAPS = {
    "face_away": face_away,
}


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--trap", required=True, choices=sorted(TRAPS))
    p.add_argument("--bits", type=int, required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    if a.bits < 2:
        raise SystemExit("--bits must be at least 2, got %d" % a.bits)
    with open(a.out, "w") as f:
        f.write(TRAPS[a.trap](a.trap, a.bits))


if __name__ == "__main__":
    main(sys.argv[1:])
