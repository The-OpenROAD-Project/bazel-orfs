# How the constraint round trip scales with design size.
#
# The asap7 platform constraints say `-from [all_inputs] -to [all_registers]`
# in three set_max_delay and four group_path commands. write_sdc cannot say
# "all registers", so the generated 1_synth.sdc names every register clock
# pin seven times, and every substep of the flow re-reads it. These designs
# make the register count a parameter so that cost is a measured curve, not
# an anecdote: N flops of pipeline, 2W+2 ports, seconds to synthesize.
#
#   bazelisk build //test/sdc_scale:sdc_scale_200k_timing
#
# writes results/asap7/sdc_scale/200k/timing/timing.json with seconds for
# read_db, read_sdc, write_sdc and write_db on the synthesized design.
# The *_restore targets need an OpenROAD that stores constraints in the
# .odb (read_db -sdc): they time the restore and write the constraints
# back out so the caller can diff them against 1_synth.sdc.
load("@rules_python//python:defs.bzl", "py_binary")
load("//:openroad.bzl", "orfs_flow", "orfs_run")

py_binary(
    name = "gen_sdc_scale",
    srcs = ["gen_sdc_scale.py"],
)

# Register counts to sweep. The bus width is fixed so the port count stays
# small and constant: what varies is the all_registers expansion.
SIZES = {
    "50k": 50000,
    "200k": 200000,
    "800k": 800000,
}

BUS_WIDTH = 64

# Synthesis only, and as little of it as possible: the design is a shift
# register, there is nothing for abc to optimize and nothing to report.
SYNTH_SETTINGS = {
    "SKIP_REPORT_METRICS": "1",
    "SYNTH_HIERARCHICAL": "0",
}

[
    genrule(
        name = "sdc_scale_{}_v".format(size),
        outs = ["sdc_scale_{}.v".format(size)],
        cmd = "$(execpath :gen_sdc_scale) {} {} $@".format(flops, BUS_WIDTH),
        tools = [":gen_sdc_scale"],
    )
    for size, flops in SIZES.items()
]

[
    orfs_flow(
        name = "sdc_scale",
        arguments = SYNTH_SETTINGS,
        last_stage = "synth",
        pdk = "@orfs//flow:asap7",
        sources = {
            "SDC_FILE": [":constraint.sdc"],
        },
        top = "sdc_scale",
        variant = size,
        verilog_files = [":sdc_scale_{}.v".format(size)],
    )
    for size in SIZES
]

[
    orfs_run(
        name = "sdc_scale_{}_timing".format(size),
        src = ":sdc_scale_{}_synth".format(size),
        out_dir = "results/asap7/sdc_scale/{}/timing".format(size),
        script = ":sdc_timing.tcl",
    )
    for size in SIZES
]

[
    orfs_run(
        name = "sdc_scale_{}_restore".format(size),
        src = ":sdc_scale_{}_synth".format(size),
        out_dir = "results/asap7/sdc_scale/{}/restore".format(size),
        script = ":sdc_restore.tcl",
        tags = ["manual"],
    )
    for size in SIZES
]

# The same round trip on a real ORFS design: nangate45/bp_be_top has the
# most top-level ports of any design in ORFS CI (3031), so its generated
# .sdc is the largest one the public flow produces today.
orfs_run(
    name = "bp_be_top_timing",
    src = "@orfs//flow/designs/nangate45/bp_be_top:bp_be_top_synth",
    out_dir = "results/nangate45/bp_be_top/base/timing",
    script = ":sdc_timing.tcl",
)

orfs_run(
    name = "bp_be_top_restore",
    src = "@orfs//flow/designs/nangate45/bp_be_top:bp_be_top_synth",
    out_dir = "results/nangate45/bp_be_top/base/restore",
    script = ":sdc_restore.tcl",
    tags = ["manual"],
)
