"""The toy Rob, one flow per size."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

def rob_toy(entries):
    """A toy Rob of `entries` entries with the Rob's ports, generated, through grt.

    Args:
      entries: the number of entries.
    """
    name = "rob_%d" % entries
    native.genrule(
        name = name + "_rtl",
        outs = [name + ".sv"],
        cmd = "$(execpath :rob_toy) $@ %s entries=%d top-only" % (name, entries),
        tools = [":rob_toy"],
        tags = ["manual"],
    )

    # RobState generated: synthesis maps only the top's registers
    native.genrule(
        name = name + "_netlist",
        outs = [name + "_robstate.v"],
        cmd = "$(execpath :rob_gen) $@ entries=%d" % entries,
        tools = [":rob_gen"],
        tags = ["manual"],
    )
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
            # build time first, QoR after: the entry logic is ~550 ps
            # deep against 473 ps, and at 64 entries setup repair ground
            # 74 s of CTS over 3,874 violating endpoints
            "SKIP_CTS_REPAIR_TIMING": "1",
            "SKIP_INCREMENTAL_REPAIR": "1",
            "SKIP_REPORT_METRICS": "1",
            # detailed route waits for the final check with LEC: pin
            # access was 54 s of 128 entries' global route
            "SKIP_PIN_ACCESS": "1",
            "SYNTH_HDL_FRONTEND": "slang",
            "SYNTH_MEMORY_MAX_BITS": "1048576",
        },
        last_stage = "grt",
        sources = {"SDC_FILE": [":constraint.sdc"]},
        tags = ["manual"],
        verilog_files = [":" + name + ".sv", ":" + name + "_robstate.v"],
    )
