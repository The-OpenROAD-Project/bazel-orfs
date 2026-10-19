"""One XiangShan register file at real size, as a placed netlist in a parent of flops."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("//test/grt_scaling:arms.bzl", "TURNAROUND_ARGS")

RING_UM = 40.0  # core edge to the array on every side: the parent's flops live here
CORE_UM = 10.0  # die to core

def _r(x):
    return int(x * 1000 + 0.5) / 1000.0

def array_scaffold(name, spec, width_um, height_um, periphery_um2):
    """The scaffold flow for one spec: <name>_scaffold_<stage>, to CTS: a smoke test that
    the array dissolves and CTS seats its buffers; nothing reads a route.

    Args:
      name: the module the spec names (RenameBufferFile, ...).
      spec: the .regfile label, mode netlist.
      width_um, height_um: the array's outline as generate_ram draws it
        in the netlist shape (regfile_ram.py's <module>_ram.outline); the
        die is the array plus a ring of flops. A
        wrong pair fails at floorplan (FLW-0004, the array leaves the core),
        so the numbers are checked by the flow, not trusted.
      periphery_um2: the cell area generate_ram leaves outside the
        outline (decoders, select and input buffers) for the parent to
        place. The ring is widened to hold it at the flow's 0.5 placement
        density, beside the parent's flops.
    """

    # the periphery at density 0.5 spread along the ring's length
    ring = RING_UM + 2 * periphery_um2 / (2 * (width_um + height_um + 4 * RING_UM))
    top = name + "_scaffold"
    native.genrule(
        name = top + "_rtl",
        srcs = [spec],
        outs = [top + ".sv", top + "_macro_placement.tcl"],
        cmd = "$(execpath :scaffold_gen) --spec $(location {}) --sv $(location {}.sv) --macro-placement $(location {}_macro_placement.tcl) --corner '{} {}'".format(
            spec,
            top,
            top,
            _r(CORE_UM + ring),
            _r(CORE_UM + ring),
        ),
        tools = [":scaffold_gen"],
    )
    die_w = width_um + 2 * (CORE_UM + ring)
    die_h = height_um + 2 * (CORE_UM + ring)
    orfs_flow(
        name = top,
        arguments = TURNAROUND_ARGS | {
            "AUTO_MEMORIES": "1",
            "CORE_AREA": "{} {} {} {}".format(CORE_UM, CORE_UM, _r(die_w - CORE_UM), _r(die_h - CORE_UM)),
            "DIE_AREA": "0 0 {} {}".format(_r(die_w), _r(die_h)),
            "AUTO_MEMORIES_MACRO_PLACE": name,
            "PLACE_DENSITY": "0.5",
            "SYNTH_HDL_FRONTEND": "slang",
        },
        last_stage = "cts",
        pdk = "//flow:asap7",
        sources = {
            "SDC_FILE": [":constraints.sdc"],
            "AUTO_MEMORIES_REGFILES": [spec],
            "MACRO_PLACEMENT_TCL": [":" + top + "_macro_placement.tcl"],
        },
        verilog_files = [":" + top + ".sv"],
    )
    build_test(
        name = top + "_cts_build_test",
        tags = ["manual"],
        visibility = ["//test:__pkg__"],
        targets = [":" + top + "_cts"],
    )
