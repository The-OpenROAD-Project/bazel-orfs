"""One anchored-wirebound arm of the global-route scaling study."""

load("//:openroad.bzl", "orfs_flow")

# Everything before global route exists only to produce the CTS ODB the
# router is measured on, so it runs with the turnaround settings the
# XiangShan study's blocks use: no timing-driven or routability-driven
# placement, no repair passes, area-mode ABC, no report_metrics. The
# router then sees a placement with more overflow than a default flow
# would give it, which is the case worth measuring.
TURNAROUND_ARGS = {
    "ABC_AREA": "1",
    "ENABLE_DPO": "0",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_TIMING_DRIVEN": "0",
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_INCREMENTAL_REPAIR": "1",
    "SKIP_LAST_GASP": "1",
    "SKIP_REPORT_METRICS": "1",
    "TNS_END_PERCENT": "1",
}

def die_args(side_um, margin_um = 2):
    """DIE_AREA and CORE_AREA for a square die of `side_um` microns."""
    return {
        "DIE_AREA": "0 0 {} {}".format(side_um, side_um),
        "CORE_AREA": "{} {} {} {}".format(margin_um, margin_um, side_um - margin_um, side_um - margin_um),
    }

def grid_arm(side_um, groups, base_args, user_args, verilog_files, sdc, io_constraints, name = "wirebound_grid", **kwargs):
    """wirebound with IO anchors on a `side_um` square die, `groups` groups.

    Args:
        side_um: die side in microns; the GCell grid is side / 0.54 on asap7.
        groups: WIREBOUND_GROUPS, the net-count axis.
        base_args: the design's arguments with the floorplan removed.
        user_args: the design's project-private variables.
        verilog_files: wirebound.sv.
        sdc: the design's SDC label.
        io_constraints: io.tcl, pinning each group to a die edge.
        name: the shared flow name; the arm is the variant `d<side>_g<groups>`,
            so its stages are `<name>_d<side>_g<groups>_<stage>`, each with a
            `_deps` companion, which is where grt_bench.tcl runs.
        **kwargs: forwarded to orfs_flow (tags, visibility).
    """
    variant = "d{}_g{}".format(side_um, groups)
    # Every arm shares DESIGN_NICKNAME=wirebound; the variant keeps their
    # results, logs and _deps trees apart (results/asap7/wirebound/<variant>).
    orfs_flow(
        name = name,
        variant = variant,
        arguments = TURNAROUND_ARGS | base_args | die_args(side_um) | {
            "VERILOG_DEFINES": "-D WIREBOUND_GROUPS={} -D WIREBOUND_IO_ANCHORS".format(groups),
        },
        last_stage = "grt",
        sources = {
            "IO_CONSTRAINTS": [io_constraints],
            "SDC_FILE": [sdc],
        },
        top = "wirebound",
        user_arguments = user_args,
        verilog_files = verilog_files,
        **kwargs
    )
