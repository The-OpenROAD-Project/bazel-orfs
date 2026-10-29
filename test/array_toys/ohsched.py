"""The ohsched toy: a one-hot-addressed, broadcast-read, bank-filled
array, a scheduler's or issue queue's shape, in two arms with one
function.

The question it asks: can generate_array's generated form beat yosys's
flops on period, at no more area, with faster synthesis?

Entries sit in banks, each entry a payload and two small fields. Every
cycle:

- picks: each of a few read ports reads one entry's payload, its address
  a registered row one-hot and bank one-hot, through a one-hot mux, never
  a binary index; the payload is compared against a value, the result
  registered;
- broadcast reads of every entry at once: a decode of the entry's type
  field ANDed with a live mask (ready), and a compare of its index field
  against a vector of tags (wakeup, CAM-like);
- writes, by kind: `fill` writes a whole bank in one cycle; `lanes` has a
  few lanes each writing one entry, lane l the bank's row l mod rows.

Arms:

- yosys: plain flops, the natural RTL; synthesis maps every entry to
  flops and the picks to one-hot AND-OR muxes.
- generate_ram: the payload in a register file module (`Arr`: binary
  addresses, one write port per row written in a cycle), which
  AUTO_MEMORIES_REGFILES replaces by generate_ram's netlist; the one-hot
  picks and write banks encoded to binary for it; the type and index
  fields, which the broadcast reads consume from every entry and a
  register file cannot serve, in flops beside it.

The top registers every input and every output, so every path is
register to register; the critical one is pick register, array read,
compare, output register. The top is retimed in synthesis
(SYNTH_RETIME_MODULES).

    ohsched.py rtl <kind> <arm> <top> <out.v> [--mutate]
    ohsched.py spec <kind> <out.regfile>
    ohsched.py tb <kind> <yosys top> <generate_ram top> <out.v> [--cycles N]

`--mutate` swaps two rows of the generate_ram arm's pick decode: the
co-simulation's negative control.
"""

import argparse
import math

# kind: banks, rows per bank, payload bits, picks, tags,
# type-field bits, index-field bits, write lanes (None: whole-bank fill)
KINDS = {
    "fill": dict(
        banks=4, rows=8, width=32, picks=2, tags=2, tbits=2, ibits=5, lanes=None
    ),
    "lanes": dict(
        banks=8, rows=4, width=32, picks=2, tags=2, tbits=2, ibits=5, lanes=4
    ),
}

_CELLS = """\
cell flop DFFHQNx1_ASAP7_75t_R
cell and2 AND2x2_ASAP7_75t_R
cell or2 OR2x2_ASAP7_75t_R
cell ao22 AO22x2_ASAP7_75t_R
cell inv INVx1_ASAP7_75t_R
cell tap TAPCELL_ASAP7_75t_R
pin_layer M4
"""


def _bits(n):
    return max(1, math.ceil(math.log2(n)))


def _rng(w):
    return f"[{w - 1}:0] " if w > 1 else ""


def ports(p):
    """(direction, width, name) of the top, clock excluded."""
    n = p["banks"] * p["rows"]
    d = p["width"] + p["tbits"] + p["ibits"]
    out = []
    for r in range(p["picks"]):
        out += [
            ("input", p["rows"], f"pick{r}_row"),
            ("input", p["banks"], f"pick{r}_bank"),
            ("input", p["width"], f"cmp{r}"),
        ]
    out.append(("input", 1 << p["tbits"], "live"))
    for k in range(p["tags"]):
        out += [("input", p["ibits"], f"tag{k}"), ("input", 1, f"tag{k}_v")]
    if p["lanes"] is None:
        out += [
            ("input", 1, "fill_en"),
            ("input", p["banks"], "fill_bank"),
            ("input", p["rows"] * d, "fill_data"),
        ]
    else:
        for l in range(p["lanes"]):
            out += [
                ("input", 1, f"lane{l}_en"),
                ("input", p["banks"], f"lane{l}_bank"),
                ("input", d, f"lane{l}_data"),
            ]
    out += [
        ("output", p["picks"], "match"),
        ("output", n, "ready"),
        ("output", n, "wake"),
    ]
    return out


