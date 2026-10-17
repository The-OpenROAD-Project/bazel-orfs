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
import re
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
        _bank(f"{t}_a", n, f"{t}: block a") + _bank(f"{t}_b", n, f"{t}: block b") + f"""
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


def _pipe(name, n, src, depth):
    """depth register stages of n bits from src, each mixing a bit with its
    neighbour: the owner logic a trap's rung sizes. Returns the Verilog
    and the last stage's name."""
    lines = []
    prev = src
    for k in range(depth):
        r = "%s%d" % (name, k)
        lines.append(f"  reg [{n - 1}:0] {r};")
        lines.append(f"  always @(posedge clock) {r} <= {_mix(n, prev)};")
        prev = r
    return "\n".join(lines), prev


def tidy_row(t, n, depth=1):
    """Four small register files, each owned by logic tied to the ports
    on one edge of the die. A tidy row along one edge is what a packing
    cost asks for; three of the four files then sit across the die from
    their owners (pin trap 11; XiangShan entry 53, a file 1 972 um from
    its owner). depth is the owner's register stages on each side of its
    file: the large rung's owners are thousands of cells, above the macro
    placer's 1 000-cell cluster floor, so it can tell them apart."""
    body = _bank(f"{t}_f", n, f"{t}: a file, four instances")
    ports = []
    logic = []
    for e in ("w", "e", "s", "n"):
        ports.append(f"  input [{n - 1}:0] p{e}_in,\n  output [{n - 1}:0] p{e}_out")
        din, dlast = _pipe(f"d{e}_", n, f"p{e}_in", depth)
        dout, olast = _pipe(f"o{e}_", n, f"q{e}", depth)
        logic.append(f"""  wire [{n - 1}:0] q{e};
{din}
{dout}
  {t}_f u_f{e} (.clock(clock), .d({dlast}), .q(q{e}));
  assign p{e}_out = {olast};""")
    port_list = ",\n".join(ports)
    logic_list = "\n".join(logic)
    return body + f"""
module {t}_top (
  input clock,
{port_list}
);
{logic_list}
endmodule
"""


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


def aspect(t, n):
    """Twenty equal blocks and a few registers of the parent's: on a core
    of a given area the blocks tile five by four with their channels, and
    the same area as a square holds only four columns of four. A square
    core is every flow's default; for this parent it is infeasible, and
    no macro placer can find what does not exist (pin trap 13; ORFS #4681
    aes-block MPL-0003, the sliver outlines of mpl's real-design table)."""
    insts = "\n".join(
        f"  {t}_m u_m{i} (.clock(clock), .d(r ^ {i}), .q(q[{i}]));" for i in range(20)
    )
    return _bank(f"{t}_m", n, f"{t}: one block, twenty instances") + f"""
module {t}_top (
  input clock,
  input [{n - 1}:0] p_in,
  output p_out
);
  wire [{n - 1}:0] q [0:19];
  reg [{n - 1}:0] r;
  reg o;
  always @(posedge clock) begin
    r <= p_in;
    o <= ^(q[0] ^ q[1] ^ q[2] ^ q[3] ^ q[4] ^ q[5] ^ q[6] ^ q[7] ^ q[8] ^ q[9]
        ^ q[10] ^ q[11] ^ q[12] ^ q[13] ^ q[14] ^ q[15] ^ q[16] ^ q[17] ^ q[18] ^ q[19]);
  end
{insts}
  assign p_out = o;
endmodule
"""


def selfish(t, n):
    """Trap 1 with a block that is better off alone: its free circuit
    reads every bit of its contract circuit, not one en net, so pins by
    its own logic are the block's shortest wire, and the hand answer
    pays n long nets inside the block for the 2n it saves the parent
    (pin trap 4; XiangShan entry 35, CoupledL2's own pins 17.8 % faster
    and the parent's overflow 17.6 % up)."""
    return f"""// {t}: the block is better alone (pin trap 4).
module {t}_a (
  input clock,
  input [{n - 1}:0] w_in,
  output [{n - 1}:0] w_out,
  input [{n - 1}:0] e_in,
  output [{n - 1}:0] e_out
);
  reg [{n - 1}:0] r1, r2, er;
  always @(posedge clock) begin
    r1 <= {_mix(n, "w_in")};
    r2 <= {_mix(n, "r1")};
    er <= e_in ^ r2;
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
    q <= {_mix(n, "a_e_out")};
  {t}_a u_a (
    .clock(clock),
    .w_in(p_in),
    .w_out(p_out),
    .e_in(q),
    .e_out(a_e_out)
  );
endmodule
"""


