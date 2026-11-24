load("@bazel-orfs//:openroad.bzl", "odb_debug", "orfs_flat_sta", "orfs_module_context", "orfs_module_sta_base", "orfs_run", "orfs_schedule")
load("@rules_python//python:defs.bzl", "py_binary", "py_test")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//test/coremark_joule/designs/asap7/xiangshan/kit:kit.bzl", "xs_kit", "xs_kit_snapshot")
load("//test/coremark_joule/flow:power.bzl", "census_probe", "grt_netlist", "hier_probe", "physical_probe", "shard_replays", "stage_power", "stage_power_shards", "stage_power_units")
load(":plan/plan.bzl", "PLAN")
load(":shards.bzl", "XS_BLOCK_UNITS", "XS_COUNT_OUTPUTS", "XS_FROM_RESET", "XS_REPLAY_CUTS", "XS_REPLAY_VOPTS", "XS_SAIF_SCOPE", "XS_SHARDS", "XS_SHARD_SIMS", "XS_TRACE_ROOT", "xs_replay")
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

# The KPI's target_ps is XiangShan's 333 ps on 7 nm in fanouts of four, on
# the library the flow times with, ORFS's default asap7 corner FF, in each Vt
# class; the flow's primary Vt first.
py_test(
    name = "period_fo4_test",
    srcs = [
        "fo4.py",
        "period_fo4_test.py",
    ],
    args = [
        "$(rootpath :kpi.json)",
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
        ":kpi.json",
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
        "//test/verilog_slices:__pkg__",
    ],
)

# The plan names the modules the flow keeps, which the surgery folds
# constants into (surgery/).
exports_files(
    [
        "kpi_run.tcl",
        "plan/FltRegionModule_pins.tcl",
        "plan/plan.bzl",
        "plan/plan.json",
    ],
    visibility = ["//test/coremark_joule/designs/asap7/xiangshan:__subpackages__"],
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
# probe_pin_partners.tcl on XSTile_synth_odb_debug (GUI_TIMING=0). That
# dump is not checked in, and run 21's is gone: plan/ is run 21's plan as
# it was, its parent's register files re-placed by plan_floorplan.py
# --keep plan, which keeps the die, the blocks and every pins file and
# places only the parent's netlists, and moves the pins plan.json's
# pin_order names along their sides: the load write-back, MemBlock's
# intWriteback to the left end of its bottom edge, Vec's gpWbWakeUp_6-8
# under it and Flt's fpWbNext_6-8 to the right end of its top edge, the
# probe having placed each for another partner. A register file's outline in
# plan.json is the core ORFS patch 0172 sizes around generate_ram's array
# plus _REGFILE_MARGIN_UM on each side (xiangshan.bzl).
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
# partitioned as the plan is, the core with every arrays extraction in
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
        "constraints.sdc",
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
    # the platform files as the planned parent resolved them: the same
    # PDK and VT mix, and its synthesis is cached, where XSTile_kit's
    # 1_synth.odb, which the kit does not use, takes hours
    manifest_src = ":XSTile_synth",
    regfile_specs = ["%s.regfile" % m for m in xs_regfile_modules()],
    regfiles = xs_regfile_modules(),
    rtl_ports = ":xstile_rtl_ports",
    sdc = "constraints.sdc",
)

# The OpenROAD reference the kit's README shows, from the KPI's global
# route: images, densities, macros, ports, statistics and histograms into
# kit/snapshot/ (kit.bzl, xs_kit_snapshot). Not part of the kit's build:
#   bazelisk run //test/coremark_joule/designs/asap7/xiangshan:kit_snapshot
xs_kit_snapshot(
    name = "kit_snapshot",
    blocks = sorted(PLAN["macros"].keys()),
    top = "XSTile",
)

# A period counts only when global placement ran timing- and
# routability-driven, and neither pass says so in the exit status when it
# does not run: a parent placed with routability on ran no routability pass
# and exited 0. A part whose global placement log shows no timing-driven
# iteration (GPL-0100) or no routability-mode iteration (GPL-1017) fails
# here, in the wave that placed it (gpl_driven.sh).
GPL_DRIVEN_PARTS = sorted(PLAN["macros"].keys()) + ["XSTile"]

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
        cmd = "$(execpath :gpl_driven.sh) %s $< $@" % part,
        tags = ["manual"],
        tools = [":gpl_driven.sh"],
    )
    for part in GPL_DRIVEN_PARTS
]

