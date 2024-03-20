"""
This module contains a definiton of build_openroad() macro used for declaring
targets for running physical design flow with OpenROAD-flow-scripts.
"""

def enumerate(iterable):
    """
    Convert list of elements into list of tuples (index, element)

    Args:
      iterable: collection of objects

    Returns:
      list of tuples in form of (index, element)
    """
    result = []
    for i in range(len(iterable)):
        result.append((i, iterable[i]))
    return result

def map(func, iterable):
    """
    Convert list of elements into list of mapped elements according to the mapping function

    Args:
      func: mapping function
      iterable: collection of objects

    Returns:
      list of mapped elements
    """
    result = []
    for item in iterable:
        result.append(func(item))
    return result

def map2(func, iterable):
    """
    Convert list of elements into list of mapped elements according to the mapping function

    Args:
      func: mapping function
      iterable: collection of objects

    Returns:
      list of mapped elements
    """
    result = []
    for item in iterable:
        result.append(func(item))
    return result

def set(iterable):
    """
    Create a list out of `iterable` of strings with all whitespace removed

    Args:
      iterable: collection of strings

    Returns:
      List of strings with removed whitespaces
    """
    result = []
    for item in iterable:
        if item not in result:
            result = result + [item.strip()]
    return result

def filter(iterable, func):
    """
    Filter out elements from `iterable` according to the results of `func`.

    Args:
      iterable: collection of strings
      func: function used for filtering out elements of `iterable`. Must return
            true or false. Element is filtered out when function returns false
            for this element

    Returns:
      List with filtered out elements
    """
    result = []
    for item in iterable:
        if func(item):
            result = result + [item]
    return result

def wrap_args(args, escape):
    """
    Wrap environment variables to ensure correct escaping and evaluation.

    Add single quotes to env vars which have values containing spaces.
    Do not ad single quotes for `DESIGN_CONFIG` env var - it contains
    $(location <path>) which will be later expanded to regular path
    and does not require this modification.

    Args:
      args: list of strings containing environment variables definitions
      escape: flag controlling whether the env var value should have escaped quotes

    Returns:
      List of wrapped environment variables definitions
    """
    wrapped_args = []

    for arg in args:
        splt = arg.split("=", 1)
        if (len(splt) == 2):
            if (" " in splt[1]):
                if (escape):
                    wrapped_args.append(splt[0] + "=\\\'" + splt[1] + "\\\'")
                else:
                    wrapped_args.append(splt[0] + "='" + splt[1] + "'")
            else:
                wrapped_args.append(arg)
        else:
            wrapped_args.append(arg)
    return wrapped_args

def write_config(
        name,
        design_name,
        env = {},
        env_list = []):
    """
    Writes config file for running physical design flow with OpenROAD-flow-scripts.

    It appends a common configuration file and additional make rules used for
    calling complex ORFS flows.

    Args:
      name: name of the design target
      design_name: short name of the design
      env: dictionary of environment variables to be placed in the config file
      env_list: list of environment variables to be placed in the config file
    """

    export_env = ""
    for var, value in env.items():
        export_env += "export " + var + "=" + value + "\n"
    for env_var in env_list:
        export_env += "export " + env_var + "\n"

    export_env += "export DESIGN_NAME=" + design_name + "\n"
    export_env += "export UTIL_TCL=\\$$(BUILD_DIR)/util.tcl\n"

    native.genrule(
        name = name,
        srcs = [
            Label("//:config_common.mk"),
        ],
        cmd = """
               echo \"# Common config\" > $@
               cat $(location """ + str(Label("//:config_common.mk")) + """) >> $@
               echo \"\n# Design config\" >> $@
               echo \"""" + export_env + """\" >> $@
               echo \"# Make rules\" >> $@
               echo \"include \\$$(BUILD_DIR)/\\$$(MAKE_PATTERN)\" >> $@
              """,
        outs = [name + ".mk"],
    )

def get_make_targets(
        stage,
        do_mock_area,
        mock_area):
    """
    Prepare make targets to execute in ORFS environment.

    Args:
      stage: name of the stage to execute
      do_mock_area: flag to recognize if the target should be always a mock_area target
      mock_area: floating point number, will always run _mock_area target for generate_abstract stage if set,
                 even if do_mock_area is not set

    Returns:
      string with space-separated make targets to be executed in ORFS environment
    """
    targets = "bazel-" + stage
    if (mock_area != None and stage == "generate_abstract"):
        targets += "_mock_area"
    elif (do_mock_area and stage == "floorplan"):
        targets += "-mock_area"
    targets += " elapsed"

    return targets

