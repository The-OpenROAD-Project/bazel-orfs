"""MainBtb as its own flow, the analogue of Frontend's worst path."""

load("//:openroad.bzl", "orfs_flow")

XS = "//test/coremark_joule/designs/asap7/xiangshan"

# The Frontend block's own synthesis settings, so R0 reproduces its
# netlist before anything is varied.
XS_BLOCK_ARGUMENTS = {
    "ABC_AREA": "1",
    "AUTO_MEMORIES": "1",
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_EXTRACT_FA": "1",
    "SKIP_REPORT_METRICS": "1",
}

MAINBTB_PLACE = {
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_TIMING_DRIVEN": "0",
    "MACRO_PLACE_HALO": "2 2",
    "PLACE_DENSITY": "0.65",
}

def mainbtb_flow(arguments, variant = None, previous_stage = {}, sources = {}):
    """MainBtb through the flow with XiangShan's ICG mapping and 473 ps SDC.

    Args:
      arguments: floorplan and placement arguments over the block's own.
      variant: the orfs_flow variant, None for the base flow.
      previous_stage: shared stages, as orfs_flow takes them.
      sources: more sources, as orfs_flow takes them.
    """
    orfs_flow(
        name = "MainBtb",
        arguments = XS_BLOCK_ARGUMENTS | MAINBTB_PLACE | arguments,
        previous_stage = previous_stage,
        sources = {"SDC_FILE": [XS + ":constraints_473ps.sdc"]} | sources,
        tags = ["manual"],
        user_arguments = {
            "SYNTH_POST_HIERARCHY_SCRIPTS": "test/coremark_joule/designs/asap7/xiangshan/xs_icg.ys",
        },
        user_sources = {
            "XS_ICG_MAP": [
                XS + ":xs_icg.ys",
                XS + ":xs_icg_map.v",
            ],
        },
        user_stages = {
            "SYNTH_POST_HIERARCHY_SCRIPTS": ["synth"],
            "XS_ICG_MAP": ["synth"],
        },
        variant = variant,
        verilog_files = [":mainbtb_sv"],
    )
