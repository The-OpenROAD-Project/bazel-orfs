"""One tiny design per generate_ram option, through the flow to route."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load("@bazel_skylib//rules:write_file.bzl", "write_file")

# 16 words of 8 bits, two reads and a write, asap7's cells: each option
# adds its lines to this
BASE = """\
module RegFile
words 16
bits 8
clock clock
read r0_addr r0_data
read r1_addr r1_data
cell icg ICGx1_ASAP7_75t_R
cell flop DFFHQNx1_ASAP7_75t_R
cell flop_r DFFASRHQNx1_ASAP7_75t_R
cell tie_hi TIEHIx1_ASAP7_75t_R
cell and2 AND2x2_ASAP7_75t_R
cell or2 OR2x2_ASAP7_75t_R
cell ao22 AO22x2_ASAP7_75t_R
cell inv INVx1_ASAP7_75t_R
cell tap TAPCELL_ASAP7_75t_R
pin_layer M4
"""

ONE_WRITE = "write w0_addr w0_data w0_en\n"
TWO_WRITES = ONE_WRITE + "write w1_addr w1_data w1_en\n"

def option_flow(name, lines, writes = None, base = BASE):
    """RegFile with `lines` added, inlined in a parent of flops, to route.

    Args:
      name: the option's name, the flow's.
      lines: the spec lines that turn the option on.
      writes: the spec's write ports; one when None.
      base: the spec without its write ports and the option.
    """
    write_file(
        name = name + "_spec",
        out = name + ".regfile",
        content = [base + (writes or ONE_WRITE) + lines],
        tags = ["manual"],
    )
    native.genrule(
        name = name + "_rtl",
        srcs = [":" + name + ".regfile"],
        outs = [name + ".sv"],
        cmd = "$(execpath //test/structured_netlist:scaffold_gen) --spec $< --sv $@ --top " + name,
        tools = ["//test/structured_netlist:scaffold_gen"],
        tags = ["manual"],
    )
    orfs_flow(
        name = name,
        arguments = {
            "AUTO_MEMORIES": "1",
            "CORE_UTILIZATION": "30",
            "PLACE_DENSITY": "0.5",
            "SYNTH_HDL_FRONTEND": "slang",
        },
        last_stage = "route",
        sources = {
            "AUTO_MEMORIES_REGFILES": [":" + name + ".regfile"],
            "SDC_FILE": ["//test/regfile:constraint.sdc"],
        },
        tags = ["manual"],
        verilog_files = [":" + name + ".sv"],
    )
