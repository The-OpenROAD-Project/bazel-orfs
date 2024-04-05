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
        variant,
        additional_cfg = []):
    """
    Writes config file for running physical design flow with OpenROAD-flow-scripts.

    It appends a common configuration file and additional make rules used for
    calling complex ORFS flows.

    Args:
      name: name of the design target
      design_name: short name of the design
      variant: variant of the ORFS flow
      additional_cfg: list of strings with definitions of additional configuration env vars
    """

    export_env = "export DESIGN_NAME=" + design_name + "\n"
    export_env += "export FLOW_VARIANT=" + variant + "\n"

    add_cfg = ""
    for cfg in additional_cfg:
        add_cfg += "export " + cfg + "\n"

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
               echo \"\n# Additional config\" >> $@
               echo \"""" + add_cfg + """\" >> $@
               echo \"\n# Stage config\" >> $@
               echo \"include \\$$(STAGE_CONFIG)\" >> $@
               echo \"# Make rules\" >> $@
               echo \"include \\$$(MAKE_PATTERN)\" >> $@
              """,
        outs = [name + ".mk"],
    )

def write_stage_config(
        name,
        stage,
        srcs,
        stage_args):
    """
    Writes config file for running physical design flow with OpenROAD-flow-scripts.

    It appends a common configuration file and additional make rules used for
    calling complex ORFS flows.

    Args:
      name: name of the design target
      stage: ORFS stage for which the config is generated
      srcs: list of sources required for generating the config
      stage_args: list of environment variables to be placed in the config file
    """

    export_env = ""
    for env_var in stage_args:
        export_env += "export " + env_var + "\n"

    native.genrule(
        name = name,
        srcs = srcs,
        cmd = """
               echo \"# Stage """ + stage + """ config\" > $@
               echo \"""" + export_env + """\" >> $@
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

def get_entrypoint_cmd(
        make_pattern,
        design_config,
        stage_config,
        entrypoint,
        make_targets = None,
        docker_image = None):
    """
    Prepare command line for running docker_shell utility

    Args:
      make_pattern: label pointing to makefile conatining rules relevant to current stage
      design_config: label pointing to design-specific generated config.mk file
      stage_config: label pointing to stage- and design-specific generated config.mk file
      make_targets: string with space-separated make targets to be executed in ORFS environment
      entrypoint: label pointing to the entrypint script for running ORFS flow
      docker_image: name of the docker image used for running ORFS flow

    Returns:
      string with command line for running ORFS flow in docker container
    """

    cmd = ""
    if (docker_image != None):
        cmd += "OR_IMAGE=" + docker_image
    cmd += " DESIGN_CONFIG=$(location " + str(design_config) + ")"
    cmd += " STAGE_CONFIG=$(location " + str(stage_config) + ")"
    cmd += " MAKE_PATTERN=$(location " + str(make_pattern) + ")"
    cmd += " RULEDIR=$(RULEDIR)"
    cmd += " $(location " + str(entrypoint) + ")"
    cmd += " make "
    if (make_targets != None):
        cmd += make_targets

    return cmd

def mock_area_stages(
        name,
        design_name,
        stage_sources,
        io_constraints,
        sdc_constraints,
        stage_args,
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
      io_constraints: path to tcl script with IO constraints
      sdc_constraints: path to SDC file with design constraints
      stage_args: dictionary keyed by ORFS stages with lists of stage-specific arguments
      outs: dictionary of lists with paths to output files for each flow stage
      variant: default variant of the ORFS flow, used for replacing output paths
      mock_area: floating point number used for scaling the design
    """

    # Write ORFS options for mock_area targets
    # Filter out floorplan options affecting Chip Area and default flow variant
    floorplan_args = [s for s in stage_args["floorplan"] if not any([sub in s for sub in ("DIE_AREA", "CORE_AREA", "CORE_UTILIZATION")])]
    mock_area_stage_args = dict(stage_args)
    mock_area_stage_args["floorplan"] = floorplan_args

    # Add mock_area-specific options
    mock_area_env_list = ["DEFAULT_FLOW_VARIANT=" + variant]
    mock_area_env_list.append("MOCK_AREA=" + str(mock_area))
    mock_area_env_list.append("MOCK_AREA_TCL=\\$$(BUILD_DIR)/mock_area.tcl")
    mock_area_env_list.append("SYNTH_GUT=1")
    mock_area_env_list.append("ABSTRACT_SOURCE=2_floorplan")

    # Generate config for mock_area targets
    write_config(
        name = name + "_mock_area_config",
        design_name = design_name,
        variant = "mock_area",
        additional_cfg = mock_area_env_list,
    )

    mock_stages = ["clock_period", "synth", "synth_sdc", "floorplan", "generate_abstract"]

    for (previous, stage) in zip(["n/a"] + mock_stages, mock_stages):
        stage_cfg_srcs = []
        if sdc_constraints != None:
            stage_cfg_srcs.append(sdc_constraints)
        if io_constraints != None:
            stage_cfg_srcs.append(io_constraints)

        # Generate config for stage targets
        write_stage_config(
            name = name + "_" + stage + "_mock_area_config",
            stage = stage,
            srcs = stage_cfg_srcs,
            stage_args = mock_area_stage_args[stage],
        )
        make_pattern = Label("//:" + stage + "-bazel.mk")
        design_config = Label("@@//:" + name + "_mock_area_config.mk")
        stage_config = Label("@@//:" + name + "_" + stage + "_mock_area_config.mk")
        make_targets = get_make_targets(stage, True, mock_area)

        native.genrule(
            name = name + "_" + stage + "_mock_area",
            tools = [Label("//:docker_shell")],
            srcs = [make_pattern, design_config, stage_config] +
                   stage_sources[stage] +
                   ([name + "_" + stage, Label("//:mock_area.tcl")] if stage == "floorplan" else []) +
                   ([name + "_" + previous + "_mock_area"] if stage != "clock_period" else []) +
                   ([name + "_synth_mock_area"] if stage == "floorplan" else []),
            cmd = get_entrypoint_cmd(make_pattern, design_config, stage_config, Label("//:docker_shell"), make_targets, docker_image = "bazel-orfs/orfs_env:latest"),
            outs = [s.replace("/" + variant + "/", "/mock_area/") for s in outs.get(stage, [])],
        )

