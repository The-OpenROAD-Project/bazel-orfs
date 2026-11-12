load("@bazel-orfs//:openroad.bzl", "odb_debug", "orfs_schedule")
load("@rules_python//python:defs.bzl", "py_binary", "py_test")
load("//test/coremark_joule/designs/asap7/xiangshan/kit:kit.bzl", "xs_kit")
load("//test/coremark_joule/flow:power.bzl", "census_probe", "grt_netlist", "hier_probe", "physical_probe", "stage_power", "stage_power_units")
load(":plan/plan.bzl", "PLAN")
load(":xiangshan.bzl", "xiangshan_flat_flow", "xiangshan_flow", "xs_regfile_modules")

exports_files(["constraints.sdc"])

# kpi.py: the KPI chart, its memory, and the README's tables, written into
# the source tree (see its docstring)
py_binary(
    name = "kpi",
    srcs = ["kpi.py"],
    main = "kpi.py",
    tags = ["manual"],
    deps = ["@bazel-orfs-dev-pip//matplotlib"],
)

py_test(
    name = "kpi_test",
    srcs = [
        "kpi.py",
        "kpi_test.py",
    ],
    imports = ["."],
    main = "kpi_test.py",
    deps = ["@bazel-orfs-dev-pip//matplotlib"],
)

# The SDC period is XiangShan's 333 ps on 7 nm in fanouts of four, on the
# library the flow times with, ORFS's default asap7 corner FF, in each Vt
# class; the flow's primary Vt first.
py_test(
    name = "period_fo4_test",
    srcs = [
        "fo4.py",
        "period_fo4_test.py",
    ],
    args = [
        "$(rootpath :constraints.sdc)",
        "R",
        "$(rootpath @orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_RVT_FF_nldm_220122.lib.gz)",
        "INVx1_ASAP7_75t_R",
        "L",
        "$(rootpath @orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_LVT_FF_nldm_220122.lib.gz)",
        "INVx1_ASAP7_75t_L",
        "SL",
        "$(rootpath @orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_SLVT_FF_nldm_220122.lib.gz)",
        "INVx1_ASAP7_75t_SL",
    ],
    data = [
        ":constraints.sdc",
        "@orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_LVT_FF_nldm_220122.lib.gz",
        "@orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_RVT_FF_nldm_220122.lib.gz",
        "@orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_SLVT_FF_nldm_220122.lib.gz",
    ],
    main = "period_fo4_test.py",
    tags = ["manual"],
)

# XiangShan's ClockGate onto ASAP7's ICG (xs_icg.ys says why and how);
# test/xs_clockgate checks the mapping on a small design.
exports_files([
    "xs_icg.ys",
    "xs_icg_map.v",
])

# The entry cells' fold, for the arrays' own flows too.
exports_files(
    ["fold_entries.tcl"],
    visibility = [
        "//test/coremark_joule/designs/asap7/xiangshan/arrays:__pkg__",
        "//test/coremark_joule/designs/asap7/xiangshan/rob_array:__pkg__",
    ],
)

# The plan names the modules the flow keeps, which the surgery folds
# constants into (surgery/).
exports_files(
    [
        "plan/plan.bzl",
        "plan/plan.json",
    ],
    visibility = ["//test/coremark_joule/designs/asap7/xiangshan/surgery:__pkg__"],
)

# The parent's legalization hook, on the miniature planned parent too:
# stranded_cells_test checks it there in minutes.
exports_files(
    ["legalize_out_of_blocks.tcl"],
    visibility = ["//test/planned_parent:__pkg__"],
)

# The register-file specs: the parent's three placed netlists, at real
# size in a parent of flops, are the battery's rung for what the resizer,
# CTS and the router do to an array of this size (test/structured_netlist,
# scaffold.bzl).
exports_files(
    glob(["*.regfile"]),
    visibility = [
        "//test/coremark_joule/designs/asap7/xiangshan/flow_only:__pkg__",
        "//test/coremark_joule/designs/asap7/xiangshan/rob_array:__pkg__",
        "//test/structured_netlist:__pkg__",
    ],
)

# The Bpu's macro placement in its flow, for the flow-only measurement.
exports_files(
    ["anneal_in_flow.tcl"],
    visibility = ["//test/coremark_joule/designs/asap7/xiangshan/flow_only:__pkg__"],
)

# The planned parent: the blocks the macro selection tables named, each a
# real flow at the outline plan_floorplan.py drew with its pins on one
# side, the parent at the planned die. plan/ is generated (see
# .claude/skills/macro-selection/SKILL.md, step 3); regenerate it, never edit it:
# plan/plan.json is its input, with pin_partners.txt beside it from
# XSTile_parent_pin_partners, the parent macro's synthesis: no block is
# built for it.
xiangshan_flow(
    name = "XSTile",
    plan = PLAN,
)

