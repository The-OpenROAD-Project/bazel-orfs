"""The toy Rob, one flow per size."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")

def rob_toy(entries, rtl = False, repair = False, entry_rtl = False):
    """A toy Rob of `entries` entries with the Rob's ports, through grt.

    Args:
      entries: the number of entries.
      rtl: RobState as RTL through yosys and ABC, the baseline, instead
        of generated.
      repair: setup repair at CTS and global route on, for QoR.
      entry_rtl: the generated structure around one RobEntry module of
        RTL, kept through synthesis so ABC maps it once.
    """
    name = "rob_%d%s%s%s" % (
        entries,
        "_rtl" if rtl else "",
        "_abc" if entry_rtl else "",
        "_repair" if repair else "",
    )
    native.genrule(
        name = name + "_top",
        outs = [name + ".sv"],
        cmd = "$(execpath :rob_toy) $@ %s entries=%d%s" % (
            name,
            entries,
            "" if rtl else " top-only",
        ),
        tools = [":rob_toy"],
        tags = ["manual"],
    )
    verilog_files = [":" + name + ".sv"]
    sources = {"SDC_FILE": [":constraint.sdc"]}
    if not rtl:
        # placed by construction: a column per bank, lines in order
        sources["POST_TAPCELL_TCL"] = [":place.tcl"]
        sources["POST_GLOBAL_PLACE_TCL"] = [":unfix.tcl"]

        # RobState generated: synthesis maps only the top's registers
        native.genrule(
            name = name + "_netlist",
            outs = [name + "_robstate.v"],
            cmd = "$(execpath :rob_gen) $@ entries=%d%s" % (
                entries,
                " entry_rtl=1" if entry_rtl else "",
            ),
            tools = [":rob_gen"],
            tags = ["manual"],
        )
        verilog_files.append(":" + name + "_robstate.v")
    keep = {"SYNTH_KEEP_MODULES": "RobEntry"} if entry_rtl else {}
    repair_off = {} if repair else {
        "SKIP_CTS_REPAIR_TIMING": "1",
        "SKIP_INCREMENTAL_REPAIR": "1",
    }
    orfs_flow(
        name = name,
        arguments = {
            "CORE_UTILIZATION": "30",
            # the XSTile carve's development settings, as in
            # test/array_toys
            "ENABLE_DPO": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "GPL_TIMING_DRIVEN": "0",
            "PLACE_DENSITY": "0.5",
            "SKIP_FLOORPLAN_REPAIR_TIMING": "1",
            "SKIP_REPORT_METRICS": "1",
            # detailed route waits for the final check with LEC: pin
            # access was 54 s of 128 entries' global route
            "SKIP_PIN_ACCESS": "1",
            "SYNTH_HDL_FRONTEND": "slang",
            "SYNTH_MEMORY_MAX_BITS": "1048576",
        } | repair_off | keep,
        last_stage = "grt",
        sources = sources,
        tags = ["manual"],
        verilog_files = verilog_files,
    )
    for stage in ["cts", "grt"]:
        orfs_run(
            name = "%s_%s_qor" % (name, stage),
            src = ":%s_%s" % (name, stage),
            outs = ["%s_%s_qor.json" % (name, stage)],
            script = ":qor_probe.tcl",
            tags = ["manual"],
            user_arguments = {
                "OUTPUT_JSON": "$(location %s_%s_qor.json)" % (name, stage),
            },
        )
