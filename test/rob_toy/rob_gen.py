"""The toy Rob's RobState as a structural asap7 netlist: synthesis maps
nothing.

The same ports and update rules as rob_toy.py's RobState, built the way
a generator would: every indexed channel decoded once and shared by all
entries, the redirect's circular range from two thermometers, Mux1H
reductions as AND-OR trees, the banked line read of Rob.scala's
robBanks read.

    rob_gen.py <out.v> key=value...   (the keys of rob_toy.py)
"""

import math
import sys

from rob_toy import DEFAULTS, DEST, ITYPE, NONTAKEN, TAKEN, UOPNUM, WBCNT
from structgen import Netlist


class Net(Netlist):
    # the inverting form of a cell, to drive a flop's D with the
    # complement so that its QN is the true value
    _NEG = {
        "AO22x1": "AOI22x1",
        "AO222x2": "AOI222xp33",
        "AND2x2": "NAND2xp5",
        "OR2x2": "NOR2xp33",
        "OR3x1": "NOR3xp33",
        "OR4x1": "NOR4xp25",
        "XOR2xp5": "XNOR2xp5",
        "XNOR2xp5": "XOR2xp5",
    }

    def __init__(self):
        super().__init__()
        self._inv = {}
        self.uses = {}
        self.driver = {}

    def cell(self, master, **pins):
        for v in pins.values():
            self.uses[v] = self.uses.get(v, 0) + 1
        out = super().cell(master, **pins)
        self.driver[out] = (len(self.lines) - 1, master)
        return out

    def ff_n(self, d):
        """A flop whose QN is the register's value: d is its complement."""
        out = self.wire()
        self.lines.append(
            f"  DFFHQNx1_ASAP7_75t_R c{self.n} (.CLK(clock), .D({d}), .QN({out}));"
        )
        return out

    def negate(self, x):
        """~x: x's own cell turned into its inverting form when nothing
        else reads x, else an inverter."""
        if x == self.zero:
            return self.one
        if x == self.one:
            return self.zero
        for a, out in self._inv.items():
            if out == x:
                return a
        k, master = self.driver.get(x, (None, None))
        if self.uses.get(x, 0) == 0 and master in self._NEG:
            line = self.lines[k]
            self.lines[k] = line.replace(
                f"{master}_ASAP7", f"{self._NEG[master]}_ASAP7", 1
            )
            self.uses[x] = 1
            return x
        return self.inv(x)

    def inv(self, a):
        if a not in self._inv:
            self._inv[a] = super().inv(a)
        return self._inv[a]

    def mux(self, s, a, b):
        """s ? b : a"""
        if s == self.zero:
            return a
        if s == self.one:
            return b
        if a == b:
            return a
        return self.cell("AO22x1", A1=s, A2=b, B1=self.inv(s), B2=a)

    def decode(self, bits, n, en=None):
        """One-hot of an index, LSB-first bits, gated by en: the low and
        high halves predecoded (en folded into the low half), one AND2
        per output."""
        if len(bits) < 3:
            return super().decode(bits, n, en)
        h = len(bits) // 2
        lo = super().decode(bits[:h], 1 << h, en)
        hi = super().decode(bits[h:], 1 << (len(bits) - h))
        return [self.and2(lo[i & ((1 << h) - 1)], hi[i >> h]) for i in range(n)]

    def or_tree(self, xs):
        """OR4, OR3 and OR2 cells: fewer instances than a tree of OR2."""
        xs = [x for x in xs if x != self.zero]
        if self.one in xs:
            return self.one
        if not xs:
            return self.zero
        while len(xs) > 1:
            nxt = []
            for k in range(0, len(xs), 4):
                g = xs[k : k + 4]
                if len(g) == 1:
                    nxt.append(g[0])
                elif len(g) == 2:
                    nxt.append(self.cell("OR2x2", A=g[0], B=g[1]))
                else:
                    pins = dict(zip("ABCD", g))
                    nxt.append(self.cell(f"OR{len(g)}x1", **pins))
            xs = nxt
        return xs[0]

    def and_or(self, sels, words):
        """Mux1H: per bit the OR of sel & word."""
        width = len(words[0])
        out = []
        for b in range(width):
            terms = []
            pairs = list(zip(sels, [w[b] for w in words]))
            for k in range(0, len(pairs), 3):
                g = pairs[k : k + 3]
                if len(g) == 3:
                    (s0, d0), (s1, d1), (s2, d2) = g
                    terms.append(
                        self.cell("AO222x2", A1=s0, A2=d0, B1=s1, B2=d1, C1=s2, C2=d2)
                    )
                elif len(g) == 2:
                    (s0, d0), (s1, d1) = g
                    terms.append(self.cell("AO22x1", A1=s0, A2=d0, B1=s1, B2=d1))
                else:
                    terms.append(self.and2(*g[0]))
            out.append(self.or_tree(terms))
        return out

    def full_add(self, a, b, c):
        """One FAx1, whose outputs are inverted: (sum, carry)."""
        con, sn = self.wire(), self.wire()
        self.lines.append(
            f"  FAx1_ASAP7_75t_R c{self.n} (.A({a}), .B({b}), .CI({c}),"
            f" .CON({con}), .SN({sn}));"
        )
        return self.inv(sn), self.inv(con)

    def add(self, xs, ys):
        """Ripple xs + ys, truncated to len(xs)."""
        out, carry = [], self.zero
        for k, x in enumerate(xs):
            y = ys[k] if k < len(ys) else self.zero
            if carry == self.zero and y == self.zero:
                out.append(x)
                continue
            if carry == self.zero:
                out.append(self.xor2(x, y))
                carry = self.and2(x, y)
            else:
                s, carry = self.full_add(x, y, carry)
                out.append(s)
        return out

    def sub(self, xs, ys):
        """xs - ys: xs + ~ys + 1, truncated to len(xs)."""
        out, carry = [], self.one
        for k, x in enumerate(xs):
            y = self.inv(ys[k]) if k < len(ys) else self.one
            s, carry = self.full_add_c(x, y, carry)
            out.append(s)
        return out

    def full_add_c(self, a, b, c):
        if b == self.one and c == self.one:
            return a, self.one
        if b == self.one:
            return self.inv(self.xor2(a, c)), self.or2(a, c)
        if c == self.one:
            return self.xnor2(a, b), self.or2(a, b)
        return self.full_add(a, b, c)

    def popcount(self, bits, width):
        """Wallace-style: column sums of full adders, width bits out."""
        cols = [list(bits)] + [[] for _ in range(width)]
        out = []
        for k in range(width):
            col = cols[k]
            while len(col) > 2:
                s, c = self.full_add(col.pop(), col.pop(), col.pop())
                col.insert(0, s)
                cols[k + 1].append(c)
            if len(col) == 2:
                a, b = col
                col[:] = [self.xor2(a, b)]
                cols[k + 1].append(self.and2(a, b))
            out.append(col[0] if col else self.zero)
        return out

    def eq_const(self, bits, value):
        return self.tree(
            self.and2,
            [b if value >> k & 1 else self.inv(b) for k, b in enumerate(bits)],
        )


