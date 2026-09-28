#!/usr/bin/env python3
"""A random co-simulation testbench for a generated block and its RTL.

Writes a synthesizable Verilog module `cosim_tb` that drives the RTL
module (renamed `gold`) and the generated netlist (renamed `gate`) with
the same pseudo-random inputs from an LFSR and asserts every output
equal, for `yosys sim -assert`. A simulation, not an equivalence proof.

--equal A,B makes input B copy input A on half the cycles, and --zero A
makes input A zero on a quarter of them, so that rare conditions (a set
index match, a zero tag) are exercised.

--loaded-by 'PATTERN=VALID' compares an output matching the regular
expression PATTERN only once the output VALID (with PATTERN's groups
substituted) has been high: a register without a reset holds an
undefined value in both designs until it is first loaded. --warmup N
compares nothing for the first N cycles, for when outputs are buses too
coarse for --loaded-by.
"""

import argparse
import re


def ports(verilog, module):
    text = open(verilog).read()
    m = re.search(r"module\s+" + module + r"\s*\((.*?)\);", text, re.S)
    if not m:
        raise SystemExit("cosim_tb: no module %s in %s" % (module, verilog))
    out = []
    d, w = None, 1
    header = " ".join(l.split("//")[0] for l in m.group(1).split("\n"))
    for line in header.split(","):
        line = " ".join(line.split())
        if not line:
            continue
        mm = re.match(r"(input|output)\s*(\[(\d+):0\])?\s*(\w+)$", line)
        if mm:
            d = mm.group(1)
            w = int(mm.group(3)) + 1 if mm.group(3) else 1
            out.append((d, w, mm.group(4)))
        else:
            out.append((d, w, line))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rtl", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--clock", default="clock")
    ap.add_argument("--reset", default="reset")
    ap.add_argument("--equal", action="append", default=[])
    ap.add_argument("--zero", action="append", default=[])
    ap.add_argument("--loaded-by", action="append", default=[])
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ps = ports(a.rtl, a.module)
    ins = [(w, n) for d, w, n in ps if d == "input" and n not in (a.clock, a.reset)]
    outs = [(w, n) for d, w, n in ps if d == "output"]
    total = sum(w for w, _ in ins) + 8
    L = 1
    while L < total + 64:
        L *= 2
    o = ["module cosim_tb(input clock);"]
    o.append("  reg [%d:0] lfsr = %d'h%s;" % (L - 1, L, "5a" * (L // 8)))
    o.append("  reg [15:0] cycle = 0;")
    o.append("  always @(posedge clock) begin")
    o.append(
        "    lfsr <= {lfsr[%d:0], lfsr[%d] ^ lfsr[%d] ^ lfsr[%d] ^ lfsr[%d]};"
        % (L - 2, L - 1, L - 3, L // 2, 1)
    )
    o.append("    if (cycle != 16'hffff) cycle <= cycle + 1;")
    o.append("  end")
    o.append("  wire reset = cycle < 2;")
    bit = 8
    names = {}
    for w, n in ins:
        o.append("  wire [%d:0] r_%s = lfsr[%d:%d];" % (w - 1, n, bit + w - 1, bit))
        names[n] = w
        bit += w

    # Per input bit, the expression that drives it; --equal and --zero
    # take a port or a slice of one, NAME or NAME[HI:LO].
    def slice_of(spec):
        m = re.fullmatch(r"(\w+)(?:\[(\d+):(\d+)\])?", spec)
        if not m or m.group(1) not in names:
            raise SystemExit("cosim_tb: no input %s" % spec)
        n = m.group(1)
        if m.group(2) is None:
            return n, 0, names[n]
        hi, lo = int(m.group(2)), int(m.group(3))
        return n, lo, hi - lo + 1

    bits = {n: ["r_%s[%d]" % (n, i) for i in range(w)] for w, n in ins}
    orig = {n: list(v) for n, v in bits.items()}
    sel = 0
    for spec in a.equal:
        x, y = spec.split(",")
        xn, xlo, xw = slice_of(x)
        yn, ylo, yw = slice_of(y)
        if xw != yw:
            raise SystemExit("cosim_tb: --equal %s: widths differ" % spec)
        for k in range(xw):
            bits[yn][ylo + k] = "(lfsr[%d] ? %s : %s)" % (
                sel,
                orig[xn][xlo + k],
                orig[yn][ylo + k],
            )
        sel += 1
    for z in a.zero:
        zn, zlo, zw = slice_of(z)
        for k in range(zw):
            bits[zn][zlo + k] = "((lfsr[%d] & lfsr[%d]) ? 1'b0 : %s)" % (
                sel,
                sel + 1,
                orig[zn][zlo + k],
            )
        sel += 2
    drive = {n: "{" + ", ".join(reversed(v)) + "}" for n, v in bits.items()}
    for w, n in ins:
        o.append("  wire [%d:0] i_%s = %s;" % (w - 1, n, drive[n]))
    for tag in ("g", "n"):
        for w, n in outs:
            o.append("  wire [%d:0] %s_%s;" % (w - 1, tag, n))
    for tag, mod in (("g", "gold"), ("n", "gate")):
        conns = [".%s(clock)" % a.clock, ".%s(reset)" % a.reset]
        conns += [".%s(i_%s)" % (n, n) for _, n in ins]
        conns += [".%s(%s_%s)" % (n, tag, n) for _, n in outs]
        o.append("  %s u_%s(%s);" % (mod, tag, ", ".join(conns)))
    gate = {}
    for spec in a.loaded_by:
        pat, valid = spec.split("=")
        for _, n in outs:
            m = re.fullmatch(pat, n)
            if m:
                gate[n] = m.expand(valid)
    for v in sorted(set(gate.values())):
        o.append("  reg loaded_%s = 0;" % v)
        o.append(
            "  always @(posedge clock) if (!reset && g_%s) loaded_%s <= 1;" % (v, v)
        )
    o.append("  always @* if (!reset && cycle >= %d) begin" % a.warmup)
    for w, n in outs:
        cond = "loaded_%s && " % gate[n] if n in gate else ""
        o.append("    if (%s1) assert (g_%s == n_%s);" % (cond, n, n))
    o.append("  end")
    o.append("endmodule")
    open(a.out, "w").write("\n".join(o) + "\n")


if __name__ == "__main__":
    main()