def _writes(p):
    """Per write port: (enable, bank one-hot, row, data, data's lowest
    bit) of registered signals; a fill is one port per row."""
    d = p["width"] + p["tbits"] + p["ibits"]
    if p["lanes"] is None:
        return [
            ("fill_en_q", "fill_bank_q", e, "fill_data_q", e * d)
            for e in range(p["rows"])
        ]
    return [
        (f"lane{l}_en_q", f"lane{l}_bank_q", l % p["rows"], f"lane{l}_data_q", 0)
        for l in range(p["lanes"])
    ]


def _encode(onehot, n, name, lines):
    """Binary index of a one-hot vector: bit k is the OR of the lines
    whose index has bit k set."""
    a = _bits(n)
    lines.append(f"  wire [{a - 1}:0] {name};")
    for k in range(a):
        terms = [f"{onehot}[{i}]" for i in range(n) if i >> k & 1] or ["1'b0"]
        lines.append(f"  assign {name}[{k}] = {' | '.join(terms)};")


def rtl(kind, arm, top, mutate=False):
    p = KINDS[kind]
    banks, rows, w = p["banks"], p["rows"], p["width"]
    tb_, ib = p["tbits"], p["ibits"]
    n = banks * rows
    d = w + tb_ + ib
    lines = [f"module {top}(", "  input clock,"]
    lines.append(
        ",\n".join(f"  {dr} {_rng(wd)}{nm}" for dr, wd, nm in ports(p)) + "\n);"
    )
    # every input registered; outputs from registers
    for dr, wd, nm in ports(p):
        if dr == "input":
            lines.append(f"  reg {_rng(wd)}{nm}_q;")
            lines.append(f"  always @(posedge clock) {nm}_q <= {nm};")
        else:
            lines.append(f"  reg {_rng(wd)}{nm}_r;")
            lines.append(f"  wire {_rng(wd)}{nm}_d;")
            lines.append(f"  always @(posedge clock) {nm}_r <= {nm}_d;")
            lines.append(f"  assign {nm} = {nm}_r;")
    writes = _writes(p)

    def we(i):
        b, e = divmod(i, rows)
        terms = [f"({en} & {bank}[{b}])" for en, bank, row, _, _ in writes if row == e]
        return " | ".join(terms) or "1'b0"

    def wd(i, lo, hi):
        """Data written to entry i, bits lo..hi of the entry; the ports
        that can write it are distinct rows, so at most one does."""
        b, e = divmod(i, rows)
        srcs = [(en, bank, data, o) for en, bank, row, data, o in writes if row == e]
        if len(srcs) == 1:
            data, o = srcs[0][2], srcs[0][3]
            return f"{data}[{o + hi}:{o + lo}]"
        sel = " | ".join(
            f"({{{hi - lo + 1}{{{en} & {bank}[{b}]}}}} & {data}[{o + hi}:{o + lo}])"
            for en, bank, data, o in srcs
        )
        return f"({sel})"

    # entry fields: payload [w-1:0], type [w+tb-1:w], index [d-1:w+tb]
    fields_lo = w
    # one register per entry, not an array: plain flops, no memory
    # inference
    for i in range(n):
        lines.append(f"  reg [{tb_ + ib - 1}:0] fld{i};")
        lines.append(
            f"  always @(posedge clock) if ({we(i)}) fld{i} <= {wd(i, fields_lo, d - 1)};"
        )
        if arm == "yosys":
            lines.append(f"  reg [{w - 1}:0] pay{i};")
            lines.append(
                f"  always @(posedge clock) if ({we(i)}) pay{i} <= {wd(i, 0, w - 1)};"
            )
    # picks
    rdata = []
    for r in range(p["picks"]):
        row, bank = f"pick{r}_row_q", f"pick{r}_bank_q"
        lines.append(f"  wire pick{r}_v = (|{row}) & (|{bank});")
        if arm == "yosys":
            terms = [
                f"({{{w}{{{bank}[{i // rows}] & {row}[{i % rows}]}}}} & pay{i})"
                for i in range(n)
            ]
            lines.append(f"  wire [{w - 1}:0] rd{r} = {' | '.join(terms)};")
        else:
            rowsig = row
            if mutate and r == 0:
                # negative control: rows 0 and 1 swapped in the decode
                lines.append(
                    f"  wire [{rows - 1}:0] {row}_m = {{{row}[{rows - 1}:2], {row}[0], {row}[1]}};"
                )
                rowsig = f"{row}_m"
            _encode(bank, banks, f"pick{r}_b", lines)
            _encode(rowsig, rows, f"pick{r}_e", lines)
            lines.append(f"  wire [{w - 1}:0] rd{r};")
        rdata.append(f"rd{r}")
    if arm == "generate_ram":
        conns = [".clock(clock)"]
        for r in range(p["picks"]):
            conns += [f".r{r}_addr({{pick{r}_b, pick{r}_e}})", f".r{r}_data(rd{r})"]
        for j, (en, bank, row, data, o) in enumerate(writes):
            _encode(bank, banks, f"w{j}_b", lines)
            rb = _bits(rows)
            conns += [
                f".w{j}_addr({{w{j}_b, {rb}'d{row}}})",
                f".w{j}_data({data}[{o + w - 1}:{o}])",
                f".w{j}_en({en} & (|{bank}))",
            ]
        lines.append(f"  Arr arr({', '.join(conns)});")
    lines.append(
        "  assign match_d = {"
        + ", ".join(
            f"pick{r}_v & ({rdata[r]} == cmp{r}_q)" for r in reversed(range(p["picks"]))
        )
        + "};"
    )
    # broadcast reads of every entry
    for i in range(n):
        typ = f"fld{i}[{tb_ - 1}:0]"
        idx = f"fld{i}[{tb_ + ib - 1}:{tb_}]"
        lines.append(f"  assign ready_d[{i}] = |(({1 << tb_}'d1 << {typ}) & live_q);")
        wake = " | ".join(
            f"(tag{k}_v_q & ({idx} == tag{k}_q))" for k in range(p["tags"])
        )
        lines.append(f"  assign wake_d[{i}] = {wake};")
    lines += ["endmodule", ""]
    if arm == "generate_ram":
        lines += _arr(p)
    return "\n".join(lines)


