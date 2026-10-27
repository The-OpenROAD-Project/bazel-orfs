"""Toy array structures, one per kind, at any depth and width.

Each toy is a module Arr holding the structure and a top, toy, that
registers every input and output of Arr: every path through the
structure is register to register, so the period measures the structure
and not the I/O constraints. The structures are written as packed
vectors, `reg [N-1:0][W-1:0] r`, the way firtool emits Chisel's vectors:
written as unpacked arrays, yosys's memory passes grind on the
per-entry-updated ones (opt_mem_priority, 74 s for a 256-entry counter),
and the arrays are found by tools/yosys_arrays's passes instead.

    toys.py <kind> <depth> <width> <out.sv> [top [top-only]]
"""

import math
import re
import sys


def _abits(depth):
    return max(1, math.ceil(math.log2(depth)))


def rf(depth, width, reads, writes):
    a = _abits(depth)
    ports = ["input clock"]
    for w in range(writes):
        ports += [
            f"input w{w}_en",
            f"input [{a-1}:0] w{w}_addr",
            f"input [{width-1}:0] w{w}_data",
        ]
    for r in range(reads):
        ports += [f"input [{a-1}:0] r{r}_addr", f"output [{width-1}:0] r{r}_data"]
    body = [
        f"  reg [{width-1}:0] mem [0:{depth-1}];",
        "  always @(posedge clock) begin",
    ]
    body += [f"    if (w{w}_en) mem[w{w}_addr] <= w{w}_data;" for w in range(writes)]
    body += ["  end"]
    body += [f"  assign r{r}_data = mem[r{r}_addr];" for r in range(reads)]
    return ports, body


