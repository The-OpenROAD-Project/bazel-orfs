"""Structural netlists of array parts in asap7 cells, a prototype of
generate_array's parts.

The structures the literature gives each part, built cell by cell so
that synthesis maps nothing: one decoder per index signal shared by every
word, log-depth trees and prefixes, no per-entry comparators. What a
mapper would add is added here: buffer trees on high-fanout nets, wide
inverting gates in the trees, drive strengths by fanout. Each kind
is written as module Arr with the ports test/array_toys's toy of that kind
has, and the update order of its RTL, so LEC can check one against the
other. Once the structures settle, they move into OpenROAD's
generate_array, which builds the same netlists and places them.

    structgen.py <kind> <depth> <width> <out.v>

kinds: flags, counter, cam, agematrix
"""

import math
import sys

_V = "_ASAP7_75t_R"

# a net drives at most this many cell inputs; more go through a tree of
# buffers, as a mapper builds one. A decoded write enable drives a whole
# word: left to repair_design, it is a chain of buffers at fanout 25-50,
# and at 32 x 128 every word of the CAM missed the period by up to
# 170 ps, which repair_timing then worked through endpoint by endpoint
FANOUT = 32

# the drive strengths a cell takes by its fanout: 1, 2-3, more
_SIZES = {
    "INVx1": ["INVx1", "INVx2", "INVx3"],
    "AND2x2": ["AND2x2", "AND2x4", "AND2x4"],
    "NAND2xp5": ["NAND2xp5", "NAND2x1", "NAND2x1p5"],
    "NAND3xp33": ["NAND3xp33", "NAND3x1", "NAND3x2"],
    "NOR2xp33": ["NOR2xp33", "NOR2x1", "NOR2x1p5"],
    "NOR3xp33": ["NOR3xp33", "NOR3x1", "NOR3x2"],
    "OR2x2": ["OR2x2", "OR2x4", "OR2x4"],
    "AO22x1": ["AO22x1", "AO22x2", "AO22x2"],
    "AO21x1": ["AO21x1", "AO21x2", "AO21x2"],
    "XOR2xp5": ["XOR2xp5", "XOR2x1", "XOR2x2"],
    "XNOR2xp5": ["XNOR2xp5", "XNOR2x1", "XNOR2x2"],
}