def in2out(t, n):
    """A combinational path through a hardened block on the parent's worst
    path. Block x registers its output, block c registers its input, and
    the two sit side by side; between them the parent's path runs through
    block b, an adder from b's f_in pins to its f_out pins with no
    register on the way, and b sits across the die where its own
    registered interface (m_in, m_out) puts it. No placement of the parent
    shortens x to b to c without moving b off its own interface, and the
    blocks are placed as built: this is a surgery problem, not a placement
    one (surgery trap; XiangShan inventory entry 26, the parent's worst
    paths bare wires between blocks).

    The surgery, written out here as the modules <t>_b_s and <t>_top_s:
    the adder leaves b for the parent, between x and c, and b keeps its
    own interface. No register is added or moved; in2out_equiv proves the
    two parents equivalent."""
    h = n // 2
    cone = f"(f_in + {{f_in[{h - 1}:0], f_in[{n - 1}:{h}]}})"
    return f"""// {t}: an in2out path through a block on the worst path (surgery trap).
module {t}_x (
  input clock,
  input [{n - 1}:0] xi,
  output [{n - 1}:0] xq
);
  reg [{n - 1}:0] r;
  always @(posedge clock) r <= {_mix(n, "xi")};
  assign xq = r;
endmodule

module {t}_c (
  input clock,
  input [{n - 1}:0] cd,
  output [{n - 1}:0] cq
);
  reg [{n - 1}:0] r;
  always @(posedge clock) r <= {_mix(n, "cd")};
  assign cq = r;
endmodule

module {t}_b (
  input clock,
  input [{n - 1}:0] m_in,
  output [{n - 1}:0] m_out,
  input [{n - 1}:0] f_in,
  output [{n - 1}:0] f_out
);
  reg [{n - 1}:0] r1, r2;
  always @(posedge clock) begin
    r1 <= {_mix(n, "m_in")};
    r2 <= {_mix(n, "r1")};
  end
  assign m_out = r2;
  assign f_out = {cone};
endmodule

module {t}_top (
  input clock,
  input [{n - 1}:0] px_in,
  output [{n - 1}:0] pc_out,
  input [{n - 1}:0] pm_in,
  output [{n - 1}:0] pm_out
);
  wire [{n - 1}:0] xq, bf;
  {t}_x u_x (.clock(clock), .xi(px_in), .xq(xq));
  {t}_b u_b (.clock(clock), .m_in(pm_in), .m_out(pm_out), .f_in(xq), .f_out(bf));
  {t}_c u_c (.clock(clock), .cd(bf), .cq(pc_out));
endmodule

// after surgery: the adder in the parent, b with its own interface only
module {t}_b_s (
  input clock,
  input [{n - 1}:0] m_in,
  output [{n - 1}:0] m_out
);
  reg [{n - 1}:0] r1, r2;
  always @(posedge clock) begin
    r1 <= {_mix(n, "m_in")};
    r2 <= {_mix(n, "r1")};
  end
  assign m_out = r2;
endmodule

module {t}_top_s (
  input clock,
  input [{n - 1}:0] px_in,
  output [{n - 1}:0] pc_out,
  input [{n - 1}:0] pm_in,
  output [{n - 1}:0] pm_out
);
  wire [{n - 1}:0] xq, f_in, bf;
  {t}_x u_x (.clock(clock), .xi(px_in), .xq(xq));
  {t}_b_s u_b (.clock(clock), .m_in(pm_in), .m_out(pm_out));
  assign f_in = xq;
  assign bf = {cone};
  {t}_c u_c (.clock(clock), .cd(bf), .cq(pc_out));
endmodule
"""


# The combined parent: these traps, each its own parent as a submodule,
# their ports prefixed with the trap's name, at the widths their own
# traps use.
COMBINED = (("face_away", 32), ("narrow_channel", 32), ("split_logic", 64))


def mini_top(t, n):
    """Several traps' parents in one parent, each in a band of its own:
    whether each trap still catches today's flow, and whether the pin
    loop still finds its answer, once the traps share a die and the
    parent's placer can trade between them. n is not used: each trap
    keeps its own width."""
    del n
    text = []
    ports = []
    insts = []
    for trap, bits in COMBINED:
        sv = TRAPS[trap](trap, bits)
        text.append(sv)
        header = re.search(r"module %s_top \((.*?)\);" % trap, sv, re.S)
        if header is None:
            raise SystemExit("mini_top: no %s_top header" % trap)
        conns = []
        for decl in header.group(1).split(","):
            m = re.match(r"\s*(input|output)\s*(\[[^\]]*\])?\s*(\w+)\s*$", decl)
            if m is None:
                raise SystemExit(
                    "mini_top: cannot read port %r of %s_top" % (decl, trap)
                )
            direction, width, port = m.groups()
            if port == "clock":
                conns.append(".clock(clock)")
                continue
            ports.append(
                "  %s %s%s_%s" % (direction, (width + " ") if width else "", trap, port)
            )
            conns.append(".%s(%s_%s)" % (port, trap, port))
        insts.append("  %s_top u_%s (%s);" % (trap, trap, ", ".join(conns)))
    port_list = ",\n".join(["  input clock"] + ports)
    inst_list = "\n".join(insts)
    return "".join(text) + f"""
module {t}_top (
{port_list}
);
{inst_list}
endmodule
"""


def tidy_row_large(t, n):
    """Trap 11 on the large rung: owners of 8 stages a side."""
    return tidy_row(t, n, depth=8)


def random_io_large(t, n):
    """Trap 12 on the large rung: trap 11's large netlist, every pin free."""
    return tidy_row(t, n, depth=8)


TRAPS = {
    "aspect": aspect,
    "both_own": both_own,
    "face_away": face_away,
    "flip": flip,
    "in2out": in2out,
    "mini_top": mini_top,
    "narrow_channel": narrow_channel,
    "random_io": random_io,
    "random_io_large": random_io_large,
    "selfish": selfish,
    "split_logic": split_logic,
    "tidy_row": tidy_row,
    "tidy_row_large": tidy_row_large,
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
