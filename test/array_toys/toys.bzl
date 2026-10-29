"""The array toys, one flow per kind, depth and width, per arm."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:defs.bzl", "cc_test")
load("@rules_verilator//verilator:defs.bzl", "verilator_cc_library")
load("@rules_verilog//verilog:defs.bzl", "verilog_library")

# generate_ram's register file: the kinds it can build today, and their
# spec's ports
_REGFILE_PORTS = {
    "rf1r1w": (["r0"], ["w0"]),
    "rf4r2w": (["r0", "r1", "r2", "r3"], ["w0", "w1"]),
}

# the kinds tools/yosys_arrays/structgen.py builds as netlists
_STRUCTGEN = ["flags", "counter", "cam", "agematrix"]

_CELLS = """\
cell flop DFFHQNx1_ASAP7_75t_R
cell and2 AND2x2_ASAP7_75t_R
cell or2 OR2x2_ASAP7_75t_R
cell ao22 AO22x2_ASAP7_75t_R
cell inv INVx1_ASAP7_75t_R
cell tap TAPCELL_ASAP7_75t_R
pin_layer M4
"""

# every toy's flow settings
_ARGUMENTS = {
    "AUTO_MEMORIES": "1",
    "CORE_UTILIZATION": "30",
    # turnaround: the timing- and routability-driven global
    # placement is most of a big toy's placement, as in the
    # XSTile carve's development builds
    # and the rest of the XSTile carve's development settings:
    # floorplan's repair_timing (unbuffer) took 271-332 s of a
    # generated 128-deep toy, improve_placement 158 s
    "ENABLE_DPO": "0",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_TIMING_DRIVEN": "0",
    "PLACE_DENSITY": "0.5",
    "SKIP_FLOORPLAN_REPAIR_TIMING": "1",
    "SYNTH_HDL_FRONTEND": "slang",
    # the yosys arm synthesises every array to flops, which
    # is the baseline: ORFS's stop on big flop memories (4 kbit)
    # would stop the larger toys
    "SYNTH_MEMORY_MAX_BITS": "1048576",
}

def _spec(depth, width, reads, writes):
    lines = ["module Arr", "words %d" % depth, "bits %d" % width, "clock clock"]
    lines += ["read %s_addr %s_data" % (r, r) for r in reads]
    lines += ["write %s_addr %s_data %s_en" % (w, w, w) for w in writes]
    return "\n".join(lines) + "\n" + _CELLS

def array_toy(kind, depth, width):
    """A toy, synthesised by yosys and, where it can, generated.

    Args:
      kind: a kind in toys.py.
      depth: words.
      width: bits per word.
    """
    name = "%s_%dx%d" % (kind, depth, width)
    arms = [("yosys", {})]
    if kind in _REGFILE_PORTS:
        reads, writes = _REGFILE_PORTS[kind]
        write_file(
            name = name + "_spec",
            out = name + ".regfile",
            content = [_spec(depth, width, reads, writes)],
            tags = ["manual"],
        )
        arms.append(("generate_ram", {"AUTO_MEMORIES_REGFILES": [":" + name + ".regfile"]}))
    if kind in _STRUCTGEN:
        native.genrule(
            name = name + "_structgen_netlist",
            outs = [name + "_structgen_arr.v"],
            cmd = "$(execpath //tools/yosys_arrays:structgen) %s %d %d $@" % (kind, depth, width),
            tools = ["//tools/yosys_arrays:structgen"],
            tags = ["manual"],
        )
        arms.append(("structgen", {}))
    for arm, sources in arms:
        flow = "%s_%s" % (name, arm)

        # the top is named after the flow: a flow's results are keyed on it
        native.genrule(
            name = flow + "_rtl",
            outs = [flow + ".sv"],
            cmd = "$(execpath :toys) %s %d %d $@ %s%s" % (
                kind,
                depth,
                width,
                flow,
                " top-only" if arm == "structgen" else "",
            ),
            tools = [":toys"],
            tags = ["manual"],
        )
        orfs_flow(
            name = flow,
            arguments = _ARGUMENTS,
            last_stage = "grt",
            sources = {"SDC_FILE": [":constraint.sdc"]} | sources,
            tags = ["manual"],
            verilog_files = [":" + flow + ".sv"] + (
                [":" + name + "_structgen_arr.v"] if arm == "structgen" else []
            ),
        )
        orfs_run(
            name = flow + "_period",
            src = ":" + flow + "_floorplan",
            outs = [flow + "_period.json"],
            script = ":period_probe.tcl",
            tags = ["manual"],
            user_arguments = {
                "OUTPUT_JSON": "$(location %s_period.json)" % flow,
            },
        )

# the ohsched toy's generated-arm variants, each a hypothesis about what
# keeps the generated array from beating flops: the spec lines that test it
OHSCHED_VARIANTS = {
    # the boundary: the decoders and read muxes as Verilog, which
    # synthesis maps and retimes with the logic around them
    "periphery": ["periphery verilog"],
}

def ohsched_toy(kind, depth, width):
    """The ohsched toy (ohsched.py) of a kind, in both arms, with a
    co-simulation of the two arms and its negative control.

    Args:
      kind: `fill` or `lanes`, as ohsched.py's KINDS.
      depth: entries, as KINDS gives them: names the toy.
      width: payload bits, as KINDS gives them: names the toy.
    """
    name = "ohsched_%s_%dx%d" % (kind, depth, width)
    for arm in ["yosys", "generate_ram"]:
        native.genrule(
            name = "%s_%s_rtl" % (name, arm),
            outs = ["%s_%s.v" % (name, arm)],
            cmd = "$(execpath :ohsched) rtl %s %s %s_%s $@" % (kind, arm, name, arm),
            tools = [":ohsched"],
        )

    # the generated arm's variants: each a set of spec lines, one lever
    # each
    for flow, variant, spec_lines in [
        (name + "_yosys", None, None),
        (name + "_generate_ram", None, []),
    ] + [
        (name + "_generate_ram", v, lines)
        for v, lines in OHSCHED_VARIANTS.items()
    ]:
        sources = {}
        if spec_lines != None:
            spec = "%s%s" % (name, "_" + variant if variant else "")
            native.genrule(
                name = spec + "_spec",
                outs = [spec + ".regfile"],
                cmd = "$(execpath :ohsched) spec %s $@ %s" % (
                    kind,
                    " ".join(["'%s'" % line for line in spec_lines]),
                ),
                tools = [":ohsched"],
            )
            sources = {"AUTO_MEMORIES_REGFILES": [":" + spec + ".regfile"]}
        orfs_flow(
            name = flow,
            # the top around the array is retimed, as the logic around
            # such an array is
            arguments = _ARGUMENTS | {"SYNTH_RETIME_MODULES": flow},
            last_stage = "grt",
            sources = {"SDC_FILE": [":constraint.sdc"]} | sources,
            tags = ["manual"],
            variant = variant,
            verilog_files = [":" + flow + ".v"],
        )
    native.genrule(
        name = name + "_mutated_rtl",
        outs = [name + "_mutated.v"],
        cmd = "$(execpath :ohsched) rtl %s generate_ram %s_generate_ram $@ --mutate" % (kind, name),
        tools = [":ohsched"],
    )
    native.genrule(
        name = name + "_tb",
        outs = [name + "_tb.v"],
        cmd = "$(execpath :ohsched) tb %s %s_yosys %s_generate_ram $@" % (kind, name, name),
        tools = [":ohsched"],
    )

    # both arms under the same random stimulus, every output compared;
    # the negative control swaps two rows of the generated arm's pick
    # decode and passes only if some output differs
    for test, generated, defines in [
        ("sim_test", ":%s_generate_ram.v" % name, []),
        ("mutated_sim_test", ":%s_mutated.v" % name, ["EXPECT_MISMATCH"]),
    ]:
        verilog_library(
            name = "%s_%s_rtl" % (name, test),
            srcs = [":%s_tb.v" % name, ":%s_yosys.v" % name, generated],
        )
        verilator_cc_library(
            name = "%s_%s_tb" % (name, test),
            module = ":%s_%s_rtl" % (name, test),
            module_top = "tb",
            trace_mode = "none",
            vopts = [
                "-Wno-fatal",
                "--x-initial",
                "0",
            ],
        )
        cc_test(
            name = "%s_%s" % (name, test),
            size = "small",
            srcs = ["ohsched_tb_main.cc"],
            defines = defines,
            deps = [":%s_%s_tb" % (name, test)],
        )