# The same tile with a macro pin plan (//tools/pin_plan), built forward from
# the flow above in one graph: each part's <part>_pin_plan reads its grt and
# plans its register files' pins on the sides that face their logic and its
# macros' places, and this variant's flows build with them.
xiangshan_flow(
    name = "XSTile",
    plan = PLAN,
    variant = "pinplan",
)

# The same, its plans made from each part's placement instead of its
# global route: if <part>_pin_plan_diff finds the two plans the same, a
# first pass need only reach place.
xiangshan_flow(
    name = "XSTile",
    plan = PLAN,
    variant = "pinplan_place",
)

# A second round: each part planned again from the pinplan variant's
# global route (<part>_pin_plan2), whether the plan converges.
xiangshan_flow(
    name = "XSTile",
    plan = PLAN,
    variant = "pinplan2",
)

# The tile as one flow, no hardened blocks: ORFS's hierarchical synthesis
# of the whole tile, then macro and global placement over all of it,
# through global route, with the hierarchy kept in the ODB. The planned
# flow's register-file macros, reused. The GUI:
#
#   bazelisk run :XSTile_flat_grt gui_grt
xiangshan_flat_flow(
    name = "XSTile",
    variant = "flat",
)

# The implementation kit's netlist: the whole tile in one synthesis,
# partitioned as the carve is, the core with every arrays extraction in
# place, the register files and the memories as macros (kit/EXPORT.md).
xiangshan_flat_flow(
    name = "XSTile",
    plan = PLAN,
    variant = "kit",
)

# The implementation kit for a place-and-route tool, its
# README.pdf written from the files it is made of (kit/):
#   bazelisk run //test/coremark_joule/designs/asap7/xiangshan:export -- <dir>
filegroup(
    name = "kit_doc_inputs",
    srcs = [
        "kpi.json",
        "plan/plan.bzl",
        "plan/plan.json",
        "resources.json",
        "//test/coremark_joule/designs/asap7/xiangshan/arrays:ab.json",
    ] + glob(["*.regfile"]),
    visibility = ["//test/coremark_joule/designs/asap7/xiangshan/kit:__pkg__"],
)

# XSTile's ports as the flow reads the RTL, after the surgery: what a
# tool's floorplan has to place. A test-mode pin (scan, BIST, a DFT
# control) stops the build here: the kit's top level is functional pins
# only, and one that appears is tied off by surgery before a kit ships.
# MBIST is off in the generator (CoreMarkJouleConfig) and XSTile has no
# scan or DFT port of its own.
XS_TEST_PORTS = "(^|_)(dft|scan|scanmode|mbist|bist|testmode|test_mode|sram_?ctl|cgen)(_|$$)"

genrule(
    name = "xstile_rtl_ports",
    srcs = ["//test/coremark_joule/designs/asap7/xiangshan/surgery:xiangshan_surgered.sv"],
    outs = ["xstile_rtl_ports.json"],
    cmd = "$(execpath //test/coremark_joule/designs/asap7/xiangshan/kit:ports) --module XSTile --refuse '%s' --out $@ $<" % XS_TEST_PORTS,
    tags = ["manual"],
    tools = ["//test/coremark_joule/designs/asap7/xiangshan/kit:ports"],
)

xs_kit(
    name = "kit",
    doc_inputs = {
        "ab": "//test/coremark_joule/designs/asap7/xiangshan/arrays:ab.json",
        "kpi": "kpi.json",
        "plan": "plan/plan.json",
        "plan-bzl": "plan/plan.bzl",
        "resources": "resources.json",
    },
    flow = "XSTile_kit",
    regfile_specs = ["%s.regfile" % m for m in xs_regfile_modules()],
    regfiles = xs_regfile_modules(),
    rtl_ports = ":xstile_rtl_ports",
    sdc = "constraints.sdc",
)

# A period counts only when global placement ran timing- and
# routability-driven, and neither pass says so in the exit status when it
# does not run: a parent placed with routability on ran no routability pass
# and exited 0. Each pass prints a line when it runs, GPL-0100 and GPL-0040,
# so a part whose global placement log lacks either fails here, in the wave
# that placed it.
GPL_DRIVEN_PARTS = sorted(PLAN["macros"].keys()) + ["XSTile_parent"]

[
    filegroup(
        name = "%s_3_3_place_gp.log" % part,
        srcs = [":%s_place" % part],
        output_group = "3_3_place_gp.log",
        tags = ["manual"],
    )
    for part in GPL_DRIVEN_PARTS
]