sh_test(
    name = "gpl_driven_test",
    size = "small",
    srcs = ["gpl_driven_test.sh"],
    args = [
        "$(rootpath :gpl_driven.sh)",
        "$(rootpath gpl_driven_logs/parent.log)",
        "$(rootpath gpl_driven_logs/no_routability.log)",
        "$(rootpath gpl_driven_logs/no_timing.log)",
    ],
    data = [
        "gpl_driven.sh",
        "gpl_driven_logs/no_routability.log",
        "gpl_driven_logs/no_timing.log",
        "gpl_driven_logs/parent.log",
    ],
)

# The blocks and the parent, scheduled to the memory there is
# (docs/schedule.md): each block through grt with its abstract and its
# placement-driver gate, in waves that fit free memory, then the parent
# alone. The flat timing (XSTile_ilm_sta) is not in it: its parts are not
# in resources.json, and it is run alone after the schedule.
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
    },
    parent = {"XSTile": [
        ":XSTile_kpi",
        ":XSTile_gpl_driven",
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
        "Frontend_pinplan",
        "Frontend_pinplan2",
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
    saif_scope = XS_SAIF_SCOPE,
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_xiangshan_grt_power",
    src = ":XSTile_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = XS_SAIF_SCOPE,
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Power in shards (flow/power.bzl's stage_power_shards): XSTile and every
# unit hardened inside it (shards.bzl), each reported on its own
# global-route ODB, the SAIF read where the unit is. The SAIF is the
# replays' (cmj_xiangshan_replayed, below).
# every unit's netlist for the shards' simulation, `/` in a flattened
# name spelled as the shards spell it (scripts/slash_names.py)
[
    grt_netlist(
        name = "%s_grt_netlist_shards" % unit,
        src = ":%s_grt" % unit,
        # write_verilog names three clock-gate latches alike in one module
        # (scripts/uniquify_netlist.py), CoupledL2's of one slice's data
        # array, XSTile's of the ExuBlock's exuALU1_AluDiv: two renamed
        # each, and the shard's SAIF misses those two cells
        max_renames = {
            "CoupledL2": 2,
            "XSTile": 2,
        }.get(unit, 0),
        saif_names = True,
        visibility = ["//test/coremark_joule:__subpackages__"],
    )
    for unit in XS_SHARD_SIMS
]

# The power shards' SAIF: one RTL capture (sim:xiangshan_rv64gc_capture),
# each unit's netlist replayed alone from it and checked against it every
# clock phase, XSTile's with every unit a stub driven from its capture,
# the replays merged (flow/power.bzl's shard_replays).
shard_replays(
    name = "cmj_xiangshan_replayed",
    capture = "//test/coremark_joule/sim:xiangshan_rv64gc_capture.vcd",
    capture_scope = "TOP." + XS_TRACE_ROOT,
    cells = "//test/coremark_joule/rtl:asap7_stdcells_3vt_init",
    # for the cycle a mismatch is reported at: the SDC's period, as the
    # capture's (sim/run.bzl); the window is in the file
    clk_period = ":constraints.sdc",
    compare_from_reset = XS_FROM_RESET,
    count_outputs = XS_COUNT_OUTPUTS,
    cuts = XS_REPLAY_CUTS,
    netlist = ":XSTile_grt_netlist_shards.v",
    # each unit's power shard on its own replay too, before the merged
    # SAIF exists: cmj_xiangshan_replayed_power_<slug>
    power_srcs = ({} if XS_REPLAY_CUTS.get("") else {"": ":XSTile_grt"}) | {
        path: ":%s_grt" % unit
        for path, unit in XS_SHARDS.items()
        if not XS_REPLAY_CUTS.get(path)
    },
    rtl = "//test/coremark_joule/xiangshan:cm_soc_xiangshan_rtl.sv",
    top = "XSTile",
    two_level = True,
    units = {path: (
        unit,
        ":%s_grt_netlist_shards.v" % unit,
    ) for path, unit in XS_SHARDS.items()},
    vopts = XS_REPLAY_VOPTS,
    window_file = "//test/coremark_joule/sim:xiangshan_rv64gc_capture_window.txt",
)

# The pinned measurement behind XiangShan's point: power.json, written by
# `bazelisk run :pin_power` from cmj_xiangshan_grt_power_shards (below)
# with its per-module rows (scripts/pin_power.py), compared with a fresh
# run by `bazelisk run :power_pin_check`, checked by power_pin_test. Its
# provenance says which pass it is: XS_PIN_PASS, "first" until the
# numbers are read and corrected, and only a "final" pin goes into
# results.json.
XS_PIN_PASS = "final"

# caveats the pinned numbers carry, written into its provenance
XS_PIN_NOTES = [
    "every two-level piece counted, not stopped: its output differences from the RTL are in replays.outputs_differing",
    "dynamic power at the SDC period, 1,800 ps, which the capture was timed against; the period of the design is 2,377 ps, set by the parent (reg2reg WNS -577 ps), a finding of this build: derived has the energy per cycle and the power at 2,377 ps",
    "cycles is the whole run the capture traced, reset to halt; the power is averaged over saif_window_ps alone, the last CoreMark iteration, 120,389 cycles at the SDC period",
]

_PIN = "cmj_xiangshan_grt_power_shards"

# every hardened block's and the parent's reg2reg minimum period at
# global route; the register files have no KPI target and are pinned null
_PIN_KPIS = {"": "XSTile"} | {
    path: unit
    for path, unit in XS_SHARDS.items()
    if unit in XS_BLOCK_UNITS
}

# (unit, replay) of every two-level unit's remainder and its cuts
_PIN_REPLAYS = [(
    u,
    xs_replay(u),
) for u in XS_REPLAY_CUTS] + [
    (
        u,
        xs_replay((u + "/" if u else "") + c),
    )
    for u, cs in XS_REPLAY_CUTS.items()
    for c in cs
]

_PIN_ARGS = [
    "--vectorless $(rootpath :%s_vectorless.json)" % _PIN,
    "--vector-driven $(rootpath :%s_vector_driven.json)" % _PIN,
    "--report $(rootpath :%s_shards.json)" % _PIN,
    "--units $(rootpath :%s_units.json)" % _PIN,
    "--cycles $(rootpath //test/coremark_joule/sim:xiangshan_rv64gc_capture.cycles)",
    "--window $(rootpath //test/coremark_joule/sim:xiangshan_rv64gc_capture_window.txt)",
    "--constraints $(rootpath :constraints.sdc)",
    "--pass " + XS_PIN_PASS,
] + ["--note '%s'" % n for n in XS_PIN_NOTES] + [
    "--kpi '%s=$(rootpath :%s_kpi.txt)'" % (path, unit)
    for path, unit in _PIN_KPIS.items()
] + [
    # how each unit's activity was replayed: two-level ones with what
    # their replays did not compare and the stub inputs that differ
    "--two-level '%s='" % u
    for u in XS_REPLAY_CUTS
] + [
    "--replay-report '%s=$(rootpath :%s_report.json)'" % (u, r)
    for u, r in _PIN_REPLAYS
] + [
    "--stub-inputs '%s=$(rootpath :%s_stub_inputs.json)'" % (
        u,
        xs_replay(u),
    )
    for u in XS_REPLAY_CUTS
] + [
    "--counted '%s=%s:$(rootpath :%s_outputs.json)'" % (
        u,
        c,
        xs_replay((u + "/" if u else "") + c),
    )
    for u, cs in XS_REPLAY_CUTS.items()
    for c in cs
    if (u + "/" if u else "") + c in XS_COUNT_OUTPUTS
] + [
    "--out test/coremark_joule/designs/asap7/xiangshan/power.json",
]

_PIN_DATA = [
    ":%s_vectorless.json" % _PIN,
    ":%s_vector_driven.json" % _PIN,
    ":%s_shards.json" % _PIN,
    ":%s_units.json" % _PIN,
    ":constraints.sdc",
    "//test/coremark_joule/sim:xiangshan_rv64gc_capture.cycles",
    "//test/coremark_joule/sim:xiangshan_rv64gc_capture_window.txt",
] + [":%s_kpi.txt" % unit for unit in _PIN_KPIS.values()] + [
    ":%s_report.json" % r
    for _, r in _PIN_REPLAYS
] + [":%s_stub_inputs.json" % xs_replay(u) for u in XS_REPLAY_CUTS] + [
    ":%s_outputs.json" % xs_replay(path)
    for path in XS_COUNT_OUTPUTS
]

[
    py_binary(
        name = name,
        srcs = ["//test/coremark_joule/scripts:pin_power.py"],
        args = _PIN_ARGS + extra,
        data = _PIN_DATA,
        main = "//test/coremark_joule/scripts:pin_power.py",
        tags = ["manual"],
    )
    for name, extra in [
        ("pin_power", []),
        (
            "power_pin_check",
            ["--check"],
        ),
    ]
]

# FltRegionModule's leakage on its own replay, every cell with its pins'
# duties (flow/leakage_states.tcl after power_shard_grt.tcl), for
# scripts/leakage_states.py: report_power weighs a liberty `when` that
# names a cell's output as if the output were independent of the inputs.
orfs_run(
    name = "FltRegionModule_leakage_states",
    src = ":FltRegionModule_grt",
    outs = [
        "FltRegionModule_leakage_states.json",
        "FltRegionModule_leakage_states.tsv",
    ],
    data = [
        ":cmj_xiangshan_replayed_core_backend_inner_fpRegion",
        "//test/coremark_joule/flow:power_shard_grt.tcl",
    ],
    script = "//test/coremark_joule/flow:leakage_states.tcl",
    tags = ["manual"],
    user_arguments = {
        "LEAKAGE_SHARD_TCL": "$(location //test/coremark_joule/flow:power_shard_grt.tcl)",
        "LEAKAGE_STATES_TSV": "$(location FltRegionModule_leakage_states.tsv)",
        "SAIF_SCOPE": "TOP/cmj_xiangshan_replayed_core_backend_inner_fpRegion/dut",
        "SAIF_STIMULI": "$(location :cmj_xiangshan_replayed_core_backend_inner_fpRegion)",
        "SHARD_CHILDREN": "fpRegFile",
        "SHARD_JSON": "$(location FltRegionModule_leakage_states.json)",
        "SHARD_UNIT": "core/backend/inner_fpRegion",
        "STAGE_STEM": "5_1_grt",
    },
)

py_test(
    name = "power_pin_test",
    size = "small",
    srcs = ["//test/coremark_joule/scripts:power_pin_test.py"],
    args = [
        "$(rootpath power.json)",
        "--results $(rootpath //test/coremark_joule:results.json)",
        "--core xiangshan",
    ],
    data = [
        "power.json",
        "//test/coremark_joule:results.json",
    ],
    main = "//test/coremark_joule/scripts:power_pin_test.py",
    tags = ["study"],
)

stage_power_shards(
    name = "cmj_xiangshan_grt_power_shards",
    parent = ":XSTile_grt",
    saif = ":cmj_xiangshan_replayed",
    saif_scope = "TOP/cmj_xiangshan_replayed_parent/dut",
    shards = {path: ":%s_grt" % unit for path, unit in XS_SHARDS.items()},
    units = True,
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

# The cells under every kept module of each hardened unit's global route:
# where the power shards' replays are cut (shards.bzl, XS_SHARD_CUTS).
[
    census_probe(
        name = "%s_grt_census" % unit,
        src = ":%s_grt" % unit,
        stage = "grt",
    )
    for unit in ["XSTile"] + XS_BLOCK_UNITS
]

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
    cmd = "$(execpath //tools/boundary_constants) " +
          "$(location //test/coremark_joule/xiangshan:xiangshan_flat) --top XSTile " +
          "--plan $(location plan/plan.json) --plan-bzl $(location plan/plan.bzl) --out $@",
    tags = ["manual"],
    tools = ["//tools/boundary_constants"],
)

# Module-in-context timing on Frontend (private/module_sta.bzl): its
# synthesis as a hierarchical database, and the timing contexts of a few of
# its modules, each for an AI loop iterating on that module in a dirty lane:
#
#   bazelisk run :Frontend_tage_ctx_iterate -- Tage_new tage_new.v <its tables' netlists>
orfs_module_sta_base(
    name = "Frontend_hier",
    synth = ":Frontend_synth",
    tags = ["manual"],
)

[orfs_module_context(
    name = "Frontend_%s_ctx" % name,
    base = ":Frontend_hier",
    clocks = {"clock": "2000"},
    module = path,
    tags = ["manual"],
) for name, path in [
    ("tage", "inner_bpu/tage"),
    ("ftq", "inner_ftq"),
    ("icache", "inner_icache"),
]]

orfs_flat_sta(
    name = "Frontend_flat",
    base = ":Frontend_hier",
    clocks = {"clock": "2000"},
    synth = ":Frontend_synth",
    tags = ["manual"],
)

# The two-level replay's proof at size: VecRegionModule replayed with its
# issuePipes_1 (421K instances, 1,928 ports its RTL module lacks) cut out,
# the remainder writing the stub's VCD, the cut replayed from it; against
# the whole unit's replay (cmj_xiangshan_replayed_core_backend_inner_vecRegion).
# Only the vecRegion targets are built.
shard_replays(
    name = "cmj_xs2",
    capture = "//test/coremark_joule/sim:xiangshan_rv64gc_capture.vcd",
    capture_scope = "TOP." + XS_TRACE_ROOT,
    cells = "//test/coremark_joule/rtl:asap7_stdcells_3vt_init",
    clk_period = ":constraints.sdc",
    cuts = {"core/backend/inner_vecRegion": ["issuePipes_1"]},
    netlist = ":XSTile_grt_netlist_shards.v",
    rtl = "//test/coremark_joule/xiangshan:cm_soc_xiangshan_rtl.sv",
    top = "XSTile",
    two_level = True,
    units = {path: (
        unit,
        ":%s_grt_netlist_shards.v" % unit,
    ) for path, unit in XS_SHARDS.items()},
    vopts = XS_REPLAY_VOPTS,
    window_file = "//test/coremark_joule/sim:xiangshan_rv64gc_capture_window.txt",
)
