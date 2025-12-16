"""Sweep OpenROAD stages"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "set")
load(":write_binary.bzl", "write_binary")

all_stages = [
    "floorplan",
    "place",
    "cts",
    "grt",
    "route",
    "final",
]

def orfs_sweep(
        name,
        arguments,
        sweep,
        verilog_files,
        top = None,
        stage_sources = {},
        sources = {},
        other_variants = {},
        stage = "floorplan",
        abstract_stage = "final",
        macros = [],
        pdk = None,
        visibility = ["//visibility:private"],
        tags = []):
    """Run a sweep of OpenROAD stages

    Args:
        name: Basename of bazel targets
        top: Top module, default "name"
        arguments: dictionary of the base variables for the flow
        sweep: The dictionary describing the variables to sweep
        other_variants: Dictionary with other variants to generate, but not as part of the sweep
        stage: The stage to do the sweep on
        macros: name of modules to use as macros
        verilog_files: The Verilog files to build
        stage_sources: dictionary with list of sources to use for the stage
        abstract_stage: generate abstract from this stage
        visibility: list of visibility labels
        sources: forwarded to orfs_flow
        pdk: forwarded to orfs_flow
        tags: forwarded
    """
    if top == None:
        top = name
    sweep_json = {
        "base": arguments,
        "name": name,
        "stage": stage,
        "stages": all_stages[0:all_stages.index(stage) + 1],
        "sweep": sweep,
    }
    write_binary(
        name = name + "_sweep.json",
        data = str(sweep_json),
        tags = tags,
    )

    all_variants = sweep | other_variants

    for variant in all_variants:
        for key in all_variants[variant].keys():
            if key not in [
                "arguments",
                "dissolve",
                "macros",
                "previous_stage",
                "renamed_inputs",
                "stage_arguments",
                "stage_sources",
                "description",
                "sources",
            ]:
                fail('Unknown orfs_sweep() key "' + key + '" in ' + variant)

        orfs_flow(
            name = name,
            top = top,
            pdk = pdk,
            arguments = arguments | all_variants[variant].get("arguments", {}),
            macros = [
                         m
                         for m in macros
                         if m not in all_variants[variant].get("dissolve", [])
                     ] +
                     all_variants[variant].get("macros", []),
            previous_stage = all_variants[variant].get("previous_stage", {}),
            renamed_inputs = all_variants[variant].get("renamed_inputs", {}),
            stage_arguments = all_variants[variant].get("stage_arguments", {}),
            stage_sources = {
                stage: set(
                    stage_sources.get(stage, []) +
                    all_variants[variant].get("stage_sources", {}).get(stage, []),
                )
                for stage in set(
                    stage_sources.keys() +
                    all_variants[variant].get("stage_sources", {}).keys(),
                )
            },
            variant = variant,
            verilog_files = verilog_files,
            sources = sources | all_variants[variant].get("sources", {}),
            abstract_stage = abstract_stage,
            visibility = visibility,
            tags = tags,
        )

        native.filegroup(
            name = name + "_" + variant + "_odb",
            srcs = [
                ":" +
                name +
                "_" +
                ("" if variant == "base" else variant + "_") +
                sweep_json["stage"],
            ],
            output_group = (
                               "5_1_grt" if sweep_json["stage"] == "grt" else str(sweep_json["stages"].index(sweep_json["stage"]) + 2) +
                                                                              "_" +
                                                                              sweep_json["stage"]
                           ) +
                           ".odb",
            visibility = [":__subpackages__"],
            tags = tags,
        )

        native.filegroup(
            name = name + "_" + variant + "_logs",
            srcs = [
                ":" + name + "_" + ("" if variant == "base" else variant + "_") + stage
                for stage in sweep_json["stages"]
            ],
            output_group = "logs",
            visibility = visibility,
            tags = tags,
        )

    # This can be built in parallel, but grt needs to be build in serial, or
    # we will run out of memory
    native.filegroup(
        name = name + "_sweep_parallel",
        srcs = [
            name + "_" + ("" if variant == "base" else variant + "_") + "cts"
            for variant in sweep
        ],
        visibility = visibility,
        tags = tags,
    )
