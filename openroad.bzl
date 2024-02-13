def enumerate(iterable):
    result = []
    for i in range(len(iterable)):
        result.append((i, iterable[i]))
    return result

def map(func, iterable):
    result = []
    for item in iterable:
        result.append(func(item))
    return result

def map2(func, iterable):
    result = []
    for item in iterable:
        result.append(func(item))
    return result

def set(iterable):
    result = []
    for item in iterable:
        if item not in result:
            result = result + [item.strip()]
    return result

def filter(iterable, func):
    result = []
    for item in iterable:
        if func(item):
            result = result + [item]
    return result

def wrap_args(args):
    wrapped_args = []

    for arg in args:
        splt = arg.split("=", 1)
        if (len(splt) == 2):
            if (" " in splt[1] and "DESIGN_CONFIG" != splt[0]):
                wrapped_args.append(splt[0] + "='" + splt[1] + "'")
            else:
                wrapped_args.append(arg)
        else:
            wrapped_args.append(arg)
    return wrapped_args

def build_openroad(
        name,
        # Path to Makefile which includes config.mk from this repository.
        # Use BAZEL_ORFS env var to provide correct path to config.mk
        # Workaround for the issues created by running make targets
        # in the sandbox directory when bazel-orfs rules are loaded by other repository.
        entrypoint,
        variant = "base",
        verilog_files = [],
        stage_sources = {},
        macros = [],
        macro_variants = {},
        io_constraints = None,
        stage_args = {},
        mock_abstract = False,
        mock_stage = "place",
        orfs_version = 4,
        mock_area = None,
        platform = "asap7",
        macro_variant = "base"):
    target_ext = ("_" + variant if variant != "base" else "")
    target_name = name + target_ext
    macros = set(macros + list(macro_variants.keys()))
    all_stages = [
        ("0", "clock_period"),
        ("1", "synth"),
        ("0", "synth_sdc"),
        ("2", "floorplan"),
        ("3", "place"),
        ("4", "cts"),
        ("5_1", "grt"),
        ("5", "route"),
        ("6", "final"),
        ("7", "generate_abstract"),
    ]
    all_stage_names = map(lambda s: s[1], all_stages)
    name_to_stage = dict(map(lambda s: (s[1], s[0]), all_stages))

    source_folder_name = name

    output_folder_name = source_folder_name

    all_sources = [
        Label("//:orfs"),
        Label("//:config.mk"),
        entrypoint,
    ]

    macro_targets = map(lambda m: ":" + m + "_generate_abstract", macros)
    x = map(lambda ext: map2(lambda m: "//:results/" + platform + "/%s/%s/%s.%s" % (m, macro_variants.get(m, macro_variant), m, ext), macros), ["lef", "lib"])
    macro_lef_targets, macro_lib_targets = x

    stage_sources = dict(stage_sources)

    SDC_FILE_CLOCK_PERIOD = "results/" + platform + "/%s/%s/clock_period.txt" % (output_folder_name, variant)
    stage_sources["synth"] = stage_sources.get("synth", []) + set(verilog_files)
    io_constraints_source = ([io_constraints] if io_constraints != None else [])
    stage_sources["floorplan"] = stage_sources.get("floorplan", []) + io_constraints_source
    stage_sources["place"] = stage_sources.get("place", []) + io_constraints_source

    stage_args = dict(stage_args)

    ADDITIONAL_LEFS = " ".join(map(lambda m: "$(RULEDIR)/results/" + platform + "/%s/%s/%s.lef" % (m, macro_variants.get(m, macro_variant), m), macros))
    ADDITIONAL_LIBS = " ".join(map(lambda m: "$(RULEDIR)/results/" + platform + "/%s/%s/%s.lib" % (m, macro_variants.get(m, macro_variant), m), macros))
    ADDITIONAL_GDS_FILES = " ".join(map(lambda m: "$(RULEDIR)/results/" + platform + "/%s/%s/6_final.gds" % (m, macro_variants.get(m, macro_variant)), macros))

    io_constraints_args = ["IO_CONSTRAINTS=" + io_constraints] if io_constraints != None else []

    lefs_args = (["ADDITIONAL_LEFS=" + ADDITIONAL_LEFS] if len(macros) > 0 else [])
    libs_args = (["ADDITIONAL_LIBS=" + ADDITIONAL_LIBS] if len(macros) > 0 else [])
    gds_args = (["ADDITIONAL_GDS_FILES=" + ADDITIONAL_GDS_FILES] if len(macros) > 0 else [])

    stage_args["synth"] = stage_args.get("synth", []) + libs_args + [
        "VERILOG_FILES=" + " ".join(set(verilog_files)),
        "SDC_FILE_CLOCK_PERIOD=" + SDC_FILE_CLOCK_PERIOD,
    ]
    stage_args["floorplan"] = stage_args.get("floorplan", []) + lefs_args + libs_args + (
        [] if len(macros) == 0 else [
            "CORE_MARGIN=4",
            "'PDN_TCL=\\$${PLATFORM_DIR}/openRoad/pdn/BLOCKS_grid_strategy.tcl'",
        ]
    ) + io_constraints_args + (["MACROS=" + " ".join(set(macros))] if len(macros) > 0 else [])

    stage_args["place"] = stage_args.get("place", []) + libs_args + io_constraints_args

    stage_args["final"] = stage_args.get("final", []) + gds_args + lefs_args + (
        ["GND_NETS_VOLTAGES=\"\"", "PWR_NETS_VOLTAGES=\"\""]
    ) + (
        ["GDS_ALLOW_EMPTY=(" + "|".join(macros) + ")"] if len(macros) > 0 else []
    )

    stage_args["route"] = stage_args.get("route", []) + (
        [] if len(macros) == 0 else [
            "MIN_ROUTING_LAYER=M2",
            "MAX_ROUTING_LAYER=M9",
        ]
    )

    abstract_source = str(name_to_stage[mock_stage]) + "_" + mock_stage
    stage_args["generate_abstract"] = stage_args.get("generate_abstract", []) + gds_args + lefs_args + (
        ["ABSTRACT_SOURCE=" + abstract_source] if mock_abstract else []
    )

    base_args = [
        "WORK_HOME=$(RULEDIR)",
        "ORFS_VERSION=" + str(orfs_version),
        "DESIGN_NAME=" + name,
        "FLOW_VARIANT=" + variant,
        "DESIGN_CONFIG=$(location " + entrypoint + ")",
    ]

    reports = {
        "synth": [
            "1_1_yosys",
            "1_1_yosys_hier_report",
        ],
        "floorplan": [
            "2_1_floorplan",
            "2_2_floorplan_io",
            "2_3_floorplan_tdms",
            "2_4_floorplan_macro",
            "2_5_floorplan_tapcell",
            "2_6_floorplan_pdn",
        ],
        "place": [
            "3_1_place_gp_skip_io",
            "3_2_place_iop",
            "3_3_place_gp",
            "3_4_place_resized",
            "3_5_place_dp",
        ],
        "cts": ["4_1_cts"],
        "grt": ["5_1_grt"],
        "route": [
            "5_2_fillcell",
            "5_3_route",
        ],
        "final": [
            "6_1_merge",
            "6_report",
        ],
        "generate_abstract": ["generate_abstract"],
    }

    SDC_FILE = list(filter(set([
        item
        for sublist in stage_sources.values()
        for item in sublist
    ]), lambda s: s.endswith(".sdc")))[0]
    stage_args["clock_period"] = [
        "SDC_FILE=" + SDC_FILE,
    ]
    stage_args["synth_sdc"] = stage_args["clock_period"]
    stage_sources["clock_period"] = [SDC_FILE]
    stage_sources["synth_sdc"] = [SDC_FILE]
    stage_sources["synth"] = list(filter(stage_sources["synth"], lambda s: not s.endswith(".sdc")))
    stage_sources["floorplan"] = stage_sources.get("floorplan", []) + [name + target_ext + "_synth"]

    outs = {
        "clock_period": [
            SDC_FILE_CLOCK_PERIOD,
        ],
        "synth_sdc": [
            "results/" + platform + "/%s/%s/1_synth.sdc" % (output_folder_name, variant),
        ],
        "synth": [
            "results/" + platform + "/%s/%s/1_synth.v" % (output_folder_name, variant),
        ],
        "generate_abstract": [
            "results/" + platform + "/%s/%s/%s.lib" % (output_folder_name, variant, name),
            "results/" + platform + "/%s/%s/%s.lef" % (output_folder_name, variant, name),
        ],
        "final": [
            "results/" + platform + "/%s/%s/6_final.spef" % (output_folder_name, variant),
            "results/" + platform + "/%s/%s/6_final.gds" % (output_folder_name, variant),
        ],
        "grt": ["reports/" + platform + "/%s/%s/congestion.rpt" % (output_folder_name, variant)],
        "route": ["reports/" + platform + "/%s/%s/5_route_drc.rpt" % (output_folder_name, variant)],
        "memory": ["results/" + platform + "/%s/%s/mem.json" % (output_folder_name, variant)],
    }

    stages = []
    skip = False
    for stage in all_stage_names:
        if not mock_abstract or stage == "generate_abstract":
            skip = False
        if skip:
            continue
        if mock_abstract and stage == mock_stage:
            skip = True
        stages.append(stage)

    stage_num = dict(map(lambda s: (s[1], s[0]), all_stages))

    for stage, i in map(
        lambda stage: (stage, stage_num[stage]),
        ["floorplan", "place", "cts", "grt", "route", "final"],
    ):
        outs[stage] = outs.get(stage, []) + [
            "results/" + platform + "/%s/%s/%s.sdc" % (output_folder_name, variant, str(i) + "_" + stage),
            "results/" + platform + "/%s/%s/%s.odb" % (output_folder_name, variant, str(i) + "_" + stage),
        ]

    for stage in ["place", "grt"]:
        outs[stage] = outs.get(stage, []) + [
            "results/" + platform + "/%s/%s/%s.ok" % (output_folder_name, variant, stage),
        ]

    for stage in reports:
        outs[stage] = outs.get(stage, []) + list(
            map(lambda log: "logs/" + platform + "/%s/%s/%s.log" % (output_folder_name, variant, log), reports[stage]),
        )

    stage_sources["route"] = stage_sources.get("route", []) + outs["cts"]

    for stage in name_to_stage:
        stage_sources[stage] = ([Label("//:" + stage + "-bazel.mk")] +
                                all_sources +
                                (macro_lib_targets if stage not in ("clock_period", "synth_sdc") else []) +
                                (macro_lef_targets if stage not in ("synth", "clock_period", "synth_sdc") else []) +
                                stage_sources.get(stage, []))
        stage_args[stage] = ["make"] + base_args + stage_args.get(stage, [])

    [native.genrule(
        name = target_name + "_" + stage + "_local_runner_script",
        tools = [],
        srcs = [
                   Label("//:orfs-bazel.mk"),
                   Label("//:local_runner.template.sh"),
               ] +
               stage_sources[stage] +
               [("//:" + target_name + "_" + previous_stage)] if stage not in ("clock_period", "synth_sdc", "synth") else [],
        cmd = "echo `cat $(location " + str(Label("//:local_runner.template.sh")) + ")` " + " ".join(wrap_args(stage_args.get(stage, []))) + " \\\"$$\\@\\\" > $@",
        outs = ["logs/" + platform + "/%s/%s/local_runner_script_%s.sh" % (output_folder_name, variant, stage)],
    ) for ((_, previous_stage), (i, stage)) in zip([(0, "n/a")] + enumerate(stages), enumerate(stages))]
    [
        native.sh_binary(
            name = target_name + "_" + stage + "_local_runner",
            srcs = ["//:" + target_name + "_" + stage + "_local_runner_script"],
            data = [Label("//:orfs")],
            deps = ["@bazel_tools//tools/bash/runfiles"],
        )
        for stage in stages
    ]

    if mock_area != None:
        mock_stages = ["clock_period", "synth", "synth_sdc", "floorplan", "generate_abstract"]
        [
            native.genrule(
                name = target_name + "_" + stage + "_mock_area",
                tools = [Label("//:orfs")],
                srcs = stage_sources[stage] + ([name + target_ext + "_" + stage, Label("mock_area.tcl")] if stage == "floorplan" else []) +
                       ([name + target_ext + "_" + previous + "_mock_area"] if stage != "clock_period" else []) +
                       ([name + target_ext + "_synth_mock_area"] if stage == "floorplan" else []),
                cmd = "$(location " + str(Label("//:orfs")) + ") " +
                      " ".join(wrap_args([s for s in stage_args[stage] if not any([sub in s for sub in ("DIE_AREA", "CORE_AREA", "CORE_UTILIZATION")])])) +
                      " " +
                      " ".join(wrap_args([
                          "FLOW_VARIANT=mock_area",
                          "bazel-" + stage + ("-mock_area" if stage == "floorplan" else ""),
                      ])) +
                      " " +
                      " ".join(wrap_args({
                          "floorplan": ["MOCK_AREA=" + str(mock_area), "MOCK_AREA_TCL=$(location " + str(Label("mock_area.tcl")) + ")"],
                          "synth": ["SYNTH_GUT=1"],
                          "generate_abstract": ["ABSTRACT_SOURCE=2_floorplan"],
                      }.get(stage, []))),
                outs = [s.replace("/" + variant + "/", "/mock_area/") for s in outs.get(stage, [])],
            )
            for (previous, stage) in zip(["n/a"] + mock_stages, mock_stages)
        ]

    native.genrule(
        name = target_name + "_memory",
        tools = [Label("//:orfs")],
        srcs = stage_sources["synth"] + [name + "_clock_period"],
        cmd = "$(location " + str(Label("//:orfs")) + ") " + " ".join(wrap_args(stage_args["synth"])) + " memory",
        outs = outs["memory"],
    )

    [native.genrule(
        name = target_name + "_" + stage,
        tools = [Label("//:orfs")],
        srcs = stage_sources[stage] + ([name + target_ext + "_" + previous] if stage not in ("clock_period", "synth_sdc", "synth") else []) +
               ([name + target_ext + "_generate_abstract_mock_area"] if mock_area != None and stage == "generate_abstract" else []),
        cmd = "$(location " + str(Label("//:orfs")) + ") " + " ".join(wrap_args(stage_args[stage])) + " bazel-" + stage + ("_mock_area" if mock_area != None and stage == "generate_abstract" else "") + " elapsed",
        outs = outs.get(stage, []),
    ) for ((_, previous), (i, stage)) in zip([(0, "n/a")] + enumerate(stages), enumerate(stages))]
