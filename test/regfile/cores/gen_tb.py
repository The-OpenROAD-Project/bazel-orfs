"""A testbench for a register-file spec: the generated netlist beside a reference.

The reference is the RTL module the spec replaces (--rtl-module) or,
when there is none, a behavioural memory built from the spec: words x bits, combinational
reads, writes on the rising clock edge, the zero word, and the
asynchronous reset. Both sides see the same inputs, packed into one
`stim` vector so the C++ driver (tb_main.cc) needs no port names; tb_top
reports `mismatch` when any read differs.

Two writes to one word in one cycle are masked off (the later port's
enable dropped) under `write_priority or`: what an RTL does then is its
own business, and a design may assert it never happens. Under
`write_priority last` they are driven, and the later port must win, as
the behavioural model's later assignment does.

Writes tb_top.v and tb_config.h. Fails on a spec key it does not model.
"""

import argparse
import sys

MODELLED = {
    "module",
    "memory",
    "mode",
    "words",
    "bits",
    "clock",
    "reset",
    "async_reset",
    "read",
    "write",
    "zero_word",
    "write_style",
    "cell",
    "pins",
    "banks",
    "bank_columns",
    "bit_folds",
    "tap_columns",
    "service_sites",
    "lib",
    "flop_output",
    "pin_layer",
    "pin_layer_h",
    "pin_layer_v",
    "periphery",
    "mode",
    "store_name",
    "unused",
    "write_priority",
    "read_banked",
    "bank_order",
    "read_latency",
    "read_reg_name",
}


def read_spec(path):
    spec = {
        "read": [],
        "write": [],
        "zero_word": None,
        "reset": None,
        "unused": [],
        "write_priority": "or",
        "read_banked": [],
        "banks": 1,
        "bank_order": "contiguous",
        "read_latency": 0,
    }
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, *v = line.split()
            if key not in MODELLED:
                sys.exit("%s: gen_tb.py does not model `%s`" % (path, key))
            if key == "read":
                spec["read"].append(v)
            elif key == "write":
                spec["write"].append(v)
            elif key == "unused":
                spec["unused"] += v
            elif key == "write_priority":
                spec["write_priority"] = v[0]
            elif key == "reset":
                spec["reset"] = (v[0], None)
            elif key == "async_reset":
                spec["reset"] = (v[0], v[1])
            elif key == "read_banked":
                spec["read_banked"].append(list(zip(v[0::2], v[1::2])))
            elif key in ("words", "bits", "zero_word", "banks", "read_latency"):
                spec[key] = int(v[0])
            elif key == "bank_order":
                spec[key] = v[0]
            elif key in ("module", "clock"):
                spec[key] = v[0]
    spec.setdefault("clock", "clock")
    for w in spec["write"]:
        if len(w) < 3 and len(spec["write"]) > 1:
            sys.exit("%s: a write port without an enable among several" % path)
    for rb in spec["read_banked"]:
        if len(rb) != spec["banks"]:
            sys.exit("%s: a banked read port without one address per bank" % path)
    return spec


def bank_word(spec, bank, index):
    """The word a banked read port's `index` in `bank` addresses: banks
    contiguous in the address, or interleaved (the word's bank is its
    address modulo banks)."""
    per_bank = spec["words"] // spec["banks"]
    if spec["bank_order"] == "interleaved":
        return "(%s) * %d + %d" % (index, spec["banks"], bank), per_bank
    return "%d + (%s)" % (bank * per_bank, index), per_bank


