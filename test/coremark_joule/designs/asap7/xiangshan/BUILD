load("@bazel-orfs//:openroad.bzl", "odb_debug")
load("//test/coremark_joule/flow:power.bzl", "census_probe", "grt_netlist", "hier_probe", "physical_probe", "stage_power", "stage_power_units")
load(":plan/plan.bzl", "PLAN")
load(":xiangshan.bzl", "xiangshan_flow")

exports_files(["constraints.sdc"])

# XiangShan's ClockGate onto ASAP7's ICG (xs_icg.ys says why and how);
# test/xs_clockgate checks the mapping on a small design.
exports_files([
    "xs_icg.ys",
    "xs_icg_map.v",
])

# The parent's three placed netlists, at real size in a parent of flops:
# the battery's rung for what the resizer, CTS and the router do to an
# array of this size (test/structured_netlist, scaffold.bzl).
exports_files(
    [
        "IntRegFile.regfile",
        "RenameBufferFile.regfile",
        "RobEntryFile.regfile",
    ],
    visibility = ["//test/structured_netlist:__pkg__"],
)

# The planned parent: the blocks the macro selection tables named, each a
# real flow at the outline plan_floorplan.py drew with its pins on one
# side, the parent at the planned die. plan/ is generated (see
# .claude/commands/macro-selection.md, step 3); regenerate it, never edit it:
# plan/plan.json is its input, with pin_partners.txt beside it from
# probe_pin_partners.tcl on XSTile_synth_odb_debug (GUI_TIMING=0).
xiangshan_flow(
    name = "XSTile",
    grt_probe_blocks = ["Frontend"],
    plan = PLAN,
)

# Frontend's timing where its abstract is written (cts) and after the
# global-route stage's own repair (the grt probe), for the comparison of
# the two and whether the cts checkpoint ranks the paths the same way.
odb_debug(
    name = "Frontend_cts_odb_debug",
    src = ":Frontend_cts",
)

odb_debug(
    name = "Frontend_grt_probe_grt_odb_debug",
    src = ":Frontend_grt_probe_grt",
)

# The planned parent's synthesis: the blocks as blackboxes over the flat
# parent logic, where probe_pin_partners.tcl reads which block each block
# pin talks to (geometry only: run with GUI_TIMING=0).
odb_debug(
    name = "XSTile_synth_odb_debug",
    src = ":XSTile_synth",
)

# The placement gate of the planned parent: free sites and RUDY before
# CTS and global route spend their hours (/odb-debug).
odb_debug(
    name = "XSTile_place_odb_debug",
    src = ":XSTile_place",
)

# The parent's KPI checkpoints (README.md): the reg2reg group with a clock
# tree, and the route-0 overflow. Timing on CTS needs about 33 GB.
odb_debug(
    name = "XSTile_cts_odb_debug",
    src = ":XSTile_cts",
)

odb_debug(
    name = "XSTile_grt_odb_debug",
    src = ":XSTile_grt",
)

# The planned blocks' synthesis netlists with timing: the time table's
# source. A block synthesised alone at the target period has no fanout
# phantom and probes in minutes; its worst boundary crossing sorts the
# cut (50 % error bars against global route, enough to sort by).
[
    odb_debug(
        name = block + "_synth_odb_debug",
        src = ":" + block + "_synth",
    )
    for block in PLAN["macros"].keys()
]

# Each planned block's own minimum clock period, which is the per block
# series of the KPI (README.md, kpi.json). At place the block has no clock
# tree yet, so its reg2reg slack is against an ideal clock; the parent's
# number is the one that carries a clock tree. Timing, so these load in
# minutes, not seconds.
[
    odb_debug(
        name = block + "_place_odb_debug",
        src = ":" + block + "_place",
    )
    for block in PLAN["macros"].keys()
]

grt_netlist(
    name = "cmj_xiangshan_grt_netlist",
    src = ":XSTile_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# XiangShan is the core the per-unit breakdown is for: its modules are
# monomorphic, so unlike SERV's parameterized ones they should reach the
# ODB with their names intact, and its hierarchy maps onto the categories
# the literature reports.
stage_power_units(
    name = "cmj_xiangshan_grt_power_units",
    src = ":XSTile_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_xiangshan_grt_power",
    src = ":XSTile_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Did the L2's SRAMs reach the netlist as macros? The flow can detect a
# memory, write its views, list it in blackboxes.txt and synthesise it as
# flip-flops anyway, and nothing fails. The expected list is declared, so
# an empty blackboxes.txt fails here rather than passing vacuously. Every
# name is a firtool array_<depth>x<width> module in CoupledL2's own flow,
# each a single read-write port as CoupledL2 banks them: the data banks
# (8192x137, 128 bits and SECDED), the tag, meta and replacement arrays
# and the prefetchers' tables. The ram_<n>x<w> queues stay flops by the
# macro floors, on purpose.
CONVERTED_MEMORIES = [
    "array_1024x128",
    "array_1024x156",
    "array_1024x16",
    "array_1024x8",
    "array_256x13",
    "array_32x64",
    "array_64x100",
    "array_64x256",
    "array_64x64",
    "array_8192x137",
]

genrule(
    name = "cmj_xiangshan_memories_applied",
    srcs = [":CoupledL2_synth"],
    outs = ["cmj_xiangshan_memories_applied.txt"],
    cmd = "files=$$(echo $(locations :CoupledL2_synth) | tr ' ' '\\n'); " +
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
        src = ":XSTile_" + stage,
        stage = stage,
    )
    for stage in [
        "synth",
        "grt",
    ]
]

# The measured side of the literature table (§4.9), at every stage the
# flow has reached: the standard-cell area and the gate count are the
# same from placement on, the period is only worth quoting at grt.
[
    physical_probe(
        name = "cmj_xiangshan_physical_" + stage,
        src = ":XSTile_" + stage,
        stage = stage,
    )
    for stage in [
        "place",
        "grt",
    ]
]

# What is big: leaf instances and area under every kept module, the
# input to choosing which blocks to harden as macros.
census_probe(
    name = "cmj_xiangshan_census",
    src = ":XSTile_synth",
)