class Netlist:
    def __init__(self):
        self.lines = []
        self.cells = []  # [master, {pin: net}, output pin, output net]
        self.wires = []
        self.n = 0
        self.zero = "1'b0"
        self.one = "1'b1"
        self._inv = {}
        self._inv_of = {}

    def wire(self):
        self.n += 1
        name = f"n{self.n}"
        self.wires.append(name)
        return name

    def cell(self, master, **pins):
        out = self.wire()
        outpin = "QN" if master.startswith("DFF") else "Y"
        self.cells.append([master, dict(pins), outpin, out])
        return out

    # constants fold, so a decode of a tied-off index stays small; a
    # net's complement is made once and shared
    def inv(self, a):
        if a == self.zero:
            return self.one
        if a == self.one:
            return self.zero
        if a in self._inv_of:
            return self._inv_of[a]
        if a not in self._inv:
            out = self.cell("INVx1", A=a)
            self._inv[a] = out
            self._inv_of[out] = a
        return self._inv[a]

    def and2(self, a, b):
        if self.zero in (a, b):
            return self.zero
        if a == self.one:
            return b
        if b == self.one:
            return a
        return self.cell("AND2x2", A=a, B=b)

    def or2(self, a, b):
        if self.one in (a, b):
            return self.one
        if a == self.zero:
            return b
        if b == self.zero:
            return a
        return self.cell("OR2x2", A=a, B=b)

    # a register's value is its flop's QN inverted: a compare reads QN
    # and flips the gate, so the inverter is no level of the compare
    def xor2(self, a, b):
        if a in self._inv_of:
            return self.xnor2(self._inv_of[a], b)
        return self.cell("XOR2xp5", A=a, B=b)

    def xnor2(self, a, b):
        if a in self._inv_of:
            return self.cell("XOR2xp5", A=self._inv_of[a], B=b)
        return self.cell("XNOR2xp5", A=a, B=b)

    def ao21(self, a1, a2, b):
        """a1 & a2 | b"""
        if self.zero in (a1, a2):
            return b
        if b == self.zero:
            return self.and2(a1, a2)
        return self.cell("AO21x1", A1=a1, A2=a2, B=b)

    def priority(self, xs):
        """The lowest set index of xs, a power of two long, as index bits
        LSB-first, zero when none is set. Halves combine as a mapper's
        encoder does: the low half's index where it has a set bit, else
        the high half's, one AO21 a bit and level (low | ~any_low &
        high), the new top bit ~any_low & any_high. Each half's any is
        its own tree of 3-input inverting gates, not a chain of the
        levels' ORs: a bit is one AO21 per level deep after the widest
        such tree, where a prefix OR and an OR tree over the one-hot
        lowest set bit are each log2(n) levels."""
        if len(xs) == 1:
            return []
        half = len(xs) // 2
        i_lo = self.priority(xs[:half])
        i_hi = self.priority(xs[half:])
        n_lo = self.inv(self.tree(self.or2, xs[:half]))
        bits = [self.ao21(n_lo, h, lo) for lo, h in zip(i_lo, i_hi)]
        bits.append(self.and2(n_lo, self.tree(self.or2, xs[half:])))
        return bits

    def mux(self, s, a, b):
        """s ? b : a"""
        return self.cell("AO22x1", A1=s, A2=b, B1=self.inv(s), B2=a)

    def tree(self, op, xs):
        """The AND or OR of xs. Beyond two inputs, a tree of 3-input
        inverting gates, NAND and NOR by turns, as a mapper builds one:
        a 128-bit compare is seven levels of AND2, here five levels and
        an inverter. A path that cannot close, the CAM's match into its
        priority encoder, is repaired level by level, each move timed
        over the whole cone."""
        is_and = op == self.and2
        unit, dom = (self.one, self.zero) if is_and else (self.zero, self.one)
        xs = [x for x in xs if x != unit]
        if dom in xs:
            return dom
        if not xs:
            return unit
        if len(xs) <= 2:
            return xs[0] if len(xs) == 1 else op(xs[0], xs[1])
        # inverted: the level's values are the complements of its terms;
        # AND of terms is NAND of terms or NOR of complements, OR the dual
        inverted = False
        while len(xs) > 1:
            groups = -(-len(xs) // 3)
            base, extra = divmod(len(xs), groups)
            nxt, k = [], 0
            for g in range(groups):
                n = base + (g < extra)
                nand = is_and != inverted
                nxt.append(self.gate("NAND" if nand else "NOR", xs[k : k + n]))
                k += n
            xs = nxt
            inverted = not inverted
        return self.inv(xs[0]) if inverted else xs[0]

    def gate(self, kind, xs):
        """An n-input NAND or NOR, n 1-3; one input is an inverter."""
        if len(xs) == 1:
            return self.inv(xs[0])
        master = {
            ("NAND", 2): "NAND2xp5",
            ("NAND", 3): "NAND3xp33",
            ("NOR", 2): "NOR2xp33",
            ("NOR", 3): "NOR3xp33",
        }[(kind, len(xs))]
        return self.cell(master, **dict(zip("ABC", xs)))

    def prefix(self, op, xs):
        """Sklansky prefix: out[i] = op(xs[0..i])."""
        out = list(xs)
        n = len(out)
        step = 1
        while step < n:
            for i in range(n):
                if (i // step) % 2 == 1:
                    j = (i // step) * step - 1
                    out[i] = op(out[j], out[i])
            step *= 2
        return out

    def decode(self, bits, n, en=None):
        """One-hot of an index, LSB-first bits, gated by en: per output an
        AND of predecoded pairs."""
        groups = []
        for g in range(0, len(bits), 2):
            pair = bits[g : g + 2]
            inv = [self.inv(b) for b in pair]
            lines = []
            for v in range(1 << len(pair)):
                terms = [pair[k] if v >> k & 1 else inv[k] for k in range(len(pair))]
                lines.append(self.tree(self.and2, terms))
            groups.append(lines)
        out = []
        for i in range(n):
            terms = [
                groups[g][(i >> (2 * g)) & ((1 << len(bits[2 * g : 2 * g + 2])) - 1)]
                for g in range(len(groups))
            ]
            if en is not None:
                terms.append(en)
            out.append(self.tree(self.and2, terms))
        return out

    def ff(self, d):
        """A register: returns its value (the flop's QN inverted)."""
        qn = self.cell("DFFHQNx1", CLK="clock", D=d)
        return self.inv(qn)

    def buffer(self, limit=FANOUT):
        """Every net with more than limit cell sinks drives them through
        buffers, limit sinks each, in the order the sinks were made, so
        a buffer serves neighbouring bits of one word."""
        sinks = {}
        for k, (_, pins, _, _) in enumerate(self.cells):
            for p, v in pins.items():
                if v not in (self.zero, self.one, "clock"):
                    sinks.setdefault(v, []).append((k, p))
        for net, ss in sinks.items():
            while len(ss) > limit:
                groups = [ss[k : k + limit] for k in range(0, len(ss), limit)]
                ss = []
                for g in groups:
                    out = self.wire()
                    self.cells.append(["BUFx4f", {"A": net}, "Y", out])
                    for k, p in g:
                        self.cells[k][1][p] = out
                    ss.append((len(self.cells) - 1, "A"))

    def size(self):
        """Each cell's drive strength from its fanout, as a mapper would
        choose."""
        fanout = {}
        for _, pins, _, _ in self.cells:
            for v in pins.values():
                fanout[v] = fanout.get(v, 0) + 1
        for c in self.cells:
            fo = fanout.get(c[3], 0)
            if c[0] == "BUFx4f":
                c[0] = "BUFx4f" if fo <= 8 else "BUFx6f" if fo <= 16 else "BUFx12f"
            elif c[0] in _SIZES:
                c[0] = _SIZES[c[0]][0 if fo <= 1 else 1 if fo <= 3 else 2]

    def verilog(self):
        cells = []
        for k, (master, pins, outpin, out) in enumerate(self.cells):
            conns = ", ".join(f".{p}({v})" for p, v in pins.items())
            cells.append(f"  {master}{_V} c{k} ({conns}, .{outpin}({out}));")
        return [f"  wire {w};" for w in self.wires] + cells + self.lines

    def read_mux(self, words, dec):
        """words[i][b] selected by one-hot dec: per bit an AND-OR tree."""
        width = len(words[0])
        return [
            self.tree(
                self.or2, [self.and2(dec[i], words[i][b]) for i in range(len(words))]
            )
            for b in range(width)
        ]


def _abits(depth):
    return max(1, math.ceil(math.log2(depth)))


def _bus(name, w):
    return [f"{name}[{i}]" for i in range(w)]


def _registers(net, depth, width):
    """Word registers whose next value is set later: (values, D wires)."""
    d = [[net.wire() for _ in range(width)] for _ in range(depth)]
    q = [[net.ff(d[i][b]) for b in range(width)] for i in range(depth)]
    return q, d


def counter(net, depth, width):
    a = _abits(depth)
    ports = [
        ("input", 1, "clock"),
        ("input", 1, "w_en"),
        ("input", a, "w_addr"),
        ("input", width, "w_data"),
        ("input", 1, "d0_en"),
        ("input", a, "d0_idx"),
        ("input", 1, "d1_en"),
        ("input", a, "d1_idx"),
        ("input", a, "r_addr"),
        ("output", width, "r_data"),
        ("output", depth, "zero"),
    ]
    q, d = _registers(net, depth, width)
    dw = net.decode(_bus("w_addr", a), depth, "w_en")
    d0 = net.decode(_bus("d0_idx", a), depth, "d0_en")
    d1 = net.decode(_bus("d1_idx", a), depth, "d1_en")
    data = _bus("w_data", width)
    for i in range(depth):
        # q - (d0 + d1): s = d0 + d1 is 0, 1 or 2
        s0, s1 = net.xor2(d0[i], d1[i]), net.and2(d0[i], d1[i])
        x = q[i]
        diff = [net.xor2(x[0], s0)]
        borrow = net.and2(net.inv(x[0]), s0)
        if width > 1:
            t = net.xor2(s1, borrow)
            diff.append(net.xor2(x[1], t))
            # borrow out of bit 1: ~x1 & (s1 | borrow0) | (s1 & borrow0)
            borrow = net.or2(
                net.and2(net.inv(x[1]), net.or2(s1, borrow)), net.and2(s1, borrow)
            )
            # above bit 1 a borrow ripples through zeros: a prefix AND
            zeros = net.prefix(net.and2, [net.inv(b) for b in x[2:]])
            for k in range(2, width):
                into = borrow if k == 2 else net.and2(borrow, zeros[k - 3])
                diff.append(net.xor2(x[k], into))
        for b in range(width):
            net.lines.append(
                f"  assign {d[i][b]} = {net.mux(dw[i], diff[b], data[b])};"
            )
    for b, v in enumerate(net.read_mux(q, net.decode(_bus("r_addr", a), depth))):
        net.lines.append(f"  assign r_data[{b}] = {v};")
    for i in range(depth):
        net.lines.append(f"  assign zero[{i}] = {net.inv(net.tree(net.or2, q[i]))};")
    return ports


def flags(net, depth, width):
    a = _abits(depth)
    b = _abits(width)
    ports = [("input", 1, "clock"), ("input", 1, "reset")]
    for p in range(2):
        ports += [
            ("input", 1, f"s{p}_en"),
            ("input", a, f"s{p}_idx"),
            ("input", b, f"s{p}_bit"),
        ]
        ports += [
            ("input", 1, f"c{p}_en"),
            ("input", a, f"c{p}_idx"),
            ("input", b, f"c{p}_bit"),
        ]
    ports += [
        ("input", 1, "flush"),
        ("input", a, "flush_idx"),
        ("input", a, "head"),
        ("input", a, "r_addr"),
        ("output", width, "r_data"),
    ]
    q, d = _registers(net, depth, width)

    def plane(prefix):
        rows = net.decode(_bus(f"{prefix}_idx", a), depth, f"{prefix}_en")
        cols = net.decode(_bus(f"{prefix}_bit", b), width)
        return rows, cols

    sets = [plane("s0"), plane("s1")]
    clears = [plane("c0"), plane("c1")]
    # the redirect clears entries i with (i - head) >= (flush_idx - head):
    # the circular interval from flush_idx to head, from two thermometers
    one_f = net.decode(_bus("flush_idx", a), depth)
    one_h = net.decode(_bus("head", a), depth)
    t_f = net.prefix(net.or2, one_f)
    t_h = net.prefix(net.or2, one_h)
    f_below_h = net.tree(
        net.or2, [net.and2(one_f[i], net.inv(t_h[i])) for i in range(depth)]
    )
    keep_reset = net.inv("reset")
    for i in range(depth):
        inside = net.and2(t_f[i], net.inv(t_h[i]))
        outside = net.or2(t_f[i], net.inv(t_h[i]))
        cleared = net.and2("flush", net.mux(f_below_h, outside, inside))
        live = net.and2(keep_reset, net.inv(cleared))
        for k in range(width):
            s = net.or2(
                net.and2(sets[0][0][i], sets[0][1][k]),
                net.and2(sets[1][0][i], sets[1][1][k]),
            )
            c = net.or2(
                net.and2(clears[0][0][i], clears[0][1][k]),
                net.and2(clears[1][0][i], clears[1][1][k]),
            )
            nxt = net.and2(live, net.and2(net.inv(c), net.or2(s, q[i][k])))
            net.lines.append(f"  assign {d[i][k]} = {nxt};")
    for k, v in enumerate(net.read_mux(q, net.decode(_bus("r_addr", a), depth))):
        net.lines.append(f"  assign r_data[{k}] = {v};")
    return ports


def cam(net, depth, width):
    a = _abits(depth)
    ports = [
        ("input", 1, "clock"),
        ("input", 1, "w_en"),
        ("input", a, "w_addr"),
        ("input", width, "w_key"),
        ("input", width, "key"),
        ("output", 1, "hit"),
        ("output", a, "idx"),
    ]
    q, d = _registers(net, depth, width)
    dw = net.decode(_bus("w_addr", a), depth, "w_en")
    wkey, key = _bus("w_key", width), _bus("key", width)
    for i in range(depth):
        for k in range(width):
            net.lines.append(
                f"  assign {d[i][k]} = {net.mux(dw[i], q[i][k], wkey[k])};"
            )
    m = [
        net.tree(net.and2, [net.xnor2(q[i][k], key[k]) for k in range(width)])
        for i in range(depth)
    ]
    net.lines.append(f"  assign hit = {net.tree(net.or2, m)};")
    # the lowest matching entry's index: a priority encoder over the
    # matches, padded to a power of two with no match
    padded = m + [net.zero] * ((1 << a) - depth)
    idx = net.priority(padded)
    for k in range(a):
        net.lines.append(f"  assign idx[{k}] = {idx[k]};")
    return ports


def agematrix(net, depth, width):
    a = _abits(depth)
    ports = [
        ("input", 1, "clock"),
        ("input", 1, "reset"),
        ("input", 1, "alloc"),
        ("input", a, "alloc_idx"),
        ("input", 1, "free"),
        ("input", a, "free_idx"),
        ("input", depth, "req"),
        ("output", depth, "oldest"),
    ]
    older, d = _registers(net, depth, depth)
    vd = [net.wire() for _ in range(depth)]
    valid = [net.ff(vd[i]) for i in range(depth)]
    da = net.decode(_bus("alloc_idx", a), depth, "alloc")
    df = net.decode(_bus("free_idx", a), depth, "free")
    keep_reset = net.inv("reset")
    for i in range(depth):
        nxt = net.and2(keep_reset, net.and2(net.inv(df[i]), net.or2(da[i], valid[i])))
        net.lines.append(f"  assign {vd[i]} = {nxt};")
        for j in range(depth):
            net.lines.append(
                f"  assign {d[i][j]} = {net.mux(da[i], older[i][j], valid[j])};"
            )
    req = _bus("req", depth)
    rv = [net.and2(req[j], valid[j]) for j in range(depth)]
    for g in range(depth):
        blocked = net.tree(
            net.or2, [net.and2(older[g][j], rv[j]) for j in range(depth)]
        )
        net.lines.append(
            f"  assign oldest[{g}] = {net.and2(req[g], net.inv(blocked))};"
        )
    return ports


KINDS = {"flags": flags, "counter": counter, "cam": cam, "agematrix": agematrix}


def module(kind, depth, width):
    net = Netlist()
    ports = KINDS[kind](net, depth, width)
    decl = ",\n".join(
        f"  {direction} {'[%d:0] ' % (w - 1) if w > 1 else ''}{name}"
        for direction, w, name in ports
    )
    net.buffer()
    net.size()
    body = net.verilog()
    return "\n".join([f"module Arr(\n{decl}\n);"] + body + ["endmodule", ""])


def main():
    kind, depth, width, out = (
        sys.argv[1],
        int(sys.argv[2]),
        int(sys.argv[3]),
        sys.argv[4],
    )
    with open(out, "w") as f:
        f.write(module(kind, depth, width))


if __name__ == "__main__":
    main()
