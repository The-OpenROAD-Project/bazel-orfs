"""Sweep OpenROAD stages"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

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
        sources = {},
        other_variants = {},
        stage = "floorplan",
        abstract_stage = "final",
        macros = [],
        pdk = None,
        visibility = ["//visibility:private"],
        tags = [],
        **kwargs):
    """Run a sweep of OpenROAD stages

    Args:
        name: Basename of bazel targets
        top: Top module, default "name"
        arguments: dictionary of the base variables for the flow
        sweep: The dictionary describing the variables to sweep
        other_variants: Dictionary with other variants to generate, but not as part of the sweep.
            Per-variant keys: arguments, dissolve, macros, openroad, previous_stage,
            renamed_inputs, stage_arguments, description, sources, yosys,
            abstract_stage, last_stage, tags
        stage: The stage to do the sweep on
        macros: name of modules to use as macros
        verilog_files: The Verilog files to build
        abstract_stage: generate abstract from this stage
        visibility: list of visibility labels
        sources: forwarded to orfs_flow
        pdk: forwarded to orfs_flow
        tags: forwarded
        **kwargs: forwarded to orfs_flow (e.g. openroad)
    """
    if top == None:
        top = name
    stages = all_stages[0:all_stages.index(stage) + 1]

    all_variants = sweep | other_variants

    for variant in all_variants:
        for key in all_variants[variant].keys():
            if key not in [
                "arguments",
                "dissolve",
                "macros",
                "openroad",
                "previous_stage",
                "renamed_inputs",
                "stage_arguments",
                "description",
                "sources",
                "yosys",
                "abstract_stage",
                "last_stage",
                "lint",
                "tags",
            ]:
                fail('Unknown orfs_sweep() key "' + key + '" in ' + variant)

        # Per-variant tool overrides and flags: merge into kwargs for this variant
        variant_kwargs = dict(kwargs)
        for tool in ["openroad", "yosys"]:
            variant_tool = all_variants[variant].get(tool, None)
            if variant_tool:
                variant_kwargs[tool] = variant_tool
        lint_val = all_variants[variant].get("lint", None)
        if lint_val != None:
            variant_kwargs["lint"] = lint_val

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
            variant = variant,
            verilog_files = verilog_files,
            sources = sources | all_variants[variant].get("sources", {}),
            abstract_stage = None if "last_stage" in all_variants[variant] else all_variants[variant].get("abstract_stage", abstract_stage),
            last_stage = all_variants[variant].get("last_stage", None),
            visibility = visibility,
            tags = tags + all_variants[variant].get("tags", []),
            **variant_kwargs
        )

        native.filegroup(
            name = name + "_" + variant + "_odb",
            srcs = [
                ":" +
                name +
                "_" +
                ("" if variant == "base" else variant + "_") +
                stage,
            ],
            output_group = (
                               "5_1_grt" if stage == "grt" else str(stages.index(stage) + 2) +
                                                                "_" +
                                                                stage
                           ) +
                           ".odb",
            visibility = [":__subpackages__"],
            tags = tags,
        )

        native.filegroup(
            name = name + "_" + variant + "_logs",
            srcs = [
                ":" + name + "_" + ("" if variant == "base" else variant + "_") + s
                for s in stages
            ],
            output_group = "logs",
            visibility = visibility,
            tags = tags,
        )
