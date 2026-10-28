"""The toy Rob's RobState as a structural asap7 netlist: synthesis maps
nothing.

The same ports and update rules as rob_toy.py's RobState, built the way
a generator would:

- every indexed channel decoded once, shared by all entries: up to three
  predecoded groups as NAND lines, one NOR per entry;
- the redirect's circular range from the pointers' bits: end > begin by
  a comparator tree, i > begin and i < end per entry from thermometers
  of the pointers' halves;
- trees of inverting cells (AOI222, NAND, NOR in alternation), each
  cell's drive strength chosen from its fanout, as a mapper would;
- every net within the flow's set_max_fanout (FANOUT, 32): more sinks
  are driven through a buffer tree, grouped in the order they were
  made, which is entry order, each buffer sized for its load;
- every cell named after the entry it belongs to, b<bank>_l<line>_c<n>,
  or g_c<n> for the shared logic, so place.tcl can place the entries by
  construction: a column per bank, the lines in order up the column.

    rob_gen.py <out.v> key=value...   (the keys of rob_toy.py)
"""

import math
import re
import sys

from rob_toy import DEFAULTS, DEST, ITYPE, NONTAKEN, TAKEN, UOPNUM, WBCNT

_V = "_ASAP7_75t_R"
# the flow's set_max_fanout (constraint.sdc, as XiangShan's): every net
# the generator makes stays within it, so repair_design has nothing to add
FANOUT = 32

# the inverting form of a cell whose only reader is a flop's D, which
# takes the complement (see Net.negate)
_NEG = {
    "AO22x1": "AOI22xp5",
    "AO21x1": "AOI21x1",
    "AND2x2": "NAND2xp5",
    "OR2x2": "NOR2xp33",
    "NAND2xp5": "AND2x2",
    "NOR2xp33": "OR2x2",
    "XOR2xp5": "XNOR2xp5",
    "XNOR2xp5": "XOR2xp5",
}
_NAND = {2: "NAND2xp5", 3: "NAND3xp33", 4: "NAND4xp25", 5: "NAND5xp2"}
# drive strengths by fanout: one load, two or three, more
_SIZES = {
    "INVx1": ["INVx1", "INVx2", "INVx3"],
    "NAND2xp5": ["NAND2xp5", "NAND2x1", "NAND2x1p5"],
    "NAND3xp33": ["NAND3xp33", "NAND3x1", "NAND3x2"],
    "NAND4xp25": ["NAND4xp25", "NAND4xp75", "NAND4xp75"],
    "NOR2xp33": ["NOR2xp33", "NOR2x1", "NOR2x1p5"],
    "NOR3xp33": ["NOR3xp33", "NOR3x1", "NOR3x2"],
    "NOR4xp25": ["NOR4xp25", "NOR4xp75", "NOR4xp75"],
    "AND2x2": ["AND2x2", "AND2x4", "AND2x4"],
    "OR2x2": ["OR2x2", "OR2x4", "OR2x4"],
    "AO21x1": ["AO21x1", "AO21x2", "AO21x2"],
    "AO22x1": ["AO22x1", "AO22x2", "AO22x2"],
    "AOI22xp5": ["AOI22xp5", "AOI22x1", "AOI22x1"],
    "XOR2xp5": ["XOR2xp5", "XOR2x1", "XOR2x2"],
    "XNOR2xp5": ["XNOR2xp5", "XNOR2x1", "XNOR2x2"],
    "BUFx4f": ["BUFx4f", "BUFx4f", "BUFx6f"],
}
_NOR = {2: "NOR2xp33", 3: "NOR3xp33", 4: "NOR4xp25", 5: "NOR5xp2"}


