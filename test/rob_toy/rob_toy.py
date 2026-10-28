"""A toy reorder buffer: XiangShan's Rob entry state at any size.

The per-entry update rules are Rob.scala's (aa6b5203, RobImp, "update
robEntries valid" and the loop after it): valid set at the allocate
pointers and cleared at commit or by the redirect's circular range,
uopNum loaded at enqueue and counted down by the writeback port that
hits the entry, realDestSize accumulated over the enqueue ports, fflags
and vxsat OR-accumulated, needFlush sticky, the trace itype set to taken
by a branch writeback. The payload (RobEntryFile) is written at the
allocate pointers. Enqueue and commit arrive by bank (the crossbar from
the rename ports is outside the array). Every bank reads its entry of this line and the next
at a one-hot line address. Every channel names an entry by index and
every entry compares itself against every channel, as the RTL does.

The top registers every input and output of the structure, so every
path is register to register.

    rob_toy.py <out.sv> <top> key=value... [top-only]

top-only writes the top without RobState, for rob_gen.py's netlist.

Keys: entries, enq, commit, wb (exu writebacks), exc (exception
writebacks), ff (fflags writebacks), vx (vxsat writebacks), br (branch
writebacks), payload (bits).
"""

import math
import sys

DEFAULTS = {
    "entries": 352,
    "enq": 8,
    "commit": 8,
    "wb": 16,
    "exc": 8,
    "ff": 6,
    "vx": 2,
    "br": 4,
    "payload": 21,
}

UOPNUM = 8  # log2Up(MaxUopSize * 2 + 1)
DEST = 7  # log2Up(MaxUopSize + 1)
WBCNT = 6
ITYPE = 4
NONTAKEN = 4
TAKEN = 5


