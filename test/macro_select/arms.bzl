"""The pin-wall calibration: one block, N one-side pins, a channel, the parent's flops across it.

The planner (tools/macro_select/plan_floorplan.py) uses four constants it
cannot derive: the pin pitch a side can carry, the margin on it, the channel
in front of a pin side, and the picoseconds a micron of parent wire costs.
Each arm here is one point in that space, routes in tens of seconds, and
reports what the router, the legaliser and the timer say about it.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("//test/grt_scaling:arms.bzl", "TURNAROUND_ARGS")

# asap7, the layers a block's pins use in the XiangShan study, the same
# routing range; pins on the block's top side, on the vertical layers.
PINWALL_BASE_ARGS = TURNAROUND_ARGS | {
    "AUTO_MEMORIES": "0",
    "IO_PLACER_H": "M2 M4",
    "IO_PLACER_V": "M3 M5",
    "MAX_ROUTING_LAYER": "M7",
    "MIN_ROUTING_LAYER": "M2",
    "PLACE_DENSITY": "0.6",
    "PLACE_PINS_ARGS": "-annealing",
    "SYNTH_HDL_FRONTEND": "slang",
}

PIN_PITCH_UM = 0.096  # two tracks of M5; the planner's default
PIN_LAYERS = 2  # M3 and M5 on the top side
BLOCK_DEPTH_UM = 40.0  # rows enough for 2N flops; the pins set the width
EDGE_UM = 20.0  # die to core, both designs

def _r(x):
    """Three decimals; Starlark has no round()."""
    return int(x * 1000 + 0.5) / 1000.0

def _area(x0, y0, x1, y1):
    return "{} {} {} {}".format(_r(x0), _r(y0), _r(x1), _r(y1))

def pinwall_arm(pins, channel_um, margin = 1.5, name = None, lateral = False):
    """The block and the parent for one point: pins, channel width, pin margin.

    Targets are pinwall_block_<arm>_<stage> and pinwall_top_<arm>_<stage>,
    results under results/asap7/pinwall_{block,top}/<arm>.
    """
    name = name or "pw_p{}_c{}_m{}{}".format(pins, int(channel_um), str(margin).replace(".", ""), "_lat" if lateral else "")
    side = pins * PIN_PITCH_UM * margin / PIN_LAYERS
    gen = name + "_rtl"
    native.genrule(
        name = gen,
        outs = [name + "_block.sv", name + "_top.sv"],
        cmd = "$(location :pinwall_gen) --pins {} --block $(location :{}_block.sv) --top $(location :{}_top.sv)".format(pins, name, name),
        tools = [":pinwall_gen"],
    )
    orfs_flow(
        name = "pinwall_block",
        top = "pinwall_block",
        abstract_stage = "place",
        arguments = PINWALL_BASE_ARGS | {
            "CORE_AREA": _area(2, 2, side - 2, BLOCK_DEPTH_UM - 2),
            "DIE_AREA": _area(0, 0, side, BLOCK_DEPTH_UM),
        },
        pdk = "//flow:asap7",
        sources = {
            "IO_CONSTRAINTS": [":pins_top.tcl"],
            # a block's grid: rails and straps that a parent's grid connects to
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": [":constraints.sdc"],
        },
        variant = name,
        verilog_files = [":" + name + "_block.sv"],
    )

    # the parent's region: 2N flops and their xors at PLACE_DENSITY, above
    # the channel; a floor of 30 um so a small N still has rows
    region_h = max(30.0, 2 * pins * 0.35 / 0.6 / side)
    die_w = side + 2 * EDGE_UM
    die_h = EDGE_UM + BLOCK_DEPTH_UM + channel_um + region_h + EDGE_UM
    if lateral:
        # the logic beside the block: a strip to its right as tall as the
        # block and its channel, wide enough for the cells at density
        region_w = max(30.0, 2 * pins * 0.35 / 0.6 / (BLOCK_DEPTH_UM + channel_um))
        die_w = side + channel_um + region_w + 2 * EDGE_UM
        die_h = EDGE_UM + BLOCK_DEPTH_UM + channel_um + EDGE_UM
    orfs_flow(
        name = "pinwall_top",
        top = "pinwall_top",
        arguments = PINWALL_BASE_ARGS | {
            "CORE_AREA": _area(2, 2, die_w - 2, die_h - 2),
            "DIE_AREA": _area(0, 0, die_w, die_h),
            # the channel: cells keep this far from the block
            "MACRO_PLACE_HALO": "{} {}".format(channel_um, channel_um),
        },
        last_stage = "grt",
        macros = [":pinwall_block_" + name + "_generate_abstract"],
        pdk = "//flow:asap7",
        sources = {
            "MACRO_PLACEMENT_TCL": [":place_block_lateral.tcl" if lateral else ":place_block.tcl"],
            # the parent's grid over a hardened block, as the XiangShan study's
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl"],
            "SDC_FILE": [":constraints.sdc"],
        },
        variant = name,
        verilog_files = [":" + name + "_top.sv"],
    )

def channel_arm(pins, gap_um, margin = 3.0):
    """Two blocks side by side with the whole interface between them, gap_um apart.

    XiangShan's Frontend and MemBlock (inventory entry 13): both blocks'
    pins on their top sides, inputs on the left half and outputs on the
    right (pins_split.tcl), so the interface meets at the gap the way the
    planner gives partners facing edge segments; the parent's logic above.
    The pin margin is 3: a constrained half side at 1.5 has no room for the
    pin placer's intervals (PPL-0102) where the free side at 1.5 does. Over the blocks only M6 runs
    horizontally (their abstracts obstruct M1 to M5), so what the top-side
    capacity cannot carry goes through the gap; a placement gap walls, a
    routing channel does not. Targets pinwall_block_<arm>_*,
    pinwall_top_<arm>_* and route0_<arm>.json, the route-0 gate's numbers.
    """
    name = "ch_p{}_g{}".format(pins, int(gap_um))
    side = pins * PIN_PITCH_UM * margin / PIN_LAYERS
    native.genrule(
        name = name + "_rtl",
        outs = [name + "_block.sv", name + "_top.sv"],
        cmd = "$(location :pinwall_gen) --pins {} --channel --block $(location :{}_block.sv) --top $(location :{}_top.sv)".format(pins, name, name),
        tools = [":pinwall_gen"],
    )
    orfs_flow(
        name = "pinwall_block",
        top = "pinwall_block",
        abstract_stage = "place",
        arguments = PINWALL_BASE_ARGS | {
            "CORE_AREA": _area(2, 2, side - 2, BLOCK_DEPTH_UM - 2),
            "DIE_AREA": _area(0, 0, side, BLOCK_DEPTH_UM),
            # the annealer leaves a third of the constrained pins outside
            # their interval (PPL-0102, then PPL-0107); the slot assigner
            # keeps them in
            "PLACE_PINS_ARGS": "",
        },
        pdk = "//flow:asap7",
        sources = {
            "IO_CONSTRAINTS": [":pins_split.tcl"],
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": [":constraints.sdc"],
        },
        variant = name,
        verilog_files = [":" + name + "_block.sv"],
    )
    channel_um = 10.0  # between the blocks' pin sides and the logic above
    width = 2 * side + gap_um
    region_h = max(30.0, pins * 0.35 / 0.6 / width)
    die_w = width + 2 * EDGE_UM
    die_h = EDGE_UM + BLOCK_DEPTH_UM + channel_um + region_h + EDGE_UM
    top_args = PINWALL_BASE_ARGS | {
        "CORE_AREA": _area(2, 2, die_w - 2, die_h - 2),
        "DIE_AREA": _area(0, 0, die_w, die_h),
        # the gap stays free of cells, like the plan's; the logic keeps
        # channel_um from the pin sides
        "MACRO_PLACE_HALO": "{} {}".format(_r(gap_um / 2), channel_um),
    }
    top_sources = {
        "MACRO_PLACEMENT_TCL": [":place_two_blocks.tcl"],
        "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl"],
        "SDC_FILE": [":constraints.sdc"],
    }
    orfs_flow(
        name = "pinwall_top",
        top = "pinwall_top",
        arguments = top_args,
        last_stage = "cts",
        macros = [":pinwall_block_" + name + "_generate_abstract"],
        pdk = "//flow:asap7",
        sources = top_sources,
        user_arguments = {"BLOCK_GAP_UM": str(gap_um)},
        variant = name,
        verilog_files = [":" + name + "_top.sv"],
    )
    orfs_run(
        name = "route0_" + name,
        src = ":pinwall_top_" + name + "_cts",
        outs = ["route0_" + name + ".json"],
        arguments = top_args,
        script = ":route0.tcl",
        sources = top_sources,
        user_arguments = {
            "OUTPUT_JSON": "$(location route0_" + name + ".json)",
        },
        variant = name,
    )
