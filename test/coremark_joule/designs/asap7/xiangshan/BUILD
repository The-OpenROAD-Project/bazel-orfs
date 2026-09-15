load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "hier_probe", "stage_power", "stage_power_units")

exports_files(["constraints.sdc"])

design(
    config = "config.mk",
    # The annealer's knobs, read by anneal_in_flow.tcl rather than by ORFS.
    user_arguments = [
        "ANNEAL_SEED",
        "ANNEAL_DEPTH",
        "ANNEAL_MIN_CLUSTER",
        "ANNEAL_CHANNEL_UM",
        "ANNEAL_FILL",
    ],
    # The placer and its inventory dump, staged into the floorplan sandbox.
    user_sources = [
        "ANNEAL_DUMP_TCL",
        "ANNEAL_PY",
    ],
    # All read at macro placement only; scoped so a knob edit re-runs the
    # floorplan and not the 48-minute synthesis before it.
    user_stages = {
        v: ["floorplan"]
        for v in [
            "ANNEAL_SEED",
            "ANNEAL_DEPTH",
            "ANNEAL_MIN_CLUSTER",
            "ANNEAL_CHANNEL_UM",
            "ANNEAL_FILL",
            "ANNEAL_DUMP_TCL",
            "ANNEAL_PY",
        ]
    },
    visibility = ["//test/coremark_joule:__subpackages__"],
)

grt_netlist(
    name = "cmj_xiangshan_grt_netlist",
    src = ":XSCore_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# XiangShan is the core the per-unit breakdown is for: its modules are
# monomorphic, so unlike SERV's parameterized ones they should reach the
# ODB with their names intact, and its hierarchy maps onto the categories
# the literature reports.
stage_power_units(
    name = "cmj_xiangshan_grt_power_units",
    src = ":XSCore_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2/core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_xiangshan_grt_power",
    src = ":XSCore_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2/core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Did the sixteen SRAMs reach the netlist as macros? The flow can detect a
# memory, write its views, list it in blackboxes.txt and synthesise it as
# flip-flops anyway, and nothing fails -- which is exactly what happened
# to every one of these before patches 0069 and 0070: memories.json held
# two entries, both declined, and the L1s were 1.2 Mbit of flops. The
# expected list is declared, so an empty blackboxes.txt fails here rather
# than passing vacuously. Every name is a firtool array_<depth>x<width>
# module; the four-row array_4x786 and the two-row queues stay flops by
# the macro floors, on purpose.
CONVERTED_MEMORIES = [
    "array_128x138",
    "array_128x18",
    "array_128x192",
    "array_128x38",
    "array_128x48",
    "array_128x76",
    "array_256x46",
    "array_256x66",
    "array_256x8",
    "array_256x86",
    "array_256x88",
    "array_32x148",
    "array_512x17",
    "array_64x112",
    "array_64x114",
    "array_64x16",
]

genrule(
    name = "cmj_xiangshan_memories_applied",
    srcs = [":XSCore_synth"],
    outs = ["cmj_xiangshan_memories_applied.txt"],
    cmd = "files=$$(echo $(locations :XSCore_synth) | tr ' ' '\\n'); " +
          "$(execpath //test/coremark_joule/scripts:check_memories_applied) " +
          "$$(echo \"$$files\" | grep '/memories$$')/blackboxes.txt " +
          "$$(echo \"$$files\" | grep '/1_2_yosys.v$$') " +
          "--expect " + " ".join(CONVERTED_MEMORIES) + " > $@",
    tags = ["manual"],
    tools = ["//test/coremark_joule/scripts:check_memories_applied"],
)

# Whether the kept module boundaries survived into the ODB. Cheap, and
# the failure it catches is silent: the flow completes, the netlist is
# valid, and the breakdown simply comes back empty.
[
    hier_probe(
        name = "cmj_xiangshan_hier_" + stage,
        src = ":XSCore_" + stage,
        stage = stage,
    )
    for stage in [
        "synth",
        "grt",
    ]
]
