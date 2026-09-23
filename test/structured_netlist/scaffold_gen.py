#!/usr/bin/env python3
"""The scaffold around one register-file spec: a parent of flops, at real size.

    scaffold_gen.py --spec RenameBufferFile.regfile --sv out.sv --placement out.txt

Reads a structured_gen spec (mode netlist) and writes the behavioural model
of its module in the port shape the generator gives it, and a parent that
registers every pin: one flop per address, data and enable bit, the read
data xor-reduced into a sum. The flow blackboxes the model and links the
generated netlist in its place, so the parent's place, CTS and route see
the real array with the real cell count, minutes after the spec changes.
What the miniature planned parent cannot show: its files are 30 um wide
and never grow a net the resizer wants to buffer; XiangShan's 305 um
RenameBufferFile did (inventory entry 16).

Port widths follow the generator: an address is clog2(words) bits, a
banked read port's per-bank address clog2(words / banks), data is `bits`.
"""

import argparse
import sys


def clog2(n):
    return max(1, (n - 1).bit_length())


def parse(path):
    spec = {"reads": [], "reads_banked": [], "writes": []}
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, *rest = line.split()
            if key == "read":
                spec["reads"].append(tuple(rest))
            elif key == "read_banked":
                spec["reads_banked"].append(
                    [tuple(rest[i : i + 2]) for i in range(0, len(rest), 2)]
                )
            elif key == "write":
                spec["writes"].append(tuple(rest))
            elif key in ("words", "bits", "banks", "bank_columns"):
                spec[key] = int(rest[0])
            else:
                spec[key] = rest[0] if rest else ""
    for k in ("module", "words", "bits", "clock"):
        if k not in spec:
            sys.exit("%s: spec has no %s" % (path, k))
    return spec


def ports(spec):
    """(name, direction, width) in the generator's order."""
    aw = clog2(spec["words"])
    baw = clog2(spec["words"] // spec.get("banks", 1))
    out = [(spec["clock"], "input", 1)]
    for addr, data in spec["reads"]:
        out.append((addr, "input", aw))
    for pairs in spec["reads_banked"]:
        for addr, data in pairs:
            out.append((addr, "input", baw))
    for addr, data, wen in spec["writes"]:
        out += [(addr, "input", aw), (data, "input", spec["bits"]), (wen, "input", 1)]
    for addr, data in spec["reads"]:
        out.append((data, "output", spec["bits"]))
    for pairs in spec["reads_banked"]:
        for addr, data in pairs:
            out.append((data, "output", spec["bits"]))
    return out


def rng(w):
    return "" if w == 1 else "[%d:0] " % (w - 1)


def model(spec):
    """The module, behavioural: what the flow blackboxes."""
    m = spec["module"]
    lines = [
        "// %s, behavioural: the shape of the generated netlist, never synthesised." % m
    ]
    lines.append("module %s(" % m)
    decl = ["  %-6s %s%s" % (d, rng(w), n) for n, d, w in ports(spec)]
    lines.append(",\n".join(decl))
    lines.append(");")
    lines.append("  reg [%d:0] mem [0:%d];" % (spec["bits"] - 1, spec["words"] - 1))
    lines.append("  always @(posedge %s) begin" % spec["clock"])
    for addr, data, wen in spec["writes"]:
        lines.append("    if (%s) mem[%s] <= %s;" % (wen, addr, data))
    lines.append("  end")
    for addr, data in spec["reads"]:
        lines.append("  assign %s = mem[%s];" % (data, addr))
    banks = spec.get("banks", 1)
    for pairs in spec["reads_banked"]:
        for b, (addr, data) in enumerate(pairs):
            lines.append("  assign %s = mem[%s * %d + %s];" % (data, addr, banks, b))
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def parent(spec, top, inst):
    """A flop on every pin of the file; the read data xor-reduced to sum."""
    ins = [(n, w) for n, d, w in ports(spec) if d == "input" and n != spec["clock"]]
    outs = [(n, w) for n, d, w in ports(spec) if d == "output"]
    total_in = sum(w for _, w in ins)
    lines = [
        "// The parent: every pin of the file behind a register of its own.",
        "module %s(" % top,
        "  input clock,",
        "  input [%d:0] din," % (total_in - 1),
        "  output sum",
        ");",
        "  reg [%d:0] din_q;" % (total_in - 1),
        "  always @(posedge clock) din_q <= din;",
    ]
    con = [".%s(clock)" % spec["clock"]]
    at = 0
    for n, w in ins:
        con.append(".%s(din_q[%d:%d])" % (n, at + w - 1, at))
        at += w
    for n, w in outs:
        lines.append("  wire [%d:0] %s_w;" % (w - 1, n))
        lines.append("  reg  [%d:0] %s_q;" % (w - 1, n))
        con.append(".%s(%s_w)" % (n, n))
    lines.append("  %s %s(\n    %s\n  );" % (spec["module"], inst, ",\n    ".join(con)))
    lines.append("  always @(posedge clock) begin")
    for n, w in outs:
        lines.append("    %s_q <= %s_w;" % (n, n))
    lines.append("  end")
    lines.append("  assign sum = %s;" % " ^ ".join("^%s_q" % n for n, w in outs))
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--spec", required=True)
    ap.add_argument("--sv", required=True)
    ap.add_argument("--placement", required=True)
    ap.add_argument(
        "--top", default=None, help="parent module name (default <module>_scaffold)"
    )
    ap.add_argument(
        "--corner",
        default="40 40",
        help="the array's lower-left corner in the parent, um",
    )
    a = ap.parse_args(argv)
    spec = parse(a.spec)
    top = a.top or spec["module"] + "_scaffold"
    with open(a.sv, "w") as f:
        f.write(model(spec))
        f.write("\n")
        f.write(parent(spec, top, "u_file"))
    with open(a.placement, "w") as f:
        f.write(
            "# <module> <instance path> <x um> <y um>: the array's lower-left corner\n"
        )
        f.write("%s u_file %s\n" % (spec["module"], a.corner))
    print("%s: %d ports, parent %s" % (spec["module"], len(ports(spec)), top))


if __name__ == "__main__":
    main(sys.argv[1:])
