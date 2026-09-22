#!/usr/bin/env python3
"""The planned parent in miniature: four blocks, three placed netlists, a plan.

    mini_gen.py --out DIR

Writes what the planner and the flows consume for a parent small enough to
route in minutes and shaped like the XiangShan study's: four hardened
blocks along one edge with registered interfaces, one of them with ports
to the parent's own ports, block-to-block traffic between two of them,
three generated register files as placed netlists inside the parent's
logic, one of them with a dead column, and the parent's logic answering
every block pin with a flop of its own.

  blocks.sv     the four block modules, each pins in and out, registered
  top.sv        the parent: blocks, files, registers, ports
  File*.regfile the three files in mode netlist (the SmallFile shape)
  plan.json     the planner's input: tech, margins, parent, macros, netlists
  partners.txt  the pin partner dump the planner orders pin segments by,
                in probe_pin_partners.tcl's format, from the known wiring

Plain Verilog-2005 and stdlib python; the numbers are chosen so every
block has hundreds of pins, not thousands: the geometry of the study at a
fiftieth of the size.
"""

import argparse
import json
import os
import sys

# name, pins to the parent's logic (in + out), pins to the parent's ports
BLOCKS = [
    ("BlockA", 240, 0),
    ("BlockB", 320, 32),
    ("BlockC", 200, 0),
    ("BlockD", 160, 0),
]
# BlockA's first CROSS outputs feed BlockB's first CROSS inputs directly
CROSS = 16
# the files: name, words, bits, read ports, write ports, dead bit (never read)
FILES = [
    ("FileA", 16, 8, 2, 2, 0),
    ("FileB", 16, 8, 2, 2, None),
    ("FileC", 16, 8, 1, 1, None),
]
# the SmallFile shape's outline, generously, for the plan's netlist row
FILE_W_UM, FILE_H_UM = 30.0, 10.5

TECH = {
    "pin_pitch_um": 0.096,
    "pin_layers": 2,
    "track_density_per_um": 48.6,
    "wire_ps_per_um": 0.6,
    "site_um": 0.054,
    "row_um": 0.27,
    "lattice_x_um": 0.144,
    "lattice_y_um": 2.16,
    "pin_layers_v": [
        {"name": "M3", "pitch": 0.036, "offset": 0.009, "width": 0.018},
        {"name": "M5", "pitch": 0.048, "offset": 0.012, "width": 0.024},
    ],
    "pin_layers_h": [{"name": "M4", "pitch": 0.048, "offset": 0.012, "width": 0.024}],
}


def block_sv(name, pins, ports):
    h = pins // 2
    ext = ""
    ext_logic = ""
    if ports:
        e = ports // 2
        ext = ",\n    input [{0}:0] ext_in,\n    output [{0}:0] ext_out".format(e - 1)
        ext_logic = """  reg [{0}:0] ext_r;
  always @(posedge clock) ext_r <= ext_in ^ din_r[{0}:0];
  assign ext_out = ext_r;
""".format(e - 1)
    return """// {name}: {h} pins in, {h} out, registered on both sides of the boundary.
module {name} (
    input clock,
    input [{hh}:0] din,
    output [{hh}:0] dout{ext}
);
  reg [{hh}:0] din_r;
  reg [{hh}:0] dout_r;
  always @(posedge clock) begin
    din_r <= din;
    dout_r <= {{din_r[{hh2}:0], din_r[{hh}]}} ^ din_r;
  end
  assign dout = dout_r;
{ext_logic}endmodule
""".format(name=name, h=h, hh=h - 1, hh2=h - 2, ext=ext, ext_logic=ext_logic)


def file_sv(name, words, bits, nr, nw):
    """The behavioural register file the flow blackboxes and the generator replaces."""
    aw = max(1, (words - 1).bit_length())
    ports = ["    input clock"]
    for r in range(nr):
        ports.append("    input [{}:0] io_readPorts_{}_addr".format(aw - 1, r))
        ports.append("    output [{}:0] io_readPorts_{}_data".format(bits - 1, r))
    for w in range(nw):
        ports.append("    input io_writePorts_{}_wen".format(w))
        ports.append("    input [{}:0] io_writePorts_{}_addr".format(aw - 1, w))
        ports.append("    input [{}:0] io_writePorts_{}_data".format(bits - 1, w))
    body = ["  reg [{}:0] mem [0:{}];".format(bits - 1, words - 1)]
    for r in range(nr):
        body.append("  assign io_readPorts_{0}_data = mem[io_readPorts_{0}_addr];".format(r))
    body.append("  always @(posedge clock) begin")
    for w in range(nw):
        body.append("    if (io_writePorts_{0}_wen) mem[io_writePorts_{0}_addr] <= io_writePorts_{0}_data;".format(w))
    body.append("  end")
    return "module {} (\n{}\n);\n{}\nendmodule\n".format(name, ",\n".join(ports), "\n".join(body))


