"""One row of the register-file ladder: an ORFS design and its -regfile variant.

Each arm is the design's own flow through global route, built from
@orfs; the row reads the stage logs (wall time per stage) and the global
route metrics ORFS writes (minimum period, area, power, hold) of both
arms. Manual: a row builds two flows.
"""

load("@rules_python//python:defs.bzl", "py_binary")
load("//:openroad.bzl", "orfs_run")

STAGES = ["synth", "floorplan", "place", "cts", "grt"]

def ladder_row(name, design, top, regfile_design = None):
    """A row comparing @orfs asap7/<design> with asap7/<design>-regfile.

    Args:
      name: the row, e.g. "riscv32i".
      design: the ORFS design directory under flow/designs/asap7.
      top: DESIGN_NAME, the stem of the flow's targets.
      regfile_design: the variant's directory; <design>-regfile by default.
    """
    arms = {
        "flops": design,
        "regfile": regfile_design or design + "-regfile",
    }
    for arm, d in arms.items():
        # Stage logs (wall time) and metrics JSONs (QoR), two output groups.
        for group in ["logs", "jsons"]:
            native.filegroup(
                name = "%s_%s_%s" % (name, arm, group),
                srcs = [
                    "@orfs//flow/designs/asap7/%s:%s_%s" % (d, top, stage)
                    for stage in STAGES
                ],
                output_group = group,
                tags = ["manual"],
            )
        native.filegroup(
            name = "%s_%s_logs_and_jsons" % (name, arm),
            srcs = [
                ":%s_%s_logs" % (name, arm),
                ":%s_%s_jsons" % (name, arm),
            ],
            tags = ["manual"],
        )

    # The worst register-to-register paths of each arm at global route,
    # for the debug loop.
    for arm, d in arms.items():
        orfs_run(
            name = "%s_%s_paths" % (name, arm),
            src = "@orfs//flow/designs/asap7/%s:%s_grt" % (d, top),
            outs = ["%s_%s_paths.txt" % (name, arm)],
            script = ":paths.tcl",
            tags = ["manual"],
            user_arguments = {
                "OUTPUT_TXT": "$(location %s_%s_paths.txt)" % (name, arm),
            },
            user_sources = {
                "STAGE_SRC_TCL": ["//test/pre_route_pessimism:stage_src.tcl"],
            },
        )
    native.genrule(
        name = name + "_row",
        srcs = [":%s_%s_logs_and_jsons" % (name, arm) for arm in arms],
        outs = [name + "_row.json"],
        cmd = " ".join([
            "$(execpath :row)",
            "--name",
            name,
            "--flops",
            "$(locations :%s_flops_logs_and_jsons)" % name,
            "--regfile",
            "$(locations :%s_regfile_logs_and_jsons)" % name,
            "--out",
            "$@",
        ]),
        tools = [":row"],
        tags = ["manual"],
    )

def ladder_tools():
    py_binary(
        name = "row",
        srcs = ["row.py"],
        main = "row.py",
    )
