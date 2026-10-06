#!/usr/bin/env python3
"""A register file as firtool writes it, and the structured_gen spec for it.

Writes <out>.sv (the RTL module) and <out>.spec (the generator's spec for
the same module) from one set of parameters, so the two cannot disagree.
The shapes are XiangShan's: firtool's `mem_<word>` registers written
through one-hot `wenOH` terms, reads through a `casez` on the address or
on its registered copy `io_readPorts_<r>_data[_<k>]_REG`, read ports
optionally banked with the banks interleaved, word 0 optionally the
constant zero. Small sizes only: the equivalence check is per structure,
and the generator builds every size from the same code.

Usage: lec_fixture.py --out PREFIX --module NAME --words N --bits B
           --reads R --writes W [--latency 1] [--banks K] [--banked]
           [--zero-word] [--gen-banks K] [--spec-latency 0|1]

At XiangShan's sizes it reproduces firtool's FpRegFile, VfRegFile and
IntRegFile token for token (faithful_test); the LEC runs it small.
"""

import argparse


def addr_bits(n):
    a = 0
    while (1 << a) < n:
        a += 1
    return max(a, 1)


def rtl(a):
    """The module the way firtool writes it, token for token (layout aside)."""
    n, b, r_ports, w_ports = a.words, a.bits, a.reads, a.writes
    banks = a.banks if a.banked else 1
    aw = addr_bits(n)
    al = addr_bits(n // banks)
    z = 0 if a.zero_word else None
    out = [f"module {a.module}(", "  input clock,"]
    ports = []
    for r in range(r_ports):
        if a.banked:
            for k in range(banks):
                ports.append(f"  input [{al - 1}:0] io_readPorts_{r}_addr_{k}")
            for k in range(banks):
                ports.append(f"  output [{b - 1}:0] io_readPorts_{r}_data_{k}")
        else:
            ports.append(f"  input [{aw - 1}:0] io_readPorts_{r}_addr")
            ports.append(f"  output [{b - 1}:0] io_readPorts_{r}_data")
    for w in range(w_ports):
        ports.append(f"  input io_writePorts_{w}_wen")
        ports.append(f"  input [{aw - 1}:0] io_writePorts_{w}_addr")
        ports.append(f"  input [{b - 1}:0] io_writePorts_{w}_data")
    # firtool declares a run of ports of one direction and width once:
    # `input [5:0] a, b, c`.
    merged = []
    prev = None
    for decl in ports:
        kind, name = decl.rsplit(" ", 1)
        merged.append(f"  {name}" if kind == prev else decl)
        prev = kind
    out.append(",\n".join(merged))
    out.append(");")
    words = [i for i in range(n) if i != z]
    for i in words:
        out.append(f"  reg [{b - 1}:0] mem_{i};")

    tmps = []
    reg_assigns = []

    def read(sel_name, addr_port, width, entries):
        sel = addr_port
        if a.latency:
            out.append(f"  reg [{width - 1}:0] {sel_name};")
            reg_assigns.append(f"    {sel_name} <= {addr_port};")
            sel = sel_name
        tmp = "casez_tmp" if not tmps else f"casez_tmp_{len(tmps) - 1}"
        tmps.append(tmp)
        out.append(f"  reg [{b - 1}:0] {tmp};")
        out.append("  always @(*) begin")
        out.append(f"    casez ({sel})")
        # firtool lists every address the select can hold, the last as the
        # default; an address past the end reads entry 0, the way it lowers
        # an out-of-range dynamic Vec index. The LEC fixtures are powers
        # of two, so no address is past the end there.
        word_at = dict(entries)
        last = (1 << width) - 1
        for local in range(last + 1):
            word = word_at.get(local, word_at[0])
            value = f"mem_{word}" if word is not None and word != z else f"{b}'h0"
            label = "default:" if local == last else f"{width}'b{local:0{width}b}:"
            out.append(f"      {label}")
            out.append(f"        {tmp} = {value};")
        out.append("    endcase")
        out.append("  end // always @(*)")
        return tmp

    data_ports = []
    for r in range(r_ports):
        if a.banked:
            for k in range(banks):
                entries = [(l, l * banks + k) for l in range(n // banks)]
                t = read(f"io_readPorts_{r}_data_{k}_REG", f"io_readPorts_{r}_addr_{k}", al, entries)
                data_ports.append((f"io_readPorts_{r}_data_{k}", t))
        else:
            t = read(f"io_readPorts_{r}_data_REG", f"io_readPorts_{r}_addr", aw, [(i, i) for i in range(n)])
            data_ports.append((f"io_readPorts_{r}_data", t))

    # firtool numbers the write enables by stored word, not by address:
    # with word 0 the constant zero, address 1 is the first.
    position = {word: k for k, word in enumerate(words)}

    def wen(i, w):
        return f"wenOH_{w}" if position[i] == 0 else f"wenOH_{position[i]}_{w}"

    for i in words:
        for w in range(w_ports):
            if i == (1 << aw) - 1:
                cmp = f"(&io_writePorts_{w}_addr)"
            else:
                cmp = f"io_writePorts_{w}_addr == {aw}'h{i:X}"
            out.append(f"  wire {wen(i, w)} = io_writePorts_{w}_wen & {cmp};")
    out.append("  always @(posedge clock) begin")
    for i in words:
        ens = ", ".join(wen(i, w) for w in reversed(range(w_ports)))
        out.append(f"    if (|{{{ens}}})" if w_ports > 1 else f"    if ({ens})")
        terms = [f"({wen(i, w)} ? io_writePorts_{w}_data : {b}'h0)" for w in range(w_ports)]
        out.append(f"      mem_{i} <=")
        out.append("        " + "\n        | ".join(terms) + ";")
    out += reg_assigns
    out.append("  end // always @(posedge)")
    for port, t in data_ports:
        out.append(f"  assign {port} = {t};")
    out.append("endmodule")
    return "\n".join(out) + "\n"


def spec(a):
    banks = a.banks if a.banked else 1
    lines = [
        f"module {a.module}",
        f"words {a.words}",
        f"bits {a.bits}",
        "clock clock",
    ]
    gen_banks = banks if a.banked else a.gen_banks
    if gen_banks > 1:
        lines.append(f"banks {gen_banks}")
    for r in range(a.reads):
        if a.banked:
            pairs = " ".join(
                f"io_readPorts_{r}_addr_{k} io_readPorts_{r}_data_{k}"
                for k in range(banks)
            )
            lines.append(f"read_banked {pairs}")
        else:
            lines.append(f"read io_readPorts_{r}_addr io_readPorts_{r}_data")
    for w in range(a.writes):
        lines.append(
            f"write io_writePorts_{w}_addr io_writePorts_{w}_data "
            f"io_writePorts_{w}_wen"
        )
    lines.append(f"read_latency {a.latency if a.spec_latency is None else a.spec_latency}")
    if a.banked:
        lines.append("bank_order interleaved")
    if a.zero_word:
        lines.append("zero_word 0")
    lines.append("store_name mem_{word}[{bit}]")
    lines.append(
        "read_reg_name io_readPorts_{port}_data_{bank}_REG[{bit}]"
        if a.banked
        else "read_reg_name io_readPorts_{port}_data_REG[{bit}]"
    )
    # No tap cells: they are physical only, with no liberty function.
    lines += [
        "cell flop DFFHQNx1_ASAP7_75t_R",
        "cell and2 AND2x2_ASAP7_75t_R",
        "cell or2 OR2x2_ASAP7_75t_R",
        "cell ao22 AO22x2_ASAP7_75t_R",
        "cell inv INVx1_ASAP7_75t_R",
        "pin_layer M4",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--words", type=int, required=True)
    p.add_argument("--bits", type=int, required=True)
    p.add_argument("--reads", type=int, required=True)
    p.add_argument("--writes", type=int, required=True)
    p.add_argument("--latency", type=int, default=0, choices=[0, 1])
    p.add_argument("--banks", type=int, default=1)
    p.add_argument("--banked", action="store_true")
    p.add_argument("--zero-word", action="store_true")
    p.add_argument(
        "--gen-banks",
        type=int,
        default=1,
        help="banks of the generated array for plain reads (geometry only)",
    )
    p.add_argument(
        "--spec-latency",
        type=int,
        choices=[0, 1],
        help="the spec's read_latency when it should differ from the RTL's",
    )
    a = p.parse_args(argv)
    if a.banked and a.words % a.banks:
        p.error("words must be a multiple of banks")
    with open(a.out + ".sv", "w") as f:
        f.write(rtl(a))
    with open(a.out + ".spec", "w") as f:
        f.write(spec(a))


if __name__ == "__main__":
    main()