def init_stage_dict(all_stage_names, stage_dict_init):
    """
    Initialize stage dictionary

    Args:
      all_stage_names: list of strings describing stages of the ORFS flow, keys of the dictionary
      stage_dict_init: dictionary used for providing intial values

    Returns:
      Dictionary keyed with all provided ORFS stage names with contents of stage_dict_init or an empty list
    """
    d = {}
    for stage in all_stage_names:
        d[stage] = stage_dict_init.get(stage, [])

    return d

def get_reports_dict():
    """
    Initialize reports dictionary

    Returns:
      Dictionary keyed relevant ORFS stage names. Dictionary elements contain lists of report names
    """
    return {
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

def init_output_dict(all_stages, platform, out_dir, variant, name):
    """
    Initialize output dictionary

    Args:
      all_stages: list of stages relevant to providing output files from ORFS flow
      platform: target platform, e.g. "asap7"
      out_dir: name of the output directory for the ORFS flow
      variant: variant of the ORFS flow
      name: name of the design

    Returns:
      Dictionary keyed with stages relevant for providing output files from ORFS flow.
      Elements contain a list of output files for given stage.
    """
    outs = {
        "clock_period": [
            "results/%s/%s/%s/clock_period.txt" % (platform, out_dir, variant),
        ],
        "synth_sdc": [
            "results/%s/%s/%s/1_synth.sdc" % (platform, out_dir, variant),
        ],
        "synth": [
            "results/%s/%s/%s/1_synth.v" % (platform, out_dir, variant),
        ],
        "generate_abstract": [
            "results/%s/%s/%s/%s.lib" % (platform, out_dir, variant, name),
            "results/%s/%s/%s/%s.lef" % (platform, out_dir, variant, name),
        ],
        "final": [
            "results/%s/%s/%s/6_final.spef" % (platform, out_dir, variant),
            "results/%s/%s/%s/6_final.gds" % (platform, out_dir, variant),
        ],
        "grt": ["reports/%s/%s/%s/congestion.rpt" % (platform, out_dir, variant)],
        "route": ["reports/%s/%s/%s/5_route_drc.rpt" % (platform, out_dir, variant)],
        "memory": ["results/%s/%s/%s/mem.json" % (platform, out_dir, variant)],
    }

    stage_num = dict(map(lambda s: (s[1], s[0]), all_stages))

    for stage, i in map(
        lambda stage: (stage, stage_num[stage]),
        ["floorplan", "place", "cts", "grt", "route", "final"],
    ):
        outs[stage] = outs.get(stage, []) + [
            "results/%s/%s/%s/%s.sdc" % (platform, out_dir, variant, str(i) + "_" + stage),
            "results/%s/%s/%s/%s.odb" % (platform, out_dir, variant, str(i) + "_" + stage),
        ]

    for stage in ["place", "grt"]:
        outs[stage] = outs.get(stage, []) + [
            "results/%s/%s/%s/%s.ok" % (platform, out_dir, variant, stage),
        ]

    reports = get_reports_dict()
    for stage in reports:
        outs[stage] = outs.get(stage, []) + list(
            map(lambda log: "logs/%s/%s/%s/%s.log" % (platform, out_dir, variant, log), reports[stage]),
        )

    return outs

def build_openroad(
        name,
        variant = "base",
        verilog_files = [],
        stage_sources = {},
        macros = [],
        macro_variants = {},
        io_constraints = None,
        sdc_constraints = None,
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
      sdc_constraints: path to SDC file with design constraints
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

    out_dir = source_folder_name

    outs = init_output_dict(all_stages, platform, out_dir, variant, name)

    x = map(lambda ext: map2(lambda m: "//:results/" + platform + "/%s/%s/%s.%s" % (m, macro_variants.get(m, macro_variant), m, ext), macros), ["lef", "lib"])
    macro_lef_targets, macro_lib_targets = x
    # macro_gds_targets = map(lambda m: "//:results/" + platform + "/%s/%s/6_final.gds" % (m, macro_variants.get(m, macro_variant)), macros)

    io_constraints_args = ["IO_CONSTRAINTS=\\$$(BUILD_DIR)/$(location " + io_constraints + ")"] if io_constraints != None else []

    ADDITIONAL_LEFS = " ".join(map(lambda m: "\\$$(BUILD_DIR)/$(RULEDIR)/results/" + platform + "/%s/%s/%s.lef" % (m, macro_variants.get(m, macro_variant), m), macros))
    ADDITIONAL_LIBS = " ".join(map(lambda m: "\\$$(BUILD_DIR)/$(RULEDIR)/results/" + platform + "/%s/%s/%s.lib" % (m, macro_variants.get(m, macro_variant), m), macros))
    # ADDITIONAL_GDS_FILES = " ".join(map(lambda m: "\\$$(BUILD_DIR)/$(RULEDIR)/results/" + platform + "/%s/%s/6_final.gds" % (m, macro_variants.get(m, macro_variant)), macros))

    lefs_args = (["ADDITIONAL_LEFS=" + ADDITIONAL_LEFS] if len(macros) > 0 else [])
    libs_args = (["ADDITIONAL_LIBS=" + ADDITIONAL_LIBS] if len(macros) > 0 else [])
    # gds_args = (["ADDITIONAL_GDS_FILES=" + ADDITIONAL_GDS_FILES] if len(macros) > 0 else [])

    extended_verilog_files = []
    for file in verilog_files:
        extended_verilog_files.append("\\$$(BUILD_DIR)/" + file)

    SDC_FILE_CLOCK_PERIOD = outs["clock_period"][0]
    SDC_FILE = ["SDC_FILE=\\$$(BUILD_DIR)/$(location " + sdc_constraints + ")"] if sdc_constraints != None else []

    abstract_source = str(name_to_stage[mock_stage]) + "_" + mock_stage

    stage_args = init_stage_dict(all_stage_names, stage_args)
    stage_args["clock_period"] = SDC_FILE
    stage_args["synth_sdc"] = SDC_FILE
    stage_args["synth"].append("VERILOG_FILES=" + " ".join(extended_verilog_files))
    stage_args["synth"].append("SDC_FILE_CLOCK_PERIOD=\\$$(BUILD_DIR)/" + SDC_FILE_CLOCK_PERIOD)
    stage_args["floorplan"] += SDC_FILE + (
        [] if len(macros) == 0 else [
            "CORE_MARGIN=4",
            "PDN_TCL=\\$${PLATFORM_DIR}/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        ]
    ) + io_constraints_args + (["MACROS=" + " ".join(set(macros))] if len(macros) > 0 else [])

    stage_args["place"] += io_constraints_args
    stage_args["route"] += [] if len(macros) == 0 else [
        "MIN_ROUTING_LAYER=M2",
        "MAX_ROUTING_LAYER=M9",
    ]
    stage_args["final"] += (["GND_NETS_VOLTAGES=\"\"", "PWR_NETS_VOLTAGES=\"\""] +
                            ["GDS_ALLOW_EMPTY=(" + "|".join(macros) + ")"] if len(macros) > 0 else [])
    stage_args["generate_abstract"] += ["ABSTRACT_SOURCE=" + abstract_source] if mock_abstract else []

    stage_sources = init_stage_dict(all_stage_names, stage_sources)
    if sdc_constraints != None:
        stage_sources["synth_sdc"] = [sdc_constraints]
        stage_sources["clock_period"] = [sdc_constraints]
    stage_sources["synth"] = list(filter(stage_sources["synth"], lambda s: not s.endswith(".sdc")))
    stage_sources["synth"] += set(verilog_files)
    stage_sources["floorplan"].append(name + target_ext + "_synth")
    if io_constraints != None:
        stage_sources["floorplan"].append(io_constraints)
        stage_sources["place"].append(io_constraints)
    stage_sources["route"] += outs["cts"]
    for stage in ["floorplan", "final", "generate_abstract"]:
        stage_args[stage] += lefs_args
        stage_sources[stage] += macro_lef_targets
    for stage in ["synth", "floorplan", "place", "cts", "grt", "route", "final"]:
        stage_args[stage] += libs_args
        stage_sources[stage] += macro_lib_targets

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
    #     stage_args[stage] += gds_args
    #     stage_sources[stage] += macro_gds_targets

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

    # Make (local) targets
    make_script_template = Label("//:make_script.template.sh")
    design_config = Label("@@//:" + target_name + "_config.mk")
    for stage in stages:
        make_pattern = Label("//:" + stage + "-bazel.mk")
        stage_config = Label("@@//:" + target_name + "_" + stage + "_config.mk")
        make_targets = get_make_targets(stage, False, mock_area)
        entrypoint_cmd = get_entrypoint_cmd(make_pattern, design_config, stage_config, entrypoint = Label("//:orfs"))

        native.genrule(
            name = target_name + "_" + stage + "_make_script",
            tools = [Label("//:orfs")],
            srcs = [make_script_template, design_config, stage_config, make_pattern],
            cmd = "echo \"chmod -R +w . && \" `cat $(location " + str(make_script_template) + ")` " + entrypoint_cmd + " \\\"$$\\@\\\" > $@",
            outs = ["logs/%s/%s/%s/make_script_%s.sh" % (platform, out_dir, variant, stage)],
        )

        native.sh_binary(
            name = target_name + "_" + stage + "_make",
            srcs = ["//:" + target_name + "_" + stage + "_make_script"],
            data = [Label("//:orfs"), design_config, stage_config, make_pattern],
            deps = ["@bazel_tools//tools/bash/runfiles"],
        )

    # Generate general config for design stage targets
    write_config(
        name = target_name + "_config",
        design_name = name,
        variant = variant,
    )

    if mock_area != None:
        mock_area_stages(target_name, name, stage_sources, io_constraints, sdc_constraints, stage_args, outs, variant, mock_area)

    # *_memory targets
    write_stage_config(
        name = target_name + "_memory_config",
        stage = "memory",
        srcs = [],
        stage_args = stage_args["synth"],
    )
    make_pattern = Label("//:memory-bazel.mk")
    stage_config = Label("//:" + target_name + "_memory_config.mk")
    entrypoint_cmd = get_entrypoint_cmd(make_pattern, design_config, stage_config, Label("//:orfs"))
    native.genrule(
        name = target_name + "_memory_make_script",
        tools = [Label("//:orfs")],
        srcs = [make_script_template, design_config, stage_config, make_pattern],
        cmd = "echo \"chmod -R +w . && \" `cat $(location " + str(make_script_template) + ")` " + entrypoint_cmd + " \\\"$$\\@\\\" > $@",
        outs = ["logs/%s/%s/%s/make_script_memory.sh" % (platform, out_dir, variant)],
    )
    native.sh_binary(
        name = target_name + "_memory_make",
        srcs = ["//:" + target_name + "_memory_make_script"],
        data = [Label("//:orfs"), design_config, stage_config, make_pattern],
        deps = ["@bazel_tools//tools/bash/runfiles"],
    )
    native.genrule(
        name = target_name + "_memory",
        tools = [Label("//:docker_shell")],
        srcs = [Label("//:scripts/mem_dump.py"), Label("//:scripts/mem_dump.tcl"), target_name + "_clock_period", design_config, stage_config, make_pattern],
        cmd = get_entrypoint_cmd(make_pattern, design_config, stage_config, Label("//:docker_shell"), "memory", docker_image = "bazel-orfs/orfs_env:latest"),
        outs = outs["memory"],
    )

    # Stage (Docker) targets
    for (previous, stage) in zip(["n/a"] + stages, stages):
        # Generate config for stage targets
        stage_cfg_srcs = []
        if sdc_constraints != None:
            stage_cfg_srcs.append(sdc_constraints)
        if io_constraints != None:
            stage_cfg_srcs.append(io_constraints)
        write_stage_config(
            name = target_name + "_" + stage + "_config",
            stage = stage,
            srcs = stage_cfg_srcs,
            stage_args = stage_args[stage],
        )

        make_pattern = Label("//:" + stage + "-bazel.mk")
        design_config = Label("@@//:" + target_name + "_config.mk")
        stage_config = Label("@@//:" + target_name + "_" + stage + "_config.mk")
        make_targets = get_make_targets(stage, False, mock_area)

        native.genrule(
            name = target_name + "_" + stage,
            tools = [Label("//:docker_shell")],
            srcs = [make_pattern, design_config, stage_config] + stage_sources[stage] + ([name + target_ext + "_" + previous] if stage not in ("clock_period", "synth_sdc") else []) +
                   ([name + target_ext + "_generate_abstract_mock_area"] if mock_area != None and stage == "generate_abstract" else []),
            cmd = get_entrypoint_cmd(make_pattern, design_config, stage_config, Label("//:docker_shell"), make_targets, docker_image = "bazel-orfs/orfs_env:latest"),
            outs = outs.get(stage, []),
        )