def _bus_conns(pins, outs):
    """A module instance's connections, bit pins gathered into buses."""
    buses, conns = {}, []
    for p, v in list(pins.items()) + list(outs.items()):
        m = re.match(r"(\w+)\[(\d+)\]$", p)
        if m:
            buses.setdefault(m.group(1), {})[int(m.group(2))] = v
        else:
            conns.append(f".{p}({v})")
    for name, bits in buses.items():
        conns.append(
            f".{name}({{{', '.join(bits[k] for k in sorted(bits, reverse=True))}}})"
        )
    return ", ".join(conns)


class Net:
    def __init__(self):
        self.zero = "1'b0"
        self.one = "1'b1"
        self.cells = []  # [master, tag, {pin: net}, {pin: net}]
        self.assigns = []  # (dst, src)
        self.wires = []
        self.n = 0
        self.tag = "g"
        self._inv = {}
        self._inv_of = {}
        self.driver = {}  # net: (cell index, pin)
        self.uses = {}

    def wire(self):
        self.n += 1
        w = f"n{self.n}"
        self.wires.append(w)
        return w

    def cell(self, master, outs=("Y",), **pins):
        for v in pins.values():
            self.uses[v] = self.uses.get(v, 0) + 1
        o = {p: self.wire() for p in outs}
        self.cells.append([master, self.tag, pins, o])
        for p, w in o.items():
            self.driver[w] = (len(self.cells) - 1, p)
        return o[outs[0]] if len(outs) == 1 else [o[p] for p in outs]

    def assign(self, dst, src):
        self.uses[src] = self.uses.get(src, 0) + 1
        self.assigns.append((dst, src))

    def ff_n(self, d):
        """A flop whose QN is the register's value: d is its complement."""
        return self.cell("DFFHQNx1", outs=("QN",), CLK="clock", D=d)

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

    def negate(self, x):
        """~x for a flop's D: x's own cell turned into its inverting form
        when nothing else reads x, else an inverter."""
        if x in self._inv_of:
            return self._inv_of[x]
        if x in (self.zero, self.one):
            return self.inv(x)
        k, _ = self.driver.get(x, (None, None))
        if k is not None and self.uses.get(x, 0) == 0:
            master = self.cells[k][0]
            if master in _NEG:
                self.cells[k][0] = _NEG[master]
                return x
        return self.inv(x)

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

    def xor2(self, a, b):
        return self.cell("XOR2xp5", A=a, B=b)

    def xnor2(self, a, b):
        return self.cell("XNOR2xp5", A=a, B=b)

    def nand(self, xs):
        xs = [x for x in xs if x != self.one]
        if self.zero in xs:
            return self.one
        if len(xs) == 1:
            return self.inv(xs[0])
        return self.cell(_NAND[len(xs)], **dict(zip("ABCDE", xs)))

    def nor(self, xs):
        xs = [x for x in xs if x != self.zero]
        if self.one in xs:
            return self.zero
        if len(xs) == 1:
            return self.inv(xs[0])
        return self.cell(_NOR[len(xs)], **dict(zip("ABCDE", xs)))

    def mux(self, s, a, b):
        """s ? b : a"""
        if s == self.zero or a == b:
            return a
        if s == self.one:
            return b
        if b == self.one:
            return self.or2(s, a)
        if b == self.zero:
            return self.and2(self.inv(s), a)
        return self.cell("AO22x1", A1=s, A2=b, B1=self.inv(s), B2=a)

    def ao21(self, a1, a2, b):
        """a1 & a2 | b"""
        return self.cell("AO21x1", A1=a1, A2=a2, B=b)

    def or_tree(self, xs):
        """OR of xs: NOR and NAND levels in alternation."""
        xs = [x for x in xs if x != self.zero]
        if self.one in xs:
            return self.one
        if not xs:
            return self.zero
        return self._or_pos(xs)

    def _or_pos(self, xs):
        if len(xs) == 1:
            return xs[0]
        if len(xs) <= 4:
            return self.inv(self.nor(xs))
        return self._or_neg([self.nor(xs[k : k + 4]) for k in range(0, len(xs), 4)])

    def _or_neg(self, ns):
        """OR of the complements of ns."""
        if len(ns) <= 4:
            return self.nand(ns)
        return self._or_pos([self.nand(ns[k : k + 4]) for k in range(0, len(ns), 4)])

    def and_or(self, sels, words, tags=None):
        """Mux1H: per bit the OR of sel & word, AOI222 then NAND/NOR; with
        tags, each AOI is made under the tag of its first word, so it is
        placed with that word, and each bit's OR tree under one of them in
        turn."""
        out = []
        for b in range(len(words[0])):
            pairs = [(s, w[b]) for s, w in zip(sels, words)]
            ptags = tags or [self.tag] * len(pairs)
            ptags = [t for (s, d), t in zip(pairs, ptags) if self.zero not in (s, d)]
            pairs = [(s, d) for s, d in pairs if self.zero not in (s, d)]
            saved = self.tag
            if not pairs:
                out.append(self.zero)
                continue
            ns = []
            for k in range(0, len(pairs), 3):
                g = pairs[k : k + 3]
                self.tag = ptags[k]
                pins = {}
                for (s, d), p in zip(g, "ABC"):
                    pins[p + "1"], pins[p + "2"] = s, d
                ns.append(
                    self.cell(
                        {1: "NAND2xp5", 2: "AOI22xp5", 3: "AOI222xp33"}[len(g)],
                        **(pins if len(g) > 1 else {"A": g[0][0], "B": g[0][1]}),
                    )
                )
            # the OR tree that joins a bit's AOIs, with one of its lines
            self.tag = ptags[b % len(ptags)] if tags and ptags else saved
            out.append(self._or_neg(ns))
            self.tag = saved
        return out

    def add_c(self, xs, ys, cin):
        """xs + ys + cin, truncated to len(xs): generate and propagate per
        bit, the carries by a Sklansky prefix of AO21s, log2 levels."""
        n = len(xs)
        ys = list(ys) + [self.zero] * (n - len(ys))
        g = [self.and2(x, y) for x, y in zip(xs, ys)]
        p = [x if y == self.zero else self.xor2(x, y) for x, y in zip(xs, ys)]
        # (G, P) of bits [0..k], cin folded into bit 0's generate
        G = list(g)
        P = list(p)
        # bit 0's carry out, majority(x, y, cin), straight from its inputs
        if cin == self.one:
            G[0] = self.or2(xs[0], ys[0])
        elif cin != self.zero:
            G[0] = self.ao21(cin, self.or2(xs[0], ys[0]), g[0])
        step = 1
        while step < n:
            for k in range(n):
                if (k // step) % 2 == 1:
                    j = (k // step) * step - 1
                    G[k], P[k] = self._gp(G[k], P[k], G[j], P[j])
            step *= 2
        carry = [cin] + G[:-1]
        return [self._xor_c(p[k], carry[k]) for k in range(n)]

    def _gp(self, gh, ph, gl, pl):
        """(G, P) of a high span over a low one."""
        if ph == self.zero or gl == self.zero:
            g = gh
        elif gh == self.zero:
            g = self.and2(ph, gl)
        else:
            g = self.ao21(ph, gl, gh)
        return g, self.and2(ph, pl)

    def _xor_c(self, a, b):
        if b == self.zero:
            return a
        if b == self.one:
            return self.inv(a)
        return self.xor2(a, b)

    def add(self, xs, ys):
        """xs + ys, truncated to len(xs)."""
        return self.add_c(xs, ys, self.zero)

    def sub(self, xs, ys):
        """xs - ys, truncated to len(xs): xs + ~ys + 1, ys zero-extended."""
        nys = [self.inv(y) for y in ys] + [self.one] * (len(xs) - len(ys))
        return self.add_c(xs, nys, self.one)

    def eq_const(self, bits, value):
        lits = [b if value >> k & 1 else self.inv(b) for k, b in enumerate(bits)]
        return self.inv(self.nand(lits))

    def predecode_n(self, bits, en=None):
        """The complement of every value's line: one NAND each."""
        extra = [en] if en is not None else []
        return [
            self.nand(
                [b if v >> k & 1 else self.inv(b) for k, b in enumerate(bits)] + extra
            )
            for v in range(1 << len(bits))
        ]

    def decode(self, bits, n, en=None):
        """One-hot of an index, LSB-first bits, gated by en: up to three
        predecoded groups of at most three bits (NAND lines, en folded
        into the first), one NOR per output."""
        if len(bits) == 1:
            lines = [self.inv(bits[0]), bits[0]]
            return [self.and2(x, en) if en is not None else x for x in lines][:n]
        k = max(2, -(-len(bits) // 3))
        cuts = list(range(0, len(bits), k))
        groups = [
            self.predecode_n(bits[c : c + k], en if g == 0 else None)
            for g, c in enumerate(cuts)
        ]
        out = []
        for i in range(n):
            out.append(
                self.nor(
                    [
                        grp[(i >> c) & ((1 << len(bits[c : c + k])) - 1)]
                        for grp, c in zip(groups, cuts)
                    ]
                )
            )
        return out

    def gt(self, xs, ys):
        """xs > ys, unsigned, by a tree of (greater, equal) pairs."""
        pairs = [(self.and2(x, self.inv(y)), self.xnor2(x, y)) for x, y in zip(xs, ys)]
        while len(pairs) > 1:
            nxt = []
            for k in range(0, len(pairs) - 1, 2):
                (gl, el), (gh, eh) = pairs[k], pairs[k + 1]
                nxt.append((self.ao21(eh, gl, gh), self.and2(eh, el)))
            if len(pairs) % 2:
                nxt.append(pairs[-1])
            pairs = nxt
        return pairs[0][0]

    def thermo(self, bits, n, greater):
        """Per i < n: i > value (greater) or i < value, from the halves:
        hi(i) beyond hi(v), or hi(i) == hi(v) and lo(i) beyond lo(v)."""
        h = len(bits) // 2 or 1
        lo_b, hi_b = bits[:h], bits[h:]

        def side(bs):
            oh = [self.inv(x) for x in self.predecode_n(bs)]
            # beyond[v] = v > value (or v < value): an OR prefix of the one-hot
            m = len(oh)
            beyond = []
            for v in range(m):
                below = oh[:v] if greater else oh[v + 1 :]
                beyond.append(self.or_tree(below))
            return oh, beyond

        oh_lo, by_lo = side(lo_b)
        if not hi_b:
            return by_lo[:n]
        oh_hi, by_hi = side(hi_b)
        mask = (1 << h) - 1
        return [
            self.ao21(oh_hi[i >> h], by_lo[i & mask], by_hi[i >> h]) for i in range(n)
        ]

    def buffer(self):
        """Every net with more than FANOUT cell sinks drives them through
        buffers, FANOUT sinks each, in the order the sinks were made."""
        sinks = {}
        for k, (_, _, pins, _) in enumerate(self.cells):
            for p, v in pins.items():
                if v not in (self.zero, self.one, "clock"):
                    sinks.setdefault(v, []).append((k, p))
        for net, ss in list(sinks.items()):
            limit = FANOUT
            while len(ss) > limit:
                groups = [ss[k : k + limit] for k in range(0, len(ss), limit)]
                ss = []
                for g in groups:
                    saved = self.tag
                    self.tag = self.cells[g[0][0]][1]
                    out = self.wire()
                    self.cells.append(["BUFx4f", self.tag, {"A": net}, {"Y": out}])
                    self.tag = saved
                    for k, p in g:
                        self.cells[k][2][p] = out
                    ss.append((len(self.cells) - 1, "A"))

    def size(self):
        """Each cell's drive strength from its fanout, as a mapper would
        choose: the smallest variant for one load, larger for more."""
        fanout = {}
        for _, _, pins, _ in self.cells:
            for v in pins.values():
                fanout[v] = fanout.get(v, 0) + 1
        for c in self.cells:
            sizes = _SIZES.get(c[0])
            if not sizes:
                continue
            fo = max(fanout.get(w, 0) for w in c[3].values())
            if c[0] == "BUFx4f":
                # a buffer drives up to FANOUT sinks
                c[0] = "BUFx4f" if fo <= 8 else "BUFx6f" if fo <= 16 else "BUFx12f"
            else:
                c[0] = sizes[0 if fo <= 1 else 1 if fo <= 3 else 2]

    def verilog(self):
        lines = [f"  wire {w};" for w in self.wires]
        for k, (master, tag, pins, outs) in enumerate(self.cells):
            if master == "RobEntry":
                lines.append(f"  RobEntry {tag}_c{k} ({_bus_conns(pins, outs)});")
                continue
            conns = ", ".join(
                f".{p}({v})" for p, v in list(pins.items()) + list(outs.items())
            )
            lines.append(f"  {master}{_V} {tag}_c{k} ({conns});")
        lines += [f"  assign {d} = {s};" for d, s in self.assigns]
        return lines


REC_BITS = 2 + UOPNUM + DEST + 5 + 1 + ITYPE


def entry_rtl(p):
    """RobEntry: one entry's state and update rules as RTL, its hits
    decoded outside, so synthesis maps one definition once (kept by
    SYNTH_KEEP_MODULES) and the generator instantiates it per entry."""
    W, X, F, V, Bn, P = p["wb"], p["exc"], p["ff"], p["vx"], p["br"], p["payload"]
    dw = max(1, math.ceil(math.log2(p["enq"] + 1)))
    return f"""module RobEntry(
  input clock, input hit, input enq_alloc, input enq_inst, input enq_uop,
  input [{dw-1}:0] enq_dest, input [{UOPNUM-1}:0] enq_numwb,
  input [{ITYPE-1}:0] enq_itype, input [{P-1}:0] enq_payload,
  input commit_hit, input gt_b, input lt_e, input end_gt_begin,
  input redirect_all, input redirect_valid, input redirect_valid_reg,
  input [{W-1}:0] wb_hit, input [{W*WBCNT-1}:0] wb_cnt,
  input [{X-1}:0] exc_hit, input [{F-1}:0] ff_hit, input [{F*5-1}:0] ff_flags,
  input [{V-1}:0] vx_hit, input [{Bn-1}:0] br_hit,
  output [{REC_BITS+P-1}:0] rec);
  reg valid, needflush, vxsat;
  reg [{UOPNUM-1}:0] uopnum;
  reg [{DEST-1}:0] destsize;
  reg [4:0] fflags;
  reg [{ITYPE-1}:0] itype;
  reg [{P-1}:0] payload;
  wire enq_oh = enq_alloc & hit;
  wire inst_enq = enq_inst & hit;
  wire uop_enq = enq_uop & hit;
  wire in_range = end_gt_begin ? (gt_b & lt_e) : (gt_b | lt_e);
  wire flush = redirect_valid_reg & (in_range | redirect_all);
  wire first_enq = !valid & inst_enq;
  wire [{DEST-1}:0] dest_enq = uop_enq ? {DEST}'(enq_dest) : {DEST}'d0;
  reg [{WBCNT-1}:0] wbcnt;
  reg [4:0] ff_res;
  integer k;
  always @* begin
    wbcnt = {WBCNT}'d0;
    for (k = 0; k < {W}; k = k + 1)
      wbcnt = wbcnt | ({{{WBCNT}{{wb_hit[k]}}}} & wb_cnt[k*{WBCNT} +: {WBCNT}]);
    ff_res = 5'd0;
    for (k = 0; k < {F}; k = k + 1)
      ff_res = ff_res | ({{5{{ff_hit[k]}}}} & ff_flags[k*5 +: 5]);
  end
  wire flush_wb = |exc_hit;
  wire vx_res = |vx_hit;
  wire taken = |br_hit;
  always @(posedge clock) begin
    if (commit_hit) valid <= 1'b0;
    else if (enq_oh & !redirect_valid) valid <= 1'b1;
    else if (flush) valid <= 1'b0;
    if (first_enq) destsize <= dest_enq;
    else if (valid & uop_enq) destsize <= destsize + dest_enq;
    if (first_enq) needflush <= 1'b0;
    else if (valid) needflush <= needflush | flush_wb;
    if (valid & (needflush | flush_wb)) uopnum <= uopnum - wbcnt;
    else if (!valid & inst_enq) uopnum <= enq_numwb;
    else if (valid) uopnum <= uopnum - wbcnt;
    if (first_enq) fflags <= 5'd0;
    else if (|ff_res) fflags <= fflags | ff_res;
    if (first_enq) vxsat <= 1'b0;
    else if (vx_res) vxsat <= 1'b1;
    if (first_enq) itype <= enq_itype;
    else if (valid & itype == {ITYPE}'d{NONTAKEN} & taken) itype <= {ITYPE}'d{TAKEN};
    if (enq_oh) payload <= enq_payload;
  end
  assign rec = {{valid, needflush, uopnum, destsize, fflags, vxsat, itype, payload}};
endmodule
"""


def _entries_rtl(net, p, enq_line, commit_line, wb, exc, ff, vx, br, gt_b, lt_e, egb):
    """One RobEntry instance per entry, its hits from the shared decoders."""
    n, nb, P = p["entries"], p["commit"], p["payload"]
    dw = max(1, math.ceil(math.log2(p["enq"] + 1)))
    rec = []
    for i in range(n):
        bk, ln = i % nb, i // nb
        net.tag = f"b{bk}_l{ln}"
        pins = {
            "clock": "clock",
            "hit": enq_line[bk][ln],
            "enq_alloc": f"enq{bk}_alloc",
            "enq_inst": f"enq{bk}_inst",
            "enq_uop": f"enq{bk}_uop",
            "commit_hit": commit_line[bk][ln],
            "gt_b": gt_b[i],
            "lt_e": lt_e[i],
            "end_gt_begin": egb,
            "redirect_all": "redirect_all",
            "redirect_valid": "redirect_valid",
            "redirect_valid_reg": "redirect_valid_reg",
        }
        for name, w in (
            ("dest", dw),
            ("numwb", UOPNUM),
            ("itype", ITYPE),
            ("payload", P),
        ):
            for k, v in enumerate(_bus(f"enq{bk}_{name}", w)):
                pins[f"enq_{name}[{k}]"] = v
        for w in range(p["wb"]):
            pins[f"wb_hit[{w}]"] = wb[w][i]
            for k, v in enumerate(_bus(f"wb{w}_cnt", WBCNT)):
                pins[f"wb_cnt[{w * WBCNT + k}]"] = v
        for x in range(p["exc"]):
            pins[f"exc_hit[{x}]"] = exc[x][i]
        for f in range(p["ff"]):
            pins[f"ff_hit[{f}]"] = ff[f][i]
            for k, v in enumerate(_bus(f"ff{f}_flags", 5)):
                pins[f"ff_flags[{f * 5 + k}]"] = v
        for v in range(p["vx"]):
            pins[f"vx_hit[{v}]"] = vx[v][i]
        for b in range(p["br"]):
            pins[f"br_hit[{b}]"] = br[b][i]
        outs = tuple(f"rec[{k}]" for k in range(REC_BITS + P))
        rec.append(net.cell("RobEntry", outs=outs, **pins))
    return rec


def _bus(name, w):
    return [f"{name}[{i}]" if w > 1 else name for i in range(w)]


def generate(p):
    net = Net()
    n = p["entries"]
    a = max(1, math.ceil(math.log2(n)))
    nb = p["commit"]
    lines_ = n // nb
    lb = max(1, math.ceil(math.log2(lines_)))
    dw = max(1, math.ceil(math.log2(p["enq"] + 1)))
    P = p["payload"]
    B = range(nb)

    def dec(idx, en):
        return net.decode(_bus(idx, a), n, en)

    # by bank: one line decode per bank port, shared by the bank's entries
    enq_line = [net.decode(_bus(f"enq{b}_line", lb), lines_) for b in B]
    commit_line = [
        net.decode(_bus(f"commit{b}_line", lb), lines_, f"commit{b}_valid") for b in B
    ]
    wb = [dec(f"wb{w}_idx", f"wb{w}_valid") for w in range(p["wb"])]
    exc = [
        dec(f"exc{x}_idx", net.and2(f"exc{x}_valid", f"exc{x}_flush"))
        for x in range(p["exc"])
    ]
    ff = [
        dec(f"ff{f}_idx", net.and2(f"ff{f}_valid", f"ff{f}_wen"))
        for f in range(p["ff"])
    ]
    vx = [
        dec(f"vx{v}_idx", net.and2(f"vx{v}_valid", f"vx{v}_sat"))
        for v in range(p["vx"])
    ]
    br = [
        dec(f"br{b}_idx", net.and2(f"br{b}_valid", f"br{b}_taken"))
        for b in range(p["br"])
    ]
    # the redirect's range from the pointers' bits
    begin, end = _bus("redirect_begin", a), _bus("redirect_end", a)
    end_gt_begin = net.gt(end, begin)
    gt_b = net.thermo(begin, n, greater=True)
    lt_e = net.thermo(end, n, greater=False)
    flush_en = "redirect_valid_reg"
    keep = net.inv("redirect_valid")

    def _entries_gates():
        # registers: (values, D wires) per field, LSB first; each entry's
        # flops are made with its logic, below, so they are placed with it
        fields = [
            ("payload", P),
            ("itype", ITYPE),
            ("vxsat", 1),
            ("fflags", 5),
            ("destsize", DEST),
            ("uopnum", UOPNUM),
            ("needflush", 1),
            ("valid", 1),
        ]
        q = {name: [None] * n for name, _ in fields}
        d = {name: [None] * n for name, _ in fields}
        for i in range(n):
            bk, ln = i % nb, i // nb
            net.tag = f"b{bk}_l{ln}"
            for name, w in fields:
                d[name][i] = [net.wire() for _ in range(w)]
                q[name][i] = [net.ff_n(x) for x in d[name][i]]

        def assign_d(dst, nxt):
            # the flop holds the complement of what it is given
            net.assign(dst, net.negate(nxt))

        for i in range(n):
            bk, ln = i % nb, i // nb
            net.tag = f"b{bk}_l{ln}"
            valid = q["valid"][i][0]
            in_range = net.mux(
                end_gt_begin, net.or2(gt_b[i], lt_e[i]), net.and2(gt_b[i], lt_e[i])
            )
            flush = net.and2(flush_en, net.or2(in_range, "redirect_all"))
            hit = enq_line[bk][ln]
            enq_oh = net.and2(f"enq{bk}_alloc", hit)
            commit_cond = commit_line[bk][ln]
            inst_enq = net.and2(f"enq{bk}_inst", hit)
            uop_enq = net.and2(f"enq{bk}_uop", hit)
            first_enq = net.and2(net.inv(valid), inst_enq)
            nvalid = net.and2(
                net.inv(commit_cond),
                net.or2(net.and2(enq_oh, keep), net.and2(net.inv(flush), valid)),
            )
            assign_d(d["valid"][i][0], nvalid)

            dest_enq = [net.and2(uop_enq, x) for x in _bus(f"enq{bk}_dest", dw)]
            ds = q["destsize"][i]
            acc = net.add(ds, dest_enq)
            upd = net.and2(valid, uop_enq)
            for k in range(DEST):
                v = net.mux(upd, ds[k], acc[k])
                v = net.mux(
                    first_enq, v, dest_enq[k] if k < len(dest_enq) else net.zero
                )
                assign_d(d["destsize"][i][k], v)

            flush_wb = net.or_tree([exc[x][i] for x in range(p["exc"])])
            nf = q["needflush"][i][0]
            v = net.mux(valid, nf, net.or2(nf, flush_wb))
            assign_d(d["needflush"][i][0], net.and2(net.inv(first_enq), v))

            numwb = _bus(f"enq{bk}_numwb", UOPNUM)
            wbcnt = net.and_or(
                [wb[w][i] for w in range(p["wb"])],
                [_bus(f"wb{w}_cnt", WBCNT) for w in range(p["wb"])],
            )
            un = q["uopnum"][i]
            down = net.sub(un, wbcnt)
            for k in range(UOPNUM):
                v = net.mux(valid, net.mux(inst_enq, un[k], numwb[k]), down[k])
                assign_d(d["uopnum"][i][k], v)

            ffres = net.and_or(
                [ff[f][i] for f in range(p["ff"])],
                [_bus(f"ff{f}_flags", 5) for f in range(p["ff"])],
            )
            for k in range(5):
                v = net.or2(q["fflags"][i][k], ffres[k])
                assign_d(d["fflags"][i][k], net.and2(net.inv(first_enq), v))
            vxres = net.or_tree([vx[k][i] for k in range(p["vx"])])
            v = net.or2(q["vxsat"][i][0], vxres)
            assign_d(d["vxsat"][i][0], net.and2(net.inv(first_enq), v))

            it = q["itype"][i]
            enq_itype = _bus(f"enq{bk}_itype", ITYPE)
            taken = net.or_tree([br[k][i] for k in range(p["br"])])
            settaken = net.and2(net.and2(valid, net.eq_const(it, NONTAKEN)), taken)
            for k in range(ITYPE):
                v = net.mux(settaken, it[k], net.one if TAKEN >> k & 1 else net.zero)
                assign_d(d["itype"][i][k], net.mux(first_enq, v, enq_itype[k]))

            pl = q["payload"][i]
            data = _bus(f"enq{bk}_payload", P)
            for k in range(P):
                assign_d(d["payload"][i][k], net.mux(enq_oh, pl[k], data[k]))
        return [sum((q[name][i] for name, _ in fields), []) for i in range(n)]

    if p.get("entry_rtl"):
        rec = _entries_rtl(
            net, p, enq_line, commit_line, wb, exc, ff, vx, br, gt_b, lt_e, end_gt_begin
        )
    else:
        rec = _entries_gates()

    # robBanks: per bank, this line and the next at the one-hot line; each
    # AOI of the read tree is made with the lines it reads, the OR tree
    # that joins them with the column's middle line
    oh = _bus("rd_line_oh", lines_)
    for side, shift in (("this", 0), ("next", 1)):
        for bk in range(nb):
            net.tag = f"b{bk}_l{lines_ // 2}"
            words = [rec[((l + shift) % lines_) * nb + bk] for l in range(lines_)]
            tags = [f"b{bk}_l{(l + shift) % lines_}" for l in range(lines_)]
            for k, v in enumerate(net.and_or(oh, words, tags)):
                net.assign(f"{side}{bk}_entry[{k}]", v)
    net.tag = "g"
    if not p.get("plain"):
        net.buffer()
        net.size()
    return net


def main(argv):
    from rob_toy import structure

    out = argv[1]
    p = dict(DEFAULTS)
    for kv in argv[2:]:
        k, v = kv.split("=")
        p[k] = int(v)
    ports, _ = structure({k: v for k, v in p.items() if k in DEFAULTS})
    net = generate(p)
    with open(out, "w") as f:
        f.write(
            "\n".join(
                ["module RobState("]
                + [",\n".join("  " + x for x in ports), ");"]
                + net.verilog()
                + ["endmodule", ""]
                + ([entry_rtl(p)] if p.get("entry_rtl") else [])
            )
        )


if __name__ == "__main__":
    main(sys.argv)