def masked(depth, width):
    a = _abits(depth)
    lanes = max(1, width // 8)
    lw = width // lanes
    ports = [
        "input clock",
        "input w_en",
        f"input [{a-1}:0] w_addr",
        f"input [{width-1}:0] w_data",
        f"input [{lanes-1}:0] w_mask",
        f"input [{a-1}:0] r_addr",
        f"output [{width-1}:0] r_data",
    ]
    body = [
        f"  reg [{width-1}:0] mem [0:{depth-1}];",
        "  always @(posedge clock) begin",
    ]
    for l in range(lanes):
        hi, lo = (l + 1) * lw - 1, l * lw
        body.append(
            f"    if (w_en & w_mask[{l}]) mem[w_addr][{hi}:{lo}] <= w_data[{hi}:{lo}];"
        )
    body += ["  end", "  assign r_data = mem[r_addr];"]
    return ports, body


def fifo(depth, width):
    a = _abits(depth)
    ports = [
        "input clock",
        "input reset",
        "input push",
        "input pop",
        f"input [{width-1}:0] in_data",
        f"output [{width-1}:0] out_data",
        "output empty",
        "output full",
    ]
    body = [
        f"  reg [{width-1}:0] mem [0:{depth-1}];",
        f"  reg [{a}:0] head, tail;",
        f"  assign empty = head == tail;",
        f"  assign full = head[{a-1}:0] == tail[{a-1}:0] & head[{a}] != tail[{a}];",
        "  always @(posedge clock) begin",
        "    if (reset) begin head <= 0; tail <= 0; end else begin",
        f"      if (push & ~full) begin mem[tail[{a-1}:0]] <= in_data; tail <= tail + 1'b1; end",
        "      if (pop & ~empty) head <= head + 1'b1;",
        "    end",
        "  end",
        f"  assign out_data = mem[head[{a-1}:0]];",
    ]
    return ports, body


def flags(depth, width):
    # per entry width flag bits; two set ports and two clear ports by
    # index and bit, and a redirect that clears every entry from idx to
    # the tail pointer, circularly: a ROB's or a busy table's state
    a = _abits(depth)
    b = _abits(width)
    ports = ["input clock", "input reset"]
    for p in range(2):
        ports += [
            f"input s{p}_en",
            f"input [{a-1}:0] s{p}_idx",
            f"input [{b-1}:0] s{p}_bit",
        ]
        ports += [
            f"input c{p}_en",
            f"input [{a-1}:0] c{p}_idx",
            f"input [{b-1}:0] c{p}_bit",
        ]
    ports += [
        "input flush",
        f"input [{a-1}:0] flush_idx",
        f"input [{a-1}:0] head",
        f"input [{a-1}:0] r_addr",
        f"output [{width-1}:0] r_data",
    ]
    body = [
        f"  reg [{width-1}:0] f [0:{depth-1}];",
        "  always @(posedge clock) begin",
        "    if (reset) begin",
        f"      for (int i = 0; i < {depth}; i++) f[i] <= '0;",
        "    end else begin",
        "      if (s0_en) f[s0_idx][s0_bit] <= 1'b1;",
        "      if (s1_en) f[s1_idx][s1_bit] <= 1'b1;",
        "      if (c0_en) f[c0_idx][c0_bit] <= 1'b0;",
        "      if (c1_en) f[c1_idx][c1_bit] <= 1'b0;",
        "      if (flush)",
        f"        for (int i = 0; i < {depth}; i++)",
        f"          if ({a}'(i - head) >= {a}'(flush_idx - head)) f[i] <= '0;",
        "    end",
        "  end",
        "  assign r_data = f[r_addr];",
    ]
    return ports, body


def counter(depth, width):
    # per entry a down counter: written at allocation, decremented by
    # two writeback ports that may hit the same entry in one cycle
    a = _abits(depth)
    ports = [
        "input clock",
        "input w_en",
        f"input [{a-1}:0] w_addr",
        f"input [{width-1}:0] w_data",
        "input d0_en",
        f"input [{a-1}:0] d0_idx",
        "input d1_en",
        f"input [{a-1}:0] d1_idx",
        f"input [{a-1}:0] r_addr",
        f"output [{width-1}:0] r_data",
        f"output [{depth-1}:0] zero",
    ]
    body = [
        f"  reg [{width-1}:0] c [0:{depth-1}];",
        "  always @(posedge clock)",
        f"    for (int i = 0; i < {depth}; i++)",
        f"      if (w_en && w_addr == {a}'(i)) c[i] <= w_data;",
        f"      else c[i] <= c[i] - {width}'(d0_en && d0_idx == {a}'(i)) - {width}'(d1_en && d1_idx == {a}'(i));",
        "  assign r_data = c[r_addr];",
        "  genvar g;",
        f"  for (g = 0; g < {depth}; g++) begin : z",
        "    assign zero[g] = c[g] == '0;",
        "  end",
    ]
    return ports, body


def window(depth, width, k=4):
    # one write, k consecutive reads from a rotating pointer: a ROB's
    # commit or walk
    a = _abits(depth)
    ports = [
        "input clock",
        "input w_en",
        f"input [{a-1}:0] w_addr",
        f"input [{width-1}:0] w_data",
        f"input [{a-1}:0] head",
    ]
    ports += [f"output [{width-1}:0] r{i}_data" for i in range(k)]
    body = [
        f"  reg [{width-1}:0] mem [0:{depth-1}];",
        "  always @(posedge clock) if (w_en) mem[w_addr] <= w_data;",
    ]
    body += [f"  assign r{i}_data = mem[{a}'(head + {a}'({i}))];" for i in range(k)]
    return ports, body


def cam(depth, width):
    # one write of a key; a query compares every entry and returns the
    # first match: a TLB's or a store queue's lookup
    a = _abits(depth)
    ports = [
        "input clock",
        "input w_en",
        f"input [{a-1}:0] w_addr",
        f"input [{width-1}:0] w_key",
        f"input [{width-1}:0] key",
        "output hit",
        f"output [{a-1}:0] idx",
    ]
    body = [
        f"  reg [{width-1}:0] k [0:{depth-1}];",
        "  always @(posedge clock) if (w_en) k[w_addr] <= w_key;",
        f"  logic [{depth-1}:0] m;",
        f"  always_comb for (int i = 0; i < {depth}; i++) m[i] = k[i] == key;",
        "  assign hit = |m;",
        f"  logic [{a-1}:0] first;",
        "  always_comb begin",
        "    first = '0;",
        f"    for (int i = {depth-1}; i >= 0; i--) if (m[i]) first = {a}'(i);",
        "  end",
        "  assign idx = first;",
    ]
    return ports, body


def agematrix(depth, width):
    # older[i][j]: entry j was allocated before entry i. Allocating i
    # marks every valid entry older; the oldest requester is the one no
    # other requester is older than. Width is unused: the matrix is
    # depth x depth.
    a = _abits(depth)
    ports = [
        "input clock",
        "input reset",
        "input alloc",
        f"input [{a-1}:0] alloc_idx",
        "input free",
        f"input [{a-1}:0] free_idx",
        f"input [{depth-1}:0] req",
        f"output [{depth-1}:0] oldest",
    ]
    body = [
        f"  reg [{depth-1}:0] older [0:{depth-1}];",
        f"  reg [{depth-1}:0] valid;",
        "  always @(posedge clock) begin",
        "    if (reset) valid <= '0;",
        "    else begin",
        "      if (alloc) begin older[alloc_idx] <= valid; valid[alloc_idx] <= 1'b1; end",
        "      if (free) valid[free_idx] <= 1'b0;",
        "    end",
        "  end",
        "  genvar g;",
        f"  for (g = 0; g < {depth}; g++) begin : o",
        "    assign oldest[g] = req[g] & ~|(older[g] & req & valid);",
        "  end",
    ]
    return ports, body


KINDS = {
    "rf1r1w": lambda d, w: rf(d, w, 1, 1),
    "rf4r2w": lambda d, w: rf(d, w, 4, 2),
    "masked": masked,
    "fifo": fifo,
    "flags": flags,
    "counter": counter,
    "window": window,
    "cam": cam,
    "agematrix": agematrix,
}


def _parse_port(p):
    words = p.split()
    direction = words[0]
    rng = words[1] if len(words) == 3 else ""
    return direction, rng, words[-1]


_UNPACKED = re.compile(r"^(\s*)reg \[(\d+):0\] (\w+) \[0:(\d+)\];$")


def _packed(line):
    """`reg [W-1:0] r [0:N-1];` as `reg [N-1:0][W-1:0] r;`."""
    return _UNPACKED.sub(r"\1reg [\4:0][\2:0] \3;", line)


def toy(kind, depth, width, top_name="toy", top_only=False):
    ports, body = KINDS[kind](depth, width)
    body = [_packed(line) for line in body]
    lines = ["module Arr("]
    lines.append(",\n".join("  " + p for p in ports))
    lines += [");"] + body + ["endmodule", ""]
    # the top: Arr's every input from a register, every output into one
    parsed = [_parse_port(p) for p in ports]
    top = [f"module {top_name}(", "  input clock,"]
    top_ports = []
    for direction, rng, name in parsed:
        if name == "clock":
            continue
        top_ports.append(f"  {direction} {rng} {name}".replace("  ", " ", 1))
    top.append(",\n".join(top_ports))
    top.append(");")
    conns = [".clock(clock)"]
    for direction, rng, name in parsed:
        if name == "clock":
            continue
        top.append(f"  reg {rng} {name}_q;")
        if direction == "input":
            top.append(f"  always @(posedge clock) {name}_q <= {name};")
            conns.append(f".{name}({name}_q)")
        else:
            top.append(f"  wire {rng} {name}_d;")
            top.append(f"  always @(posedge clock) {name}_q <= {name}_d;")
            top.append(f"  assign {name} = {name}_q;")
            conns.append(f".{name}({name}_d)")
    top.append("  Arr arr(" + ", ".join(conns) + ");")
    top += ["endmodule", ""]
    # top-only: Arr comes from elsewhere, a generated netlist
    return "\n".join(([] if top_only else lines) + top)


def main():
    kind, depth, width, out = (
        sys.argv[1],
        int(sys.argv[2]),
        int(sys.argv[3]),
        sys.argv[4],
    )
    top_name = sys.argv[5] if len(sys.argv) > 5 else "toy"
    top_only = len(sys.argv) > 6 and sys.argv[6] == "top-only"
    with open(out, "w") as f:
        f.write(toy(kind, depth, width, top_name, top_only))


if __name__ == "__main__":
    main()