def get_docker_shell_cmd(
        make_pattern,
        design_config,
        make_targets,
        docker_shell = Label("//:docker_shell"),
        or_image = "bazel-orfs/orfs_env:latest"):
    """
    Prepare command line for running docker_shell utility

    Args:
      make_pattern: label pointing to makefile conatining rules relevant to current stage
      design_config: label pointing to design-specific generated config.mk file
      make_targets: string with space-separated make targets to be executed in ORFS environment
      docker_shell: label pointing to the entrypint script for running ORFS flow
      or_image: name of the docker image used for running ORFS flow

    Returns:
      string with command line for running ORFS flow in docker container
    """

    cmd = "OR_IMAGE=" + or_image
    cmd += " MAKE_PATTERN=$(location " + str(make_pattern) + ")"
    cmd += " RULEDIR=$(RULEDIR)"
    cmd += " CONFIG=$(location " + str(design_config) + ")"
    cmd += " $(location " + str(docker_shell) + ")"
    cmd += " make "
    cmd += make_targets

    return cmd

def mock_area_stages(
        name,
        design_name,
        stage_sources,
        env_list,
        outs,
        variant,
        mock_area):
    """
    Spawn mock_area targets.

    Filter out unnecessary ORFS options and inject new ones for the mock_area flow.
    Generate config.mk specific for those targets

    Args:
      name: name of the target design
      design_name: short name of the design
      stage_sources: dictionary of lists with sources for each flow stage
      env_list: list of environment variables to be placed in the config file
      outs: dictionary of lists with paths to output files for each flow stage
      variant: default variant of the ORFS flow, used for replacing output paths
      mock_area: floating point number used for scaling the design
    """

    # Write ORFS options for mock_area targets
    # Filter out options affecting Chip Area and default flow variant
    mock_area_env_list = [s for s in env_list if not any([sub in s for sub in ("DIE_AREA", "CORE_AREA", "CORE_UTILIZATION", "FLOW_VARIANT")])]

    # Add mock_area-specific options
    mock_area_env_list.append("FLOW_VARIANT=mock_area")
    mock_area_env_list.append("DEFAULT_FLOW_VARIANT=" + variant)
    mock_area_env_list.append("MOCK_AREA=" + str(mock_area))
    mock_area_env_list.append("MOCK_AREA_TCL=\\$$(BUILD_DIR)/mock_area.tcl")
    mock_area_env_list.append("SYNTH_GUT=1")
    mock_area_env_list.append("ABSTRACT_SOURCE=2_floorplan")

    # Generate config for mock_area targets
    write_config(
        name = name + "_mock_area_config",
        design_name = design_name,
        env_list = mock_area_env_list,
    )

    mock_stages = ["clock_period", "synth", "synth_sdc", "floorplan", "generate_abstract"]

    for (previous, stage) in zip(["n/a"] + mock_stages, mock_stages):
        make_pattern = Label("//:" + stage + "-bazel.mk")
        design_config = Label("//:" + name + "_mock_area_config.mk")
        make_targets = get_make_targets(stage, True, mock_area)

        native.genrule(
            name = name + "_" + stage + "_mock_area",
            tools = [Label("//:docker_shell")],
            srcs = ["//:orfs_env", make_pattern, design_config] +
                   stage_sources[stage] +
                   ([name + "_" + stage, Label("mock_area.tcl")] if stage == "floorplan" else []) +
                   ([name + "_" + previous + "_mock_area"] if stage != "clock_period" else []) +
                   ([name + "_synth_mock_area"] if stage == "floorplan" else []),
            cmd = get_docker_shell_cmd(make_pattern, design_config, make_targets),
            outs = [s.replace("/" + variant + "/", "/mock_area/") for s in outs.get(stage, [])],
        )