[
    genrule(
        name = "%s_gpl_driven" % part,
        srcs = [":%s_3_3_place_gp.log" % part],
        outs = ["%s_gpl_driven.txt" % part],
        cmd = "timing=$$(grep -c GPL-0100 $< || true); " +
              "routability=$$(grep -c GPL-0040 $< || true); " +
              "echo \"{part}: $$timing timing-driven iterations, $$routability routability passes\" | tee $@; ".format(part = part) +
              "[ $$timing -gt 0 ] && [ $$routability -gt 0 ] || " +
              "{{ echo \"{part}: global placement ran without one of its drivers\" >&2; exit 1; }}".format(part = part),
        tags = ["manual"],
    )
    for part in GPL_DRIVEN_PARTS
]

# The carve, scheduled to the memory there is (docs/schedule.md): the
# blocks and the parent macro, each through grt with the abstract the top
# level reads, then the top level through CTS, alone:
#   bazelisk run //test/coremark_joule/designs/asap7/xiangshan:build
orfs_schedule(
    name = "build",
    macros = {
        block: [
            ":%s_kpi" % block,
            ":%s_generate_abstract" % block,
            ":%s_gpl_driven" % block,
        ]
        for block in sorted(PLAN["macros"].keys())
    } | {
        # its abstract in the same wave: built only when the top level
        # asked for it, it waited behind every block
        "XSTile_parent": [
            ":XSTile_parent_grt",
            ":XSTile_parent_abstract",
            ":XSTile_parent_kpi",
            ":XSTile_parent_gpl_driven",
        ],
    },
    # the top level alone: its clock tree and route, then the paths
    # between macros (the KPI's Top), and its second pass against its
    # first (both passes' reports)
    parent = {"XSTile_parent_pm": [
        ":XSTile_parent_pm_top",
        ":XSTile_parent_pm_crossings",
        ":XSTile_parent_pm_crossing_verdict",
    ]},
    tags = ["manual"],
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

# Each block at global route, where its KPI is read, the pin plan
# variants of the blocks it plans (those with a register file), and the
# planned parent, to draw the worst paths base against planned.
[
    odb_debug(
        name = flow + "_grt_odb_debug",
        src = ":" + flow + "_grt",
    )
    for flow in list(PLAN["macros"].keys()) + [
        "FltRegionModule_pinplan",
        "FltRegionModule_pinplan2",
        "Rob_pinplan",
        "Rob_pinplan2",
        "VecRegionModule_pinplan",
        "XSTile_pinplan",
    ]
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

# Every flow's synthesis maps with ABC's speed script: each planned
# block's and the parent's synthesis configuration, which merges the
# synthesis before it, so this reads a built flow.
[
    filegroup(
        name = "%s_1_synth.mk" % design,
        srcs = [":%s_synth" % design],
        output_group = "1_synth.mk",
        tags = ["manual"],
    )
    for design in [
        "XSTile",
        "XSTile_flat",
    ] + PLAN["macros"].keys()
]

py_test(
    name = "synth_config_test",
    srcs = ["synth_config_test.py"],
    args = [
        arg
        for design in [
            "XSTile",
            "XSTile_flat",
        ] + PLAN["macros"].keys()
        for arg in [
            design,
            "$(rootpath :%s_1_synth.mk)" % design,
        ]
    ],
    data = [":%s_1_synth.mk" % design for design in [
        "XSTile",
        "XSTile_flat",
    ] + PLAN["macros"].keys()],
    main = "synth_config_test.py",
    tags = ["manual"],
)

# Constants on the ports of the modules this plan keeps (blocks, kept
# modules, generated register files): what firtool left and yosys cannot
# fold across a kept boundary (boundary_constants.py).
genrule(
    name = "XSTile_boundary_constants",
    srcs = [
        "//test/coremark_joule/xiangshan:xiangshan_flat",
        "plan/plan.json",
        "plan/plan.bzl",
    ],
    outs = ["XSTile_boundary_constants.json"],
    cmd = "$(execpath //test/coremark_joule/scripts:boundary_constants) " +
          "$(location //test/coremark_joule/xiangshan:xiangshan_flat) --top XSTile " +
          "--plan $(location plan/plan.json) --plan-bzl $(location plan/plan.bzl) --out $@",
    tags = ["manual"],
    tools = ["//test/coremark_joule/scripts:boundary_constants"],
)

# each block netlist's modules renamed <block>__<module> for the flat KPI
# (xiangshan.bzl, <parent>_kpi_flat)
py_binary(
    name = "sta_prefix",
    srcs = ["sta_prefix.py"],
    main = "sta_prefix.py",
)

py_test(
    name = "sta_prefix_test",
    srcs = [
        "sta_prefix.py",
        "sta_prefix_test.py",
    ],
    imports = ["."],
    main = "sta_prefix_test.py",
    tags = ["study"],
)
