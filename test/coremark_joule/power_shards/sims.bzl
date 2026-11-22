"""The toy's simulations: one per shard, and the references."""

load("@rules_cc//cc:defs.bzl", "cc_binary")
load("@rules_verilator//verilator:defs.bzl", "verilator_cc_library")
load("@rules_verilog//verilog:defs.bzl", "verilog_library")

# The SoC's RTL: test/planned_parent's, BlockA and BlockC in their kept
# submodules (blocka_hier.sv and blockc_hier.sv, later, replace
# blocks.sv's), BlockB with its one clock.
RTL = [
    "//test/planned_parent:top.sv",
    "//test/planned_parent:files.sv",
    "//test/planned_parent:blocks.sv",
    ":blocka_hier.sv",
    ":blockc_hier.sv",
]

# the ports the SDCs put the toy's one clock on
CLOCK_PORTS = [
    "clock",
    "clock_ext",
]

# sim/BUILD.bazel's gate options, and why
VOPTS = [
    "--trace-underscore",
    "-Wno-IMPLICIT",
    "-Wno-MODDUP",
    "-Wno-PINMISSING",
    "-Wno-STMTDLY",
    "-Wno-SPECIFYIGN",
    "-Wno-WIDTH",
    "-Wno-UNOPTFLAT",
    "-Wno-TIMESCALEMOD",
    "-Wno-UNUSEDSIGNAL",
    "-Wno-DECLFILENAME",
]

def toy_sim(name, netlist = None, gates = [], scope = None, cycles = 2000):
    """One simulation: the parent's netlist or the RTL, units as gates.

    Writes <name>_raw.saif (the SAIF, all of it or only `scope`) and
    <name>_out.txt (the outputs, every cycle).

    Args:
      name: the simulation.
      netlist: the parent's netlist; None: the top is RTL.
      gates: the units' netlists swapped in.
      scope: the only scope the SAIF is to carry, Verilator's dotted name
        below its root (mini_top.u_blocka): everything else is not
        traced at all, by a Verilator configuration compiled in.
      cycles: cycles traced, after the warm-up.
    """
    native.genrule(
        name = name + "_stitch",
        srcs = RTL + ([netlist] if netlist else []) + gates,
        outs = [
            name + ".sv",
            name + "_report.json",
        ],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:gate_stitch)",
            "--top mini_top --cell-suffix _ASAP7_",
        ] + (["--netlist $(location %s)" % netlist] if netlist else []) + [
            "--rtl-file $(location %s)" % f
            for f in RTL
        ] + [
            "--gate-netlist $(location %s)" % g
            for g in gates
        ] + [
            "--clock-port %s" % c
            for c in CLOCK_PORTS
        ] + [
            "--out $(location %s.sv)" % name,
            "--report $(location %s_report.json)" % name,
        ]),
        tags = ["manual"],
        tools = ["//test/coremark_joule/scripts:gate_stitch"],
    )
    trace = []
    if scope:
        # a configuration in a .v file: verilog_library takes no .vlt
        native.genrule(
            name = name + "_trace",
            outs = [name + "_trace.v"],
            cmd = "printf '`verilator_config\\ntracing_off -scope \"*\"\\ntracing_on -scope \"%s*\"\\n' > $@" % scope,
            tags = ["manual"],
        )
        trace = [":%s_trace.v" % name]
    verilog_library(
        name = name,
        srcs = [":%s.sv" % name] + ([netlist] if netlist else []) + trace,
        tags = ["manual"],
        deps = [":cells_init"],
    )
    verilator_cc_library(
        name = name + "_lib",
        copts = [
            "-O2",
            "-Wno-all",
        ],
        module = ":" + name,
        module_top = "mini_top",
        tags = ["manual"],
        trace_mode = "saif",
        vopts = VOPTS,
    )
    cc_binary(
        name = name + "_tb",
        srcs = ["tb.cc"],
        copts = ["-O2"],
        tags = ["manual"],
        deps = [":%s_lib" % name],
    )

    # at the SDC's 1,000 ps
    native.genrule(
        name = name + "_run",
        srcs = [":%s_tb" % name],
        outs = [
            name + "_raw.saif",
            name + "_out.txt",
        ],
        cmd = "$(execpath :{n}_tb) $(location {n}_raw.saif) {c} 1000 $(location {n}_out.txt)".format(
            n = name,
            c = cycles,
        ),
        tags = ["manual"],
    )