def build_openroad(
        name,
        variant = "base",
        verilog_files = [],
        stage_sources = {},
        macros = [],
        macro_variants = {},
        io_constraints = None,
        stage_args = {},
        mock_abstract = False,
        mock_stage = "place",
        mock_area = None,
        platform = "asap7",
        macro_variant = "base"):
    """
    Spawns targets for running physical design flow with OpenROAD-flow-scripts.

    Args:
      name: name of the macro target
      variant: variant of the ORFS flow, sets FLOW_VARIANT env var (see https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/108bcf54464e989e6715bee18c3af3d3356e5023/flow/Makefile#L198)
      verilog_files: list of verilog sources of the design
      stage_sources: dictionary keyed by ORFS stages with lists of stage-specific sources
      macros: list of macros required to run physical design flow for this design
      macro_variants: dictionary keyed by macro names containing the variant of the ORFS flow that the macro was built with
      io_constraints: path to tcl script with IO constraints
      stage_args: dictionary keyed by ORFS stages with lists of stage-specific arguments
      mock_abstract: boolean controlling the scope of _generate_abstract stage
      mock_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      mock_area: floating point number, spawns additional _mock_area targets if set
      platform: string specifying target platform for running physical design flow. Supported platforms: https://openroad-flow-scripts.readthedocs.io/en/latest/user/FlowVariables.html#platform
      macro_variant: variant of the ORFS flow the macro was built with
    """
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
    ]

    x = map(lambda ext: map2(lambda m: "//:results/" + platform + "/%s/%s/%s.%s" % (m, macro_variants.get(m, macro_variant), m, ext), macros), ["lef", "lib"])
    macro_lef_targets, macro_lib_targets = x
    # macro_gds_targets = map(lambda m: "//:results/" + platform + "/%s/%s/6_final.gds" % (m, macro_variants.get(m, macro_variant)), macros)

    stage_sources = dict(stage_sources)

    SDC_FILE_CLOCK_PERIOD = "results/" + platform + "/%s/%s/clock_period.txt" % (output_folder_name, variant)
    stage_sources["synth"] = ["//:util.tcl"] + stage_sources.get("synth", []) + set(verilog_files)
    io_constraints_source = ([io_constraints] if io_constraints != None else [])
    stage_sources["floorplan"] = ["//:util.tcl"] + stage_sources.get("floorplan", []) + io_constraints_source
    stage_sources["place"] = ["//:util.tcl"] + stage_sources.get("place", []) + io_constraints_source

    stage_args = dict(stage_args)

    ADDITIONAL_LEFS = " ".join(map(lambda m: "\\$$(BUILD_DIR)/$(RULEDIR)/results/" + platform + "/%s/%s/%s.lef" % (m, macro_variants.get(m, macro_variant), m), macros))
    ADDITIONAL_LIBS = " ".join(map(lambda m: "\\$$(BUILD_DIR)/$(RULEDIR)/results/" + platform + "/%s/%s/%s.lib" % (m, macro_variants.get(m, macro_variant), m), macros))
    # ADDITIONAL_GDS_FILES = " ".join(map(lambda m: "\\$$(BUILD_DIR)/$(RULEDIR)/results/" + platform + "/%s/%s/6_final.gds" % (m, macro_variants.get(m, macro_variant)), macros))

    io_constraints_args = ["IO_CONSTRAINTS=\\$$(BUILD_DIR)/" + io_constraints] if io_constraints != None else []

    lefs_args = (["ADDITIONAL_LEFS=" + ADDITIONAL_LEFS] if len(macros) > 0 else [])
    libs_args = (["ADDITIONAL_LIBS=" + ADDITIONAL_LIBS] if len(macros) > 0 else [])
    # gds_args = (["ADDITIONAL_GDS_FILES=" + ADDITIONAL_GDS_FILES] if len(macros) > 0 else [])

    extended_verilog_files = []
    for file in verilog_files:
        extended_verilog_files.append("\\$$(BUILD_DIR)/" + file)
    stage_args["synth"] = stage_args.get("synth", []) + [
        "VERILOG_FILES=" + " ".join(extended_verilog_files),
        "SDC_FILE_CLOCK_PERIOD=\\$$(BUILD_DIR)/" + SDC_FILE_CLOCK_PERIOD,
    ]
    stage_args["floorplan"] = stage_args.get("floorplan", []) + (
        [] if len(macros) == 0 else [
            "CORE_MARGIN=4",
            "PDN_TCL=\\$${PLATFORM_DIR}/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        ]
    ) + io_constraints_args + (["MACROS=" + " ".join(set(macros))] if len(macros) > 0 else [])

    stage_args["place"] = stage_args.get("place", []) + io_constraints_args

    stage_args["cts"] = stage_args.get("cts", [])

    stage_args["final"] = stage_args.get("final", []) + (
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

    for stage in ["synth", "floorplan", "place", "cts", "grt", "route", "final"]:
        stage_args[stage] = stage_args.get(stage, []) + libs_args
        stage_sources[stage] = stage_sources.get(stage, []) + macro_lib_targets

    abstract_source = str(name_to_stage[mock_stage]) + "_" + mock_stage
    stage_args["generate_abstract"] = stage_args.get("generate_abstract", []) + (
        ["ABSTRACT_SOURCE=" + abstract_source] if mock_abstract else []
    )

    base_args = [
        "WORK_HOME=$(RULEDIR)",
        "DESIGN_NAME=" + name,
        "FLOW_VARIANT=" + variant,
        "DESIGN_CONFIG=$(location " + str(Label("//:config.mk")) + ")",
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
        "SDC_FILE=\\$$(BUILD_DIR)/" + SDC_FILE,
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

    for stage in ["floorplan", "final", "generate_abstract"]:
        stage_args[stage] = stage_args.get(stage, []) + lefs_args
        stage_sources[stage] = stage_sources.get(stage, []) + macro_lef_targets

    # FIXME add support for .gds files.
    #
    # The code currently assumes that .gds files are needed and produced by
    # the "generate_abstract" stage, which is wrong. .gds files are needed and
    # produced only by the "final" stage. Once the code is updated to reflect this,
    # a macro can produce an artifact at e.g. floorplan, yet have targets to run
    # through the "final" stage to produce the .gds file. This way, a higher level
    # macro can depend on abstracts without running all the way to completion, yet
    # have a valid .gds file dependency chain for the unused final stages.
    #
    # for stage in ["final", "generate_abstract"]:
    #     stage_args[stage] = stage_args.get(stage, []) + gds_args
    #     stage_sources[stage] = stage_sources.get(stage, []) + macro_gds_targets

    make_args = []

    for stage in stages:
        make_pattern = Label("//:" + stage + "-bazel.mk")
        make_args = ["make"] + ["MAKE_PATTERN=$(location " + str(make_pattern) + ")"] + base_args

        native.genrule(
            name = target_name + "_" + stage + "_make_script",
            tools = [],
            srcs = [
                       Label("//:make_script.template.sh"),
                       Label("//:" + stage + "-bazel.mk"),
                   ] +
                   all_sources,
            cmd = "echo \"chmod -R +w . && \" `cat $(location " + str(Label("//:make_script.template.sh")) + ")` " + " ".join(wrap_args(make_args, True)) + " ".join(wrap_args(stage_args.get(stage, []), True)) + " 'MAKE_PATTERN=$$(rlocation bazel-orfs/" + stage + "-bazel.mk)' " + " 'DESIGN_CONFIG=$$(rlocation bazel-orfs/config.mk)' " + " \\\"$$\\@\\\" > $@",
            outs = ["logs/" + platform + "/%s/%s/make_script_%s.sh" % (output_folder_name, variant, stage)],
        )

        native.sh_binary(
            name = target_name + "_" + stage + "_make",
            srcs = ["//:" + target_name + "_" + stage + "_make_script"],
            data = [Label("//:orfs"), make_pattern, Label("//:config.mk")],
            deps = ["@bazel_tools//tools/bash/runfiles"],
        )

    # Write all ORFS options to list
    env_list = []
    for stage, envs in stage_args.items():
        env_list += envs

    env_list.append("FLOW_VARIANT=" + variant)

    # Generate config for stage targets
    write_config(
        name = target_name + "_config",
        design_name = name,
        env_list = env_list,
    )

    if mock_area != None:
        mock_area_stages(target_name, name, stage_sources, env_list, outs, variant, mock_area)

    native.genrule(
        name = target_name + "_memory",
        tools = [Label("//:orfs")],
        srcs = all_sources + stage_sources["synth"] + [name + "_clock_period"],
        cmd = "$(location " + str(Label("//:orfs")) + ") " + " ".join(wrap_args(make_args, False)) + " ".join(wrap_args(stage_args["synth"], False)) + " memory",
        outs = outs["memory"],
    )

    for ((_, previous), (i, stage)) in zip([(0, "n/a")] + enumerate(stages), enumerate(stages)):
        make_pattern = Label("//:" + stage + "-bazel.mk")
        design_config = Label("//:" + target_name + "_config.mk")
        make_targets = get_make_targets(stage, False, mock_area)
        native.genrule(
            name = target_name + "_" + stage,
            tools = [Label("//:docker_shell")],
            srcs = ["//:orfs_env", make_pattern] + stage_sources[stage] + [target_name + "_config.mk"] + ([name + target_ext + "_" + previous] if stage not in ("clock_period", "synth_sdc", "synth") else []) +
                   ([name + target_ext + "_generate_abstract_mock_area"] if mock_area != None and stage == "generate_abstract" else []),
            cmd = get_docker_shell_cmd(make_pattern, design_config, make_targets),
            outs = outs.get(stage, []),
        )
