"""The toy Rob, one flow per size."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")

def rob_toy(entries, rtl = False, repair = False, entry_rtl = False, plain = False, variant = None, variant_args = {}):
    """A toy Rob of `entries` entries with the Rob's ports, through grt.

    Args:
      entries: the number of entries.
      rtl: RobState as RTL through yosys and ABC, the baseline, instead
        of generated.
      repair: setup repair at CTS and global route on, for QoR.
      entry_rtl: the generated structure around one RobEntry module of
        RTL, kept through synthesis so ABC maps it once.
      plain: the generated netlist without its buffer trees, sizing and
        placement by construction; the flow does those.
      variant: a name for variant_args, flow arguments that override the
        ones below, appended to the flow's name.
      variant_args: the overriding flow arguments.
    """
    name = "rob_%d%s%s%s%s%s" % (
        entries,
        "_rtl" if rtl else "",
        "_abc" if entry_rtl else "",
        "_plain" if plain else "",
        "_repair" if repair else "",
        "_" + variant if variant else "",
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
    if not rtl and not plain:
        # placed by construction: a column per bank, lines in order
        sources["POST_TAPCELL_TCL"] = [":place.tcl"]
        sources["POST_GLOBAL_PLACE_TCL"] = [":unfix.tcl"]
    if not rtl:
        # RobState generated: synthesis maps only the top's registers
        native.genrule(
            name = name + "_netlist",
            outs = [name + "_robstate.v"],
            cmd = "$(execpath :rob_gen) $@ entries=%d%s%s" % (
                entries,
                " entry_rtl=1" if entry_rtl else "",
                " plain=1" if plain else "",
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
            # timing-driven global placement: at 352 entries it took the
            # period from 547 to 475 ps and repair from 550 to 140 s;
            # floorplan repair and a denser core bought nothing
            "GPL_TIMING_DRIVEN": "1",
            "PLACE_DENSITY": "0.5",
            "SKIP_FLOORPLAN_REPAIR_TIMING": "1",
            # the Rob macro's repair settings (xiangshan.bzl): repair goes
            # for the worst paths, not every violating endpoint
            "SKIP_LAST_GASP": "1",
            "SKIP_REPORT_METRICS": "1",
            "TNS_END_PERCENT": "1",
            # detailed route waits for the final check with LEC: pin
            # access was 54 s of 128 entries' global route
            "SKIP_PIN_ACCESS": "1",
            "SYNTH_HDL_FRONTEND": "slang",
            "SYNTH_MEMORY_MAX_BITS": "1048576",
        } | repair_off | keep | variant_args,
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
