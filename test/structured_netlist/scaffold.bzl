"""One XiangShan register file at real size, as a placed netlist in a parent of flops."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("//test/grt_scaling:arms.bzl", "TURNAROUND_ARGS")

RING_UM = 40.0  # core edge to the array on every side: the parent's flops live here
CORE_UM = 10.0  # die to core

def _r(x):
    return int(x * 1000 + 0.5) / 1000.0

def array_scaffold(name, spec, width_um, height_um):
    """The scaffold flow for one spec: <name>_scaffold_<stage>, to global route.

    Args:
      name: the module the spec names (RenameBufferFile, ...).
      spec: the .regfile label, mode netlist.
      width_um, height_um: the array's outline as structured_gen draws it
        (its .def DIEAREA); the die is the array plus a ring of flops. A
        wrong pair fails at floorplan (FLW-0004, the array leaves the core),
        so the numbers are checked by the flow, not trusted.
    """
    top = name + "_scaffold"
    native.genrule(
        name = top + "_rtl",
        srcs = [spec],
        outs = [top + ".sv", top + "_placement.txt"],
        cmd = "$(execpath :scaffold_gen) --spec $(location {}) --sv $(location {}.sv) --placement $(location {}_placement.txt) --corner '{} {}'".format(
            spec,
            top,
            top,
            _r(CORE_UM + RING_UM),
            _r(CORE_UM + RING_UM),
        ),
        tools = [":scaffold_gen"],
    )
    die_w = width_um + 2 * (CORE_UM + RING_UM)
    die_h = height_um + 2 * (CORE_UM + RING_UM)
    orfs_flow(
        name = top,
        arguments = TURNAROUND_ARGS | {
            "AUTO_MEMORIES": "1",
            "CORE_AREA": "{} {} {} {}".format(CORE_UM, CORE_UM, _r(die_w - CORE_UM), _r(die_h - CORE_UM)),
            "DIE_AREA": "0 0 {} {}".format(_r(die_w), _r(die_h)),
            "PLACE_DENSITY": "0.5",
            "SYNTH_HDL_FRONTEND": "slang",
        },
        last_stage = "grt",
        pdk = "//flow:asap7",
        sources = {
            "SDC_FILE": [":constraints.sdc"],
            "STRUCTURED_MEMORIES": [spec],
            "STRUCTURED_PLACEMENT": [":" + top + "_placement.txt"],
        },
        verilog_files = [":" + top + ".sv"],
    )
    build_test(
        name = top + "_cts_build_test",
        targets = [":" + top + "_cts"],
    )