def _arr(p):
    """The register file generate_ram replaces: binary addresses, a read
    is the stored word, a write lands at the clock."""
    n = p["banks"] * p["rows"]
    a = _bits(n)
    w = p["width"]
    nw = len(_writes(p))
    pl = ["  input clock"]
    for r in range(p["picks"]):
        pl += [f"  input [{a - 1}:0] r{r}_addr", f"  output [{w - 1}:0] r{r}_data"]
    for j in range(nw):
        pl += [
            f"  input [{a - 1}:0] w{j}_addr",
            f"  input [{w - 1}:0] w{j}_data",
            f"  input w{j}_en",
        ]
    lines = ["module Arr(", ",\n".join(pl), ");"]
    lines.append(f"  reg [{w - 1}:0] mem [0:{n - 1}];")
    for r in range(p["picks"]):
        lines.append(f"  assign r{r}_data = mem[r{r}_addr];")
    lines.append("  always @(posedge clock) begin")
    for j in range(nw):
        lines.append(f"    if (w{j}_en) mem[w{j}_addr] <= w{j}_data;")
    lines += ["  end", "endmodule", ""]
    return lines


def spec(kind):
    p = KINDS[kind]
    lines = [
        "module Arr",
        f"words {p['banks'] * p['rows']}",
        f"bits {p['width']}",
        "clock clock",
    ]
    lines += [f"read r{r}_addr r{r}_data" for r in range(p["picks"])]
    lines += [f"write w{j}_addr w{j}_data w{j}_en" for j in range(len(_writes(p)))]
    return "\n".join(lines) + "\n" + _CELLS