def structure(p):
    n = p["entries"]
    a = max(1, math.ceil(math.log2(n)))
    nb = p["commit"]
    lines_ = n // nb
    lb = max(1, math.ceil(math.log2(lines_)))
    dw = max(1, math.ceil(math.log2(p["enq"] + 1)))
    ports = ["input clock"]
    # enqueue and commit by bank: the allocate pointers, and the commit
    # pointers, are consecutive, so one cycle's enqueues land in distinct
    # banks, one per bank, as its commits do; the crossbar from the
    # rename ports to the banks is outside the array, as robDeqGroup is
    for b in range(nb):
        ports += [
            f"input enq{b}_alloc",
            f"input enq{b}_inst",
            f"input enq{b}_uop",
            f"input [{lb-1}:0] enq{b}_line",
            f"input [{dw-1}:0] enq{b}_dest",
            f"input [{UOPNUM-1}:0] enq{b}_numwb",
            f"input [{ITYPE-1}:0] enq{b}_itype",
            f"input [{p['payload']-1}:0] enq{b}_payload",
        ]
    ports += ["input redirect_valid", "input redirect_valid_reg", "input redirect_all"]
    ports += [f"input [{a-1}:0] redirect_begin", f"input [{a-1}:0] redirect_end"]
    ports += [f"input [{lines_-1}:0] rd_line_oh"]
    for b in range(nb):
        ports += [f"input commit{b}_valid", f"input [{lb-1}:0] commit{b}_line"]
    for w in range(p["wb"]):
        ports += [
            f"input wb{w}_valid",
            f"input [{a-1}:0] wb{w}_idx",
            f"input [{WBCNT-1}:0] wb{w}_cnt",
        ]
    for x in range(p["exc"]):
        ports += [
            f"input exc{x}_valid",
            f"input [{a-1}:0] exc{x}_idx",
            f"input exc{x}_flush",
        ]
    for f in range(p["ff"]):
        ports += [
            f"input ff{f}_valid",
            f"input [{a-1}:0] ff{f}_idx",
            f"input ff{f}_wen",
            f"input [4:0] ff{f}_flags",
        ]
    for v in range(p["vx"]):
        ports += [
            f"input vx{v}_valid",
            f"input [{a-1}:0] vx{v}_idx",
            f"input vx{v}_sat",
        ]
    for b in range(p["br"]):
        ports += [
            f"input br{b}_valid",
            f"input [{a-1}:0] br{b}_idx",
            f"input br{b}_taken",
        ]
    rec = 2 + UOPNUM + DEST + 5 + 1 + ITYPE + p["payload"]
    for side in ("this", "next"):
        for b in range(nb):
            ports += [f"output [{rec-1}:0] {side}{b}_entry"]

    def any_of(terms):
        return " | ".join(terms) if terms else "1'b0"

    B = range(nb)

    def vec(name, field, w):
        return [
            (
                f"  wire [{w-1}:0] {name} [0:{nb-1}];"
                if w > 1
                else f"  wire {name} [0:{nb-1}];"
            )
        ] + [f"  assign {name}[{b}] = enq{b}_{field};" for b in B]

    body = []
    for name, field, w in (
        ("enq_alloc", "alloc", 1),
        ("enq_inst", "inst", 1),
        ("enq_uop", "uop", 1),
        ("enq_line", "line", lb),
        ("enq_dest", "dest", dw),
        ("enq_numwb_v", "numwb", UOPNUM),
        ("enq_itype_v", "itype", ITYPE),
        ("enq_payload", "payload", p["payload"]),
    ):
        body += vec(name, field, w)
    body += [
        f"  wire commit_valid [0:{nb-1}];",
        f"  wire [{lb-1}:0] commit_line [0:{nb-1}];",
    ]
    body += [f"  assign commit_valid[{b}] = commit{b}_valid;" for b in B]
    body += [f"  assign commit_line[{b}] = commit{b}_line;" for b in B]
    body += [
        f"  reg [{n-1}:0] valid, needflush, vxsat;",
        f"  reg [{n-1}:0][{UOPNUM-1}:0] uopnum;",
        f"  reg [{n-1}:0][{DEST-1}:0] destsize;",
        f"  reg [{n-1}:0][4:0] fflags;",
        f"  reg [{n-1}:0][{ITYPE-1}:0] itype;",
        f"  reg [{n-1}:0][{p['payload']-1}:0] payload;",
        "  always @(posedge clock) begin",
        f"    for (int i = 0; i < {n}; i++) begin",
    ]
    body += [
        f"      automatic int b = i % {nb};",
        f"      automatic int l = i / {nb};",
        "      automatic logic hit = enq_line[b] == l;",
        "      automatic logic enq_oh = enq_alloc[b] & hit;",
        "      automatic logic commit_cond = commit_valid[b] & commit_line[b] == l;",
        "      automatic logic in_range = redirect_end > redirect_begin"
        " ? (i > redirect_begin && i < redirect_end)"
        " : (i > redirect_begin || i < redirect_end);",
        "      automatic logic flush = redirect_valid_reg & (in_range | redirect_all);",
        "      automatic logic inst_enq = enq_inst[b] & hit;",
        "      automatic logic uop_enq = enq_uop[b] & hit;",
        "      automatic logic first_enq = !valid[i] & inst_enq;",
        f"      automatic logic [{DEST-1}:0] dest_enq = uop_enq ? {DEST}'(enq_dest[b]) : {DEST}'d0;",
        f"      automatic logic [{UOPNUM-1}:0] enq_numwb = enq_numwb_v[b];",
        f"      automatic logic [{ITYPE-1}:0] enq_itype = enq_itype_v[b];",
        f"      automatic logic [{WBCNT-1}:0] wbcnt = "
        + (
            " | ".join(
                f"({{{WBCNT}{{wb{w}_valid & wb{w}_idx == i}}}} & wb{w}_cnt)"
                for w in range(p["wb"])
            )
            or f"{WBCNT}'d0"
        )
        + ";",
        "      automatic logic flush_wb = "
        + any_of(
            [
                f"(exc{x}_valid & exc{x}_idx == i & exc{x}_flush)"
                for x in range(p["exc"])
            ]
        )
        + ";",
        "      automatic logic [4:0] ff_res = "
        + (
            " | ".join(
                f"({{5{{ff{f}_valid & ff{f}_idx == i & ff{f}_wen}}}} & ff{f}_flags)"
                for f in range(p["ff"])
            )
            or "5'd0"
        )
        + ";",
        "      automatic logic vx_res = "
        + any_of(
            [f"(vx{v}_valid & vx{v}_idx == i & vx{v}_sat)" for v in range(p["vx"])]
        )
        + ";",
        "      automatic logic taken = "
        + any_of(
            [f"(br{b}_valid & br{b}_idx == i & br{b}_taken)" for b in range(p["br"])]
        )
        + ";",
        "      if (commit_cond) valid[i] <= 1'b0;",
        "      else if (enq_oh & !redirect_valid) valid[i] <= 1'b1;",
        "      else if (flush) valid[i] <= 1'b0;",
        "      if (first_enq) destsize[i] <= dest_enq;",
        "      else if (valid[i] & uop_enq) destsize[i] <= destsize[i] + dest_enq;",
        "      if (first_enq) needflush[i] <= 1'b0;",
        "      else if (valid[i]) needflush[i] <= needflush[i] | flush_wb;",
        "      if (valid[i] & (needflush[i] | flush_wb)) uopnum[i] <= uopnum[i] - wbcnt;",
        "      else if (!valid[i] & inst_enq) uopnum[i] <= enq_numwb;",
        "      else if (valid[i]) uopnum[i] <= uopnum[i] - wbcnt;",
        "      if (first_enq) fflags[i] <= 5'd0;",
        "      else if (|ff_res) fflags[i] <= fflags[i] | ff_res;",
        "      if (first_enq) vxsat[i] <= 1'b0;",
        "      else if (vx_res) vxsat[i] <= 1'b1;",
        "      if (first_enq) itype[i] <= enq_itype;",
        f"      else if (valid[i] & itype[i] == {ITYPE}'d{NONTAKEN} & taken)"
        f" itype[i] <= {ITYPE}'d{TAKEN};",
    ]
    body += ["      if (enq_oh) payload[i] <= enq_payload[b];", "    end", "  end"]
    # Rob.scala's robBanks: the entries are banked by the low bits of
    # their index, one bank per commit slot, and every bank reads this
    # line and the next at a one-hot line address (robBanksRaddrThisLine);
    # the commit and walk slots pick from what is read, in robDeqGroup,
    # outside the array
    for side, shift in (("this", 0), ("next", 1)):
        for b in range(nb):
            terms = []
            for line in range(lines_):
                i = ((line + shift) % lines_) * nb + b
                terms.append(
                    f"({{{rec}{{rd_line_oh[{line}]}}}} & {{valid[{i}], needflush[{i}],"
                    f" uopnum[{i}], destsize[{i}], fflags[{i}], vxsat[{i}],"
                    f" itype[{i}], payload[{i}]}})"
                )
            body.append(f"  assign {side}{b}_entry = " + " | ".join(terms) + ";")
    return ports, body