def addr_bits(words):
    a = 1
    while (1 << a) < words:
        a += 1
    return a


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True)
    p.add_argument("--rtl-module", help="the RTL module the spec replaces")
    p.add_argument("--tie", action="append", default=[], help="RTL-only input=value")
    p.add_argument("--gen-module", required=True)
    p.add_argument("--tb", required=True)
    p.add_argument("--config", required=True)
    p.add_argument(
        "--expect-mismatch",
        action="store_true",
        help="a negative control: the test passes only if a read differs",
    )
    a = p.parse_args()
    s = read_spec(a.spec)
    A = addr_bits(s["words"])
    B = s["bits"]
    W = len(s["write"])
    o = []
    ports = []  # (name, width) of every spec input
    for r in s["read"]:
        ports.append((r[0], A))
    AB = addr_bits(s["words"] // s["banks"])
    for rb in s["read_banked"]:
        for addr, _ in rb:
            ports.append((addr, AB))
    for w in s["write"]:
        ports.append((w[0], A))
        ports.append((w[1], B))
        if len(w) == 3:
            ports.append((w[2], 1))
    stim_bits = sum(n for _, n in ports)
    stim_w = max(96, (stim_bits + 31) // 32 * 32)  # a VlWide, for tb_main.cc
    o.append("// generated by gen_tb.py from %s" % a.spec)
    o.append("module tb_top (")
    o.append("    input clk,")
    o.append("    input rst_act,")
    o.append("    input init_mode,")
    o.append("    input [%d:0] init_addr," % (A - 1))
    o.append("    input [%d:0] stim," % (stim_w - 1))
    o.append("    output mismatch")
    o.append(");")
    off = 0
    raw = {}
    for name, n in ports:
        o.append(
            "  wire [%d:0] %s_raw = stim[%d:%d];" % (n - 1, name, off + n - 1, off)
        )
        raw[name] = name + "_raw"
        off += n
    # init_mode: port 0 writes init_addr, the others are off.
    drive = {}
    for i, r in enumerate(s["read"]):
        drive[r[0]] = raw[r[0]]
    for rb in s["read_banked"]:
        for addr, _ in rb:
            drive[addr] = raw[addr]
    for i, w in enumerate(s["write"]):
        drive[w[0]] = "(init_mode ? %s : %s)" % (
            "init_addr" if i == 0 else raw[w[0]],
            raw[w[0]],
        )
        drive[w[1]] = raw[w[1]]
        if len(w) == 3:
            en = "(init_mode ? 1'b%d : %s)" % (1 if i == 0 else 0, raw[w[2]])
            # Drop this port's write when an earlier port writes its word,
            # unless the spec says which wins: then collisions are tested.
            for j in range(i if s["write_priority"] == "or" else 0):
                ej = "%s_eff" % s["write"][j][2]
                en += " & ~(%s & (%s == %s))" % (
                    ej,
                    drive[s["write"][j][0]],
                    drive[w[0]],
                )
            o.append("  wire %s_eff = %s;" % (w[2], en))
            drive[w[2]] = w[2] + "_eff"
    for name, n in ports:
        o.append("  wire [%d:0] %s = %s;" % (n - 1, name, drive[name]))
    reset = s["reset"]
    if reset:
        rname, level = reset
        val = "~rst_act" if level == "low" else "rst_act"
        o.append("  wire %s = %s;" % (rname, val if level else "1'b%d" % 0))
    outs = []
    for r in s["read"]:
        o.append("  wire [%d:0] %s_ref, %s_gen;" % (B - 1, r[1], r[1]))
        outs.append(r[1])
    for rb in s["read_banked"]:
        for _, data in rb:
            o.append("  wire [%d:0] %s_ref, %s_gen;" % (B - 1, data, data))
            outs.append(data)
    conns = [".%s(clk)" % s["clock"]] + [".%s(%s)" % (n, n) for n, _ in ports]
    if reset:
        conns.append(".%s(%s)" % (reset[0], reset[0]))
    # Inputs the array ignores: held low on both sides.
    conns += [".%s(1'b0)" % u for u in s["unused"]]
    gen = conns + [".%s(%s_gen)" % (d, d) for d in outs]
    o.append("  %s u_gen (%s);" % (a.gen_module, ", ".join(gen)))
    if a.rtl_module:
        ties = [t.split("=", 1) for t in a.tie]
        ref = conns + [".%s(%s_ref)" % (d, d) for d in outs]
        ref += [".%s(%s)" % (k, v) for k, v in ties]
        o.append("  %s u_ref (%s);" % (a.rtl_module, ", ".join(ref)))
    else:
        # A behavioural memory, for a spec with no RTL module.
        o.append("  reg [%d:0] mem [0:%d];" % (B - 1, s["words"] - 1))
        o.append("  integer k;")
        sens = "posedge clk"
        if reset and reset[1]:
            sens += " or %s %s" % (
                "negedge" if reset[1] == "low" else "posedge",
                reset[0],
            )
        o.append("  always @(%s) begin" % sens)
        if reset and reset[1]:
            act = "!%s" % reset[0] if reset[1] == "low" else reset[0]
            o.append("    if (%s) begin" % act)
            o.append("      for (k = 0; k < %d; k = k + 1) mem[k] <= 0;" % s["words"])
            o.append("    end else begin")
        for w in s["write"]:
            cond = w[2] if len(w) == 3 else "1'b1"
            if s["zero_word"] is not None:
                cond = "%s && %s != %d" % (cond, w[0], s["zero_word"])
            o.append(
                "      if (%s && %s < %d) mem[%s] <= %s;"
                % (cond, w[0], s["words"], w[0], w[1])
            )
        if reset and reset[1]:
            o.append("    end")
        o.append("  end")

        def addr(name, width):
            # read_latency 1: the address is registered, a plain flop, and
            # the data follows a cycle later.
            if not s["read_latency"]:
                return name
            o.append("  reg [%d:0] %s_q;" % (width - 1, name))
            o.append("  always @(posedge clk) %s_q <= %s;" % (name, name))
            return name + "_q"

        def read(data, word, limit):
            z = ""
            if s["zero_word"] is not None:
                z = "%s == %d ? %d'd0 : " % (word, s["zero_word"], B)
            o.append(
                "  assign %s_ref = %s%s < %d ? mem[%s] : %d'd0;"
                % (data, z, limit, s["words"], word, B)
            )

        for r in s["read"]:
            a_ = addr(r[0], A)
            read(r[1], a_, a_)
        for rb in s["read_banked"]:
            for bank, (address, data) in enumerate(rb):
                a_ = addr(address, AB)
                word, per_bank = bank_word(s, bank, a_)
                # An index past its bank reads 0, as a word past the end.
                o.append("  wire [%d:0] %s_word = %s;" % (A, data, word))
                read(
                    data,
                    "%s_word" % data,
                    "(%s < %d ? %s_word : %d)" % (a_, per_bank, data, s["words"]),
                )
    o.append(
        "  assign mismatch = %s;"
        % " | ".join("(%s_ref != %s_gen)" % (d, d) for d in outs)
    )
    o.append("endmodule")
    with open(a.tb, "w") as f:
        f.write("\n".join(o) + "\n")
    with open(a.config, "w") as f:
        f.write("// generated by gen_tb.py, for tb_main.cc\n")
        f.write("extern const int kWords = %d;\n" % s["words"])
        f.write("extern const int kStimWords = %d;\n" % (stim_w // 32))
        f.write(
            "extern const bool kAsyncReset = %s;\n"
            % ("true" if reset and reset[1] else "false")
        )
        f.write(
            "extern const bool kExpectMismatch = %s;\n"
            % ("true" if a.expect_mismatch else "false")
        )


if __name__ == "__main__":
    main()