def tb(kind, tops, cycles):
    """Both arms' tops under the same random stimulus, every output
    compared every cycle once every entry has been written. Picks and
    banks are one-hot or zero, as the structure assumes."""
    p = KINDS[kind]
    banks, rows = p["banks"], p["rows"]
    init = banks + 2
    lines = [
        "module tb(input clock, output reg done, output reg [31:0] bad,",
        "          output reg [31:0] n_match, output reg [31:0] n_wake,",
        "          output reg [31:0] n_ready);",
        "  reg [31:0] cycle = 0;",
        "  initial begin done = 0; bad = 0; n_match = 0; n_wake = 0; n_ready = 0; end",
    ]
    pts = ports(p)
    for dr, wd, nm in pts:
        lines.append(
            f"  {'reg' if dr == 'input' else 'wire'} {_rng(wd)}{nm}{'' if dr == 'input' else '_a, ' + nm + '_b'};"
        )
    # one xorshift64 per 64 input bits, seeded apart
    seeds = 0
    rnd = {}
    for dr, wd, nm in pts:
        if dr != "input":
            continue
        words = -(-wd // 64)
        rnd[nm] = list(range(seeds, seeds + words))
        seeds += words
    for s in range(seeds + 1):
        lines.append(
            f"  reg [63:0] s{s} = 64'd{0x9E3779B97F4A7C15 * (s + 1) % (1 << 64)};"
        )
    # stimulus and checks on the falling edge, the tops on the rising one
    lines.append("  always @(negedge clock) begin")
    for s in range(seeds + 1):
        lines.append(
            f"    s{s} = s{s} ^ (s{s} << 13); s{s} = s{s} ^ (s{s} >> 7); s{s} = s{s} ^ (s{s} << 17);"
        )

    def onehot(nm, n, src, zero_one_in):
        return f"    {nm} = ({src}[7:0] % {zero_one_in} == 0) ? {n}'d0 : ({n}'d1 << ({src}[15:8] % {n}));"

    fill_bank = f"({banks}'d1 << (cycle % {banks}))"
    for dr, wd, nm in pts:
        if dr != "input":
            continue
        src = f"s{rnd[nm][0]}"
        if nm.endswith("_row"):
            lines.append(onehot(nm, wd, src, 8))
        elif nm.endswith("_bank"):
            lines.append(f"    if (cycle < {init}) {nm} = {fill_bank}; else")
            lines.append(onehot(nm, wd, src, 4 if nm.startswith("pick") else 1 << 30))
        elif nm.endswith("_en"):
            lines.append(f"    {nm} = (cycle < {init}) | {src}[0];")
        elif nm.endswith("_data") or nm.startswith("cmp") or nm.startswith("tag"):
            # half the cycles a two-bit pattern repeated, so that compares
            # and tags match stored entries often
            full = f"{{{', '.join(f's{x}' for x in rnd[nm])}}}"
            rep = f"{{{-(-wd // 2)}{{s{seeds}[1:0]}}}}"
            lines.append(f"    {nm} = s{seeds}[63] ? {full} : {rep};")
        else:
            lines.append(f"    {nm} = {{{', '.join(f's{x}' for x in rnd[nm])}}};")
    lines.append("    cycle <= cycle + 1;")
    lines.append(f"    if (cycle > {init + 2}) begin")
    for dr, wd, nm in pts:
        if dr == "output":
            lines.append(
                f"      if ({nm}_a !== {nm}_b) begin bad <= bad + 1; "
                f'if (bad < 5) $display("cycle %0d: {nm} %h vs %h", cycle, {nm}_a, {nm}_b); end'
            )
    # cycles each kind of read hit something: a test that compares
    # zeros against zeros proves nothing
    lines.append("      if (|match_a) n_match <= n_match + 1;")
    lines.append("      if (|wake_a) n_wake <= n_wake + 1;")
    lines.append("      if (|ready_a) n_ready <= n_ready + 1;")
    lines.append("    end")
    lines.append(f"    if (cycle == {cycles}) done <= 1;")
    lines.append("  end")
    for arm, top in zip(("a", "b"), tops):
        conns = [".clock(clock)"] + [
            f".{nm}({nm}{'' if dr == 'input' else '_' + arm})" for dr, wd, nm in pts
        ]
        lines.append(f"  {top} {arm}({', '.join(conns)});")
    lines += ["endmodule", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["rtl", "spec", "tb"])
    ap.add_argument("kind", choices=sorted(KINDS))
    ap.add_argument("args", nargs="+")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--cycles", type=int, default=20000)
    a = ap.parse_args()
    if a.what == "rtl":
        arm, top, out = a.args
        text = rtl(a.kind, arm, top, a.mutate)
    elif a.what == "spec":
        (out,) = a.args
        text = spec(a.kind)
    else:
        top_a, top_b, out = a.args
        text = tb(a.kind, (top_a, top_b), a.cycles)
    with open(out, "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
