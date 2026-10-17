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


def _worker(name, n, contract, free, comment):
    """A block with a contract circuit (contract_in to contract_out, two
    register stages) and a free circuit (free_in to free_out, one stage)
    that touches the contract circuit by one net, en: built alone, the free
    circuit's cells follow en to wherever the contract pins hold the
    contract circuit, and the free pins follow them."""
    return f"""// {comment}
module {name} (
  input clock,
  input [{n - 1}:0] {contract}_in,
  output [{n - 1}:0] {contract}_out,
  input [{n - 1}:0] {free}_in,
  output [{n - 1}:0] {free}_out
);
  reg [{n - 1}:0] r1, r2, fr;
  reg en;
  always @(posedge clock) begin
    r1 <= {contract}_in ^ {{{contract}_in[0], {contract}_in[{n - 1}:1]}};
    r2 <= r1 ^ {{r1[{n - 2}:0], r1[{n - 1}]}};
    en <= ^r2;
    fr <= {free}_in ^ {{{n}{{en}}}};
  end
  assign {contract}_out = r2;
  assign {free}_out = fr;
endmodule
"""


def _bank(name, n, comment):
    """A block that registers its input: what the parent sees as a small
    register file or a pipeline stage, n bits in and out."""
    return f"""// {comment}
module {name} (
  input clock,
  input [{n - 1}:0] d,
  output [{n - 1}:0] q
);
  reg [{n - 1}:0] r;
  always @(posedge clock) r <= d ^ {{d[0], d[{n - 1}:1]}};
  assign q = r;
endmodule
"""


def _mix(n, src):
    """n bits of src mixed with its neighbour: one xor per bit."""
    return f"{src} ^ {{{src}[0], {src}[{n - 1}:1]}}"


def both_own(t, n):
    """Two blocks side by side, each with its contract on its top edge and
    a free interface to the other: built alone, each puts its free pins
    by its own logic, and neither faces the other across the gap
    between them (pin trap 2; XiangShan inventory entry 13). The parent
    registers each block's contract inputs in a strip above the blocks."""
    return (
        _worker(f"{t}_a", n, "t", "x", f"{t}: block a")
        + _worker(f"{t}_b", n, "t", "x", f"{t}: block b")
        + f"""
module {t}_top (
  input clock,
  input [{n - 1}:0] pa_in,
  output [{n - 1}:0] pa_out,
  input [{n - 1}:0] pb_in,
  output [{n - 1}:0] pb_out
);
  wire [{n - 1}:0] ab, ba;
  reg [{n - 1}:0] ra, rb;
  always @(posedge clock) begin
    ra <= {_mix(n, "pa_in")};
    rb <= {_mix(n, "pb_in")};
  end
  {t}_a u_a (.clock(clock), .t_in(ra), .t_out(pa_out), .x_in(ba), .x_out(ab));
  {t}_b u_b (.clock(clock), .t_in(rb), .t_out(pb_out), .x_in(ab), .x_out(ba));
endmodule
"""
    )


def narrow_channel(t, n):
    """Two blocks facing each other across a channel, the parent's own
    registers between them on every wire. A channel just wide enough for
    the wires has no rows for those registers, so the parent places them
    in what room it has elsewhere and every wire goes there and back
    (pin trap 9; macro_anneal's channel floor, XiangShan entry 5)."""
    return (
        _worker(f"{t}_a", n, "w", "e", f"{t}: block a")
        + _worker(f"{t}_b", n, "e", "w", f"{t}: block b")
        + f"""
module {t}_top (
  input clock,
  input [{n - 1}:0] pw_in,
  output [{n - 1}:0] pw_out,
  input [{n - 1}:0] pe_in,
  output [{n - 1}:0] pe_out
);
  wire [{n - 1}:0] a_e, b_w;
  reg [{n - 1}:0] to_b, to_a;
  always @(posedge clock) begin
    to_b <= {_mix(n, "a_e")};
    to_a <= {_mix(n, "b_w")};
  end
  {t}_a u_a (.clock(clock), .w_in(pw_in), .w_out(pw_out), .e_in(to_a), .e_out(a_e));
  {t}_b u_b (.clock(clock), .e_in(pe_in), .e_out(pe_out), .w_in(to_b), .w_out(b_w));
endmodule
"""
    )