def _bus(name, w):
    return [f"{name}[{i}]" if w > 1 else name for i in range(w)]


def generate(p):
    net = Net()
    n = p["entries"]
    a = max(1, math.ceil(math.log2(n)))
    nb = p["commit"]
    bb = max(1, math.ceil(math.log2(nb)))
    lines_ = n // nb
    P = p["payload"]

    def dec(idx, en):
        return net.decode(_bus(idx, a), n, en)

    lb = max(1, math.ceil(math.log2(lines_)))
    dw = max(1, math.ceil(math.log2(p["enq"] + 1)))
    B = range(nb)
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
    # the redirect's range: i > begin and i < end, from thermometers
    ge_b = net.prefix(net.or2, net.decode(_bus("redirect_begin", a), n))
    oh_e = net.decode(_bus("redirect_end", a), n)
    ge_e = net.prefix(net.or2, oh_e)
    gt_b = [net.zero] + ge_b[:-1]
    end_gt_begin = net.or_tree([net.and2(oh_e[i], gt_b[i]) for i in range(n)])
    flush_en = "redirect_valid_reg"
    keep = net.inv("redirect_valid")

    # registers: (values, D wires) per field, LSB first
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
    q, d = {}, {}
    for name, w in fields:
        d[name] = [[net.wire() for _ in range(w)] for _ in range(n)]
        q[name] = [[net.ff_n(d[name][i][b]) for b in range(w)] for i in range(n)]

    def assign(dst, src):
        net.lines.append(f"  assign {dst} = {src};")

    def assign_d(dst, nxt):
        # the flop holds the complement of what it is given
        assign(dst, net.negate(nxt))

    for i in range(n):
        valid = q["valid"][i][0]
        lt_e = net.inv(ge_e[i])
        in_range = net.mux(
            end_gt_begin, net.or2(gt_b[i], lt_e), net.and2(gt_b[i], lt_e)
        )
        flush = net.and2(flush_en, net.or2(in_range, "redirect_all"))
        b, l = i % nb, i // nb
        hit = enq_line[b][l]
        enq_oh = net.and2(f"enq{b}_alloc", hit)
        commit_cond = commit_line[b][l]
        inst_enq = net.and2(f"enq{b}_inst", hit)
        uop_enq = net.and2(f"enq{b}_uop", hit)
        first_enq = net.and2(net.inv(valid), inst_enq)
        nvalid = net.and2(
            net.inv(commit_cond),
            net.or2(net.and2(enq_oh, keep), net.and2(net.inv(flush), valid)),
        )
        assign_d(d["valid"][i][0], nvalid)

        dest_enq = [net.and2(uop_enq, x) for x in _bus(f"enq{b}_dest", dw)]
        ds = q["destsize"][i]
        acc = net.add(ds, dest_enq)
        upd = net.and2(valid, uop_enq)
        for b in range(DEST):
            v = net.mux(upd, ds[b], acc[b])
            v = net.mux(first_enq, v, dest_enq[b] if b < len(dest_enq) else net.zero)
            assign_d(d["destsize"][i][b], v)

        flush_wb = net.or_tree([exc[x][i] for x in range(p["exc"])])
        nf = q["needflush"][i][0]
        v = net.mux(valid, nf, net.or2(nf, flush_wb))
        assign_d(d["needflush"][i][0], net.and2(net.inv(first_enq), v))

        numwb = _bus(f"enq{b}_numwb", UOPNUM)
        wbcnt = net.and_or(
            [wb[w][i] for w in range(p["wb"])],
            [_bus(f"wb{w}_cnt", WBCNT) for w in range(p["wb"])],
        )
        un = q["uopnum"][i]
        down = net.sub(un, wbcnt)
        for b in range(UOPNUM):
            v = net.mux(valid, net.mux(inst_enq, un[b], numwb[b]), down[b])
            assign_d(d["uopnum"][i][b], v)

        ffres = net.and_or(
            [ff[f][i] for f in range(p["ff"])],
            [_bus(f"ff{f}_flags", 5) for f in range(p["ff"])],
        )
        for b in range(5):
            v = net.or2(q["fflags"][i][b], ffres[b])
            assign_d(d["fflags"][i][b], net.and2(net.inv(first_enq), v))
        vxres = net.or_tree([vx[k][i] for k in range(p["vx"])])
        v = net.or2(q["vxsat"][i][0], vxres)
        assign_d(d["vxsat"][i][0], net.and2(net.inv(first_enq), v))

        it = q["itype"][i]
        enq_itype = _bus(f"enq{b}_itype", ITYPE)
        taken = net.or_tree([br[k][i] for k in range(p["br"])])
        settaken = net.and2(net.and2(valid, net.eq_const(it, NONTAKEN)), taken)
        for b in range(ITYPE):
            v = net.mux(settaken, it[b], net.one if TAKEN >> b & 1 else net.zero)
            assign_d(d["itype"][i][b], net.mux(first_enq, v, enq_itype[b]))

        pl = q["payload"][i]
        data = _bus(f"enq{b}_payload", P)
        for k in range(P):
            assign_d(d["payload"][i][k], net.mux(enq_oh, pl[k], data[k]))

    # robBanks: per bank, this line and the next at the one-hot line
    rec = [sum((q[name][i] for name, _ in fields), []) for i in range(n)]
    oh = _bus("rd_line_oh", lines_)
    for side, shift in (("this", 0), ("next", 1)):
        for b in range(nb):
            words = [rec[((l + shift) % lines_) * nb + b] for l in range(lines_)]
            for k, v in enumerate(net.and_or(oh, words)):
                assign(f"{side}{b}_entry[{k}]", v)
    return net


def main(argv):
    from rob_toy import structure

    out = argv[1]
    p = dict(DEFAULTS)
    for kv in argv[2:]:
        k, v = kv.split("=")
        p[k] = int(v)
    ports, _ = structure(p)
    net = generate(p)
    body = [f"  wire {w};" for w in net.wires] + net.lines
    with open(out, "w") as f:
        f.write(
            "\n".join(
                ["module RobState("]
                + [",\n".join("  " + x for x in ports), ");"]
                + body
                + ["endmodule", ""]
            )
        )


if __name__ == "__main__":
    main(sys.argv)