def _parse_port(port):
    words = port.split()
    return words[0], (words[1] if len(words) == 3 else ""), words[-1]


def main(argv):
    out, top = argv[1], argv[2]
    top_only = "top-only" in argv
    p = dict(DEFAULTS)
    for kv in (x for x in argv[3:] if x != "top-only"):
        k, v = kv.split("=")
        if k not in p:
            sys.exit(f"rob_toy.py: unknown key {k}")
        p[k] = int(v)
    ports, body = structure(p)
    lines = []
    if not top_only:
        lines += ["module RobState("]
        lines += [",\n".join("  " + q for q in ports), ");"]
        lines += body + ["endmodule", ""]
    lines += [f"module {top}(input clock, input seed, output reg sig);"]
    # every input of the structure is driven from a register, every
    # output lands in one; the registers chain so nothing is constant
    parsed = [_parse_port(q) for q in ports if q != "input clock"]
    bits = 0
    for d, rng, name in parsed:
        lines.append(f"  reg {rng} r_{name};" if rng else f"  reg r_{name};")
        if d == "output":
            lines.append(f"  wire {rng} w_{name};" if rng else f"  wire w_{name};")
    lines.append("  RobState s(.clock(clock),")
    conns = [f"    .{n}({'w_' if d == 'output' else 'r_'}{n})" for d, _, n in parsed]
    lines.append(",\n".join(conns) + ");")
    # an LFSR feeds the inputs, the outputs fold back into it, so the
    # structure's inputs are neither constant nor shared
    ins = [(rng, n) for d, rng, n in parsed if d == "input"]
    outs = [(rng, n) for d, rng, n in parsed if d == "output"]
    lines.append("  reg [63:0] lfsr;")
    fold = " ^ ".join(f"^r_{n}" for _, n in outs) or "1'b0"
    lines += [
        "  always @(posedge clock) begin",
        "    lfsr <= {lfsr[62:0], lfsr[63] ^ lfsr[62] ^ lfsr[60] ^ lfsr[59] ^ seed};",
        f"    sig <= {fold};",
    ]
    for k, (rng, n) in enumerate(ins):
        lines.append(f"    r_{n} <= (lfsr >> {k % 61}) ^ (lfsr << {(k * 7) % 61});")
    for _, n in outs:
        lines.append(f"    r_{n} <= w_{n};")
    lines += ["  end", "endmodule", ""]
    with open(out, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv)