def file_spec(name, words, bits, nr, nw):
    lines = [
        "# {}: a placed netlist inside the miniature parent (mode netlist).".format(name),
        "module " + name,
        "mode netlist",
        "words {}".format(words),
        "bits {}".format(bits),
        "clock clock",
    ]
    for r in range(nr):
        lines.append("read io_readPorts_{0}_addr io_readPorts_{0}_data".format(r))
    for w in range(nw):
        lines.append("write io_writePorts_{0}_addr io_writePorts_{0}_data io_writePorts_{0}_wen".format(w))
    lines += [
        "cell flop DFFHQNx1_ASAP7_75t_R",
        "cell and2 AND2x2_ASAP7_75t_R",
        "cell or2 OR2x2_ASAP7_75t_R",
        "cell ao22 AO22x2_ASAP7_75t_R",
        "cell inv INVx1_ASAP7_75t_R",
        "cell tap TAPCELL_ASAP7_75t_R",
        "pin_layer M4",
        "tap_columns 8",
        "service_sites 40",
    ]
    return "\n".join(lines) + "\n"


def top_sv():
    """The parent. Every block output is registered in the parent and fed
    back to a block input; BlockA's first CROSS outputs go to BlockB
    directly; BlockB's ext pins are the parent's ports; the files are
    written from and read into parent registers, FileA's dead bit unread."""
    decl, inst, logic, ports = [], [], [], ["    input clock", "    input [63:0] seed", "    output [63:0] sum"]
    sums = []
    for name, pins, ext in BLOCKS:
        h = pins // 2
        lo = name.lower()
        decl.append("  wire [{0}:0] {1}_din, {1}_dout;".format(h - 1, lo))
        decl.append("  reg  [{0}:0] {1}_r;".format(h - 1, lo))
        con = ".clock(clock), .din({0}_din), .dout({0}_dout)".format(lo)
        if ext:
            e = ext // 2
            ports.append("    input [{}:0] {}_ext_in".format(e - 1, lo))
            ports.append("    output [{}:0] {}_ext_out".format(e - 1, lo))
            con += ", .ext_in({0}_ext_in), .ext_out({0}_ext_out)".format(lo)
        inst.append("  {} u_{} ({});".format(name, lo, con))
        logic.append("    {0}_r <= {0}_dout ^ {{{1}{{seed}}}};".format(lo, (h + 63) // 64))
        if name == "BlockB":
            decl.append("  wire [{0}:0] blockb_in_rest = blockb_r[{0}:0];".format(h - 1))
            inst.append("  assign blockb_din = {{blockb_r[{0}:{1}], blocka_dout[{2}:0]}};".format(h - 1, CROSS, CROSS - 1))
        else:
            inst.append("  assign {0}_din = {0}_r;".format(lo))
        sums.append("^{}_r".format(lo))
    for name, words, bits, nr, nw, dead in FILES:
        aw = max(1, (words - 1).bit_length())
        lo = name.lower()
        con = [".clock(clock)"]
        for r in range(nr):
            decl.append("  reg  [{}:0] {}_ra{};".format(aw - 1, lo, r))
            decl.append("  wire [{}:0] {}_rd{};".format(bits - 1, lo, r))
            decl.append("  reg  [{}:0] {}_rd{}_q;".format(bits - 1, lo, r))
            con.append(".io_readPorts_{0}_addr({1}_ra{0}), .io_readPorts_{0}_data({1}_rd{0})".format(r, lo))
            logic.append("    {0}_ra{1} <= seed[{2}:{3}] ^ blocka_r[{2}:{3}];".format(lo, r, aw - 1 + 4 * r, 4 * r))
            if dead is None:
                logic.append("    {0}_rd{1}_q <= {0}_rd{1};".format(lo, r))
            else:
                # the dead bit is never read: a column for eliminate_dead_logic
                keep = [i for i in range(bits) if i != dead]
                logic.append("    {0}_rd{1}_q <= {{{2}}};".format(lo, r, ", ".join("{}_rd{}[{}]".format(lo, r, i) for i in reversed(keep)) + ", 1'b0"))
            sums.append("^{}_rd{}_q".format(lo, r))
        for w in range(nw):
            decl.append("  reg  [{}:0] {}_wa{};".format(aw - 1, lo, w))
            decl.append("  reg  [{}:0] {}_wd{};".format(bits - 1, lo, w))
            decl.append("  reg  {}_we{};".format(lo, w))
            con.append(".io_writePorts_{0}_wen({1}_we{0}), .io_writePorts_{0}_addr({1}_wa{0}), .io_writePorts_{0}_data({1}_wd{0})".format(w, lo))
            logic.append("    {0}_wa{1} <= blockc_r[{2}:{3}];".format(lo, w, aw - 1 + 4 * w, 4 * w))
            logic.append("    {0}_wd{1} <= blockd_r[{2}:{3}];".format(lo, w, bits - 1 + 8 * w, 8 * w))
            logic.append("    {0}_we{1} <= blockb_r[{2}];".format(lo, w, w))
        inst.append("  {} u_{} ({});".format(name, lo, ", ".join(con)))
    return """// The miniature planned parent: four blocks along its bottom edge, three
// placed register files in its logic, a flop in the parent for every pin.
module mini_top (
{ports}
);
{decl}
{inst}
  always @(posedge clock) begin
{logic}
  end
  assign sum = ({sums}) ? seed : ~seed;
endmodule
""".format(ports=",\n".join(ports), decl="\n".join(decl), inst="\n".join(inst), logic="\n".join(logic), sums=" ^ ".join(sums))


def partners():
    """pin <block> <pin> <partner> <partner pin>: the parent's wiring, as the probe would dump it."""
    out = []
    for name, pins, ext in BLOCKS:
        h = pins // 2
        for i in range(h):
            if name == "BlockA" and i < CROSS:
                out.append("pin BlockA dout[{0}] BlockB din[{0}]".format(i))
            else:
                out.append("pin {} dout[{}] logic -".format(name, i))
            if name == "BlockB" and i < CROSS:
                out.append("pin BlockB din[{0}] BlockA dout[{0}]".format(i))
            else:
                out.append("pin {} din[{}] logic -".format(name, i))
        for i in range(ext // 2):
            out.append("pin {} ext_in[{}] port -".format(name, i))
            out.append("pin {} ext_out[{}] port -".format(name, i))
    return "\n".join(out) + "\n"


def plan(out_dir):
    # a block's area: rows enough for its flops and xors at a low density,
    # and never narrower than its pins need; the planner draws the outline
    macros = []
    for name, pins, ext in BLOCKS:
        area = max(2500.0, pins * 12.0)
        macros.append({"name": name, "pins": pins + ext, "area_um2": area, "keep": []})
    return {
        "tech": TECH,
        "margins": {"pin_side": 1.5, "channel_min_um": 20, "lateral": 0.5, "aspect_cap": 3.0, "gap_um": 10.8},
        "parent": {"cell_area_um2": 4000.0, "density": 0.5, "core_margin_um": 10, "keep": []},
        "macros": macros,
        # FileA and FileB in the planner's row along the region's top; the
        # region between the two block rows is 125 um wide, so FileC takes
        # the row below, at the same left edge (gap_um in from the region)
        "netlists": [
            {"module": "FileA", "instance": "u_filea", "w_um": FILE_W_UM, "h_um": FILE_H_UM},
            {"module": "FileB", "instance": "u_fileb", "w_um": FILE_W_UM, "h_um": FILE_H_UM},
            {"module": "FileC", "instance": "u_filec", "w_um": FILE_W_UM, "h_um": FILE_H_UM, "x_um": 20.944, "y_um": 107.4},
        ],
        # the planner opens this from where it runs: the repo root
        "pin_partners": os.path.join(out_dir, "partners.txt"),
    }


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv[1:])
    os.makedirs(a.out, exist_ok=True)

    def write(name, text):
        with open(os.path.join(a.out, name), "w") as f:
            f.write(text)

    write("blocks.sv", "\n".join(block_sv(n, p, e) for n, p, e in BLOCKS))
    write("files.sv", "\n".join(file_sv(n, w, b, r, ww) for n, w, b, r, ww, _ in FILES))
    write("top.sv", top_sv())
    for n, w, b, r, ww, _ in FILES:
        write(n + ".regfile", file_spec(n, w, b, r, ww))
    write("partners.txt", partners())
    write("plan.json", json.dumps(plan(a.out), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