def split_logic(t, n):
    """The parent's logic is one cluster (a shared reduction ties its
    registers together) that talks to two blocks, n wires each, and the
    blocks talk to each other by a few. Placing the partners side by side
    is what a pairwise cost asks for; it cuts the parent's logic in two,
    and the cluster pays across the cut (pin trap 10; XiangShan entry
    31, the logic region a strip)."""
    k = max(2, n // 8)
    return (
        _bank(f"{t}_a", n, f"{t}: block a")
        + _bank(f"{t}_b", n, f"{t}: block b")
        + f"""
module {t}_top (
  input clock,
  input [{k - 1}:0] p_in,
  output [{k - 1}:0] p_out
);
  wire [{n - 1}:0] qa, qb;
  reg [{n - 1}:0] la, lb;
  reg s;
  always @(posedge clock) begin
    s <= ^la ^ ^lb;
    la <= {_mix(n, "qb")} ^ {{{n}{{s}}}};
    lb <= {_mix(n, "qa")} ^ {{{n}{{s}}}};
  end
  // the partners' own few wires: a's low bits into b's, through the ports
  {t}_a u_a (.clock(clock), .d(la), .q(qa));
  {t}_b u_b (.clock(clock), .d(lb ^ {{{{{n - k}{{1'b0}}}}, p_in}}), .q(qb));
  assign p_out = qa[{k - 1}:0] ^ qb[{k - 1}:0];
endmodule
"""
    )


def tidy_row(t, n):
    """Four small register files, each owned by logic tied to the ports
    on one edge of the die. A tidy row along one edge is what a packing
    cost asks for; three of the four files then sit across the die from
    their owners (pin trap 11; XiangShan entry 53, a file 1 972 um from
    its owner)."""
    body = _bank(f"{t}_f", n, f"{t}: a file, four instances")
    ports = []
    logic = []
    for e in ("w", "e", "s", "n"):
        ports.append(f"  input [{n - 1}:0] p{e}_in,\n  output [{n - 1}:0] p{e}_out")
        logic.append(
            f"""  wire [{n - 1}:0] q{e};
  reg [{n - 1}:0] d{e}, o{e};
  always @(posedge clock) begin
    d{e} <= {_mix(n, f"p{e}_in")};
    o{e} <= {_mix(n, f"q{e}")};
  end
  {t}_f u_f{e} (.clock(clock), .d(d{e}), .q(q{e}));
  assign p{e}_out = o{e};"""
        )
    port_list = ",\n".join(ports)
    logic_list = "\n".join(logic)
    return (
        body
        + f"""
module {t}_top (
  input clock,
{port_list}
);
{logic_list}
endmodule
"""
    )


def flip(t, n):
    """A block whose pins sit on the west half of its top edge, under the
    parent's logic that answers them from the east. The parent's cheap fix
    is to mirror the block (MY) rather than ask for new pins: the pins
    land under the logic, and the wire is the hand-made block's. But a
    mirror moves each pin from x to w - x, and unless the block's width is
    a whole number of track pitches from the parent's tracks, every pin on
    a vertical layer lands between two of them (pin trap 7;
    macro_anneal.flip_legal, XiangShan entry 12's pin access)."""
    return f"""// {t}: the flip that wins on wire (pin trap 7).
module {t}_a (
  input clock,
  input [{n - 1}:0] x_in,
  output [{n - 1}:0] x_out
);
  reg [{n - 1}:0] r;
  always @(posedge clock) r <= {_mix(n, "x_in")};
  assign x_out = r;
endmodule

module {t}_top (
  input clock,
  input [{n - 1}:0] p_in,
  output [{n - 1}:0] p_out
);
  wire [{n - 1}:0] q;
  reg [{n - 1}:0] d, o;
  always @(posedge clock) begin
    d <= {_mix(n, "p_in")};
    o <= {_mix(n, "q")};
  end
  {t}_a u_a (.clock(clock), .x_in(d), .x_out(q));
  assign p_out = o;
endmodule
"""


def random_io(t, n):
    """Trap 11's netlist with every pin free and the files left to the
    macro placer: today's flow places the parent's pins at random, places
    the macros against them, and only after global placement puts the
    pins where the logic is; by then the macros are fixed (pin trap 12;
    ORFS patch 0077, ppl after gpl)."""
    return tidy_row(t, n)


def wide_pins(t, n):
    """Trap 7's netlist, the block's pins placed exactly on its top edge
    and drawn wider than a wire: safer for the block, a margin against
    a pin too thin to hit; the parent's pin access may find no access
    point on them (pin trap 8; XiangShan entry 12, DRT-0073 on one pin
    per block while the planner drew pins two wire widths wide)."""
    return flip(t, n)


TRAPS = {
    "both_own": both_own,
    "face_away": face_away,
    "flip": flip,
    "narrow_channel": narrow_channel,
    "random_io": random_io,
    "split_logic": split_logic,
    "tidy_row": tidy_row,
    "wide_pins": wide_pins,
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
