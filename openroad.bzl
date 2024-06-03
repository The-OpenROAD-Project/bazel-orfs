"""
This module contains a definiton of build_openroad() macro used for declaring
targets for running physical design flow with OpenROAD-flow-scripts.
"""

def add_options_all_stages(options, new_options):
    """Add new_options to all options in options dictionary.

    Args:
        options (dict): options dictionary
        new_options: options to add to all options in dictionary.

    Returns:
        dict: A new updated dictionary.
    """
    result = {}
    for key, value in options.items():
        result[key] = value + new_options
    return result

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
        additional_cfg = [],
        external_pdk = None):
    """
    Writes config file for running physical design flow with OpenROAD-flow-scripts.

    It appends a common configuration file and additional make rules used for
    calling complex ORFS flows.

    Args:
      name: name of the design target
      design_name: short name of the design
      variant: variant of the ORFS flow
      additional_cfg: list of strings with definitions of additional configuration env vars
      external_pdk: label pointing to the external PDK dependency
    """

    export_env = "export DESIGN_NAME=" + design_name + "\n"
    export_env += "export FLOW_VARIANT=" + variant + "\n"

    cfg_srcs = [Label("//:config_common.mk")]
    if (external_pdk != None):
        pdk_label = Label(external_pdk)
        pdk_name = pdk_label.package
        export_env += "export PLATFORM=" + pdk_name + "\n"
        export_env += "export PLATFORM_HOME=$$(echo \"$(location " + external_pdk + ":BUILD)\" | sed -e 's/\\(\\/" + pdk_name + "\\/BUILD\\)*$$//g')\n"
        cfg_srcs.append(external_pdk + ":BUILD")

    add_cfg = ""
    for cfg in additional_cfg:
        add_cfg += "export " + cfg + "\n"

    native.genrule(
        name = name,
        srcs = cfg_srcs,
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

    # `generate_abstract` from "regular" flow should copy mocked LEF file to the regular flow build directory
    # Perform additional `bazel-generate_abstract_mock_area` make target only for `generate_abstract` stages
    # outside of `mock_area` flow context
    if (not do_mock_area and mock_area != None and stage == "generate_abstract"):
        targets += "_mock_area"
    elif (do_mock_area and stage == "floorplan"):
        targets += "-mock_area"
    targets += " elapsed"

    return targets

def get_location(label):
    return "$(location " + str(label) + ")"

def get_entrypoint_cmd(
        make_pattern,
        design_config,
        stage_config,
        use_docker_flow = True,
        make_targets = None,
        docker_image = None,
        mock_area = False,
        entrypoint = None,
        interactive = False,
        debug_prints = False,
        fmt_whitespace = " \\\\\n"):
    """
    Prepare command line for running docker_shell utility

    Args:
      make_pattern: label pointing to makefile conatining rules relevant to current stage
      design_config: label pointing to design-specific generated config.mk file
      stage_config: label pointing to stage- and design-specific generated config.mk file
      make_targets: string with space-separated make targets to be executed in ORFS environment
      use_docker_flow: flag to distinguish whether the command should run docker flow or local flow
      docker_image: name of the docker image used for running ORFS flow
      mock_area: flag describing whether pass additional env var for mock_area target execution
      entrypoint: optional label pointing to file which will be used as entrypoint
      interactive: flag describing whether run docker container in interactive mode
      debug_prints: flag enabling make echo prints and shell trace prints
      fmt_whitespace: variables separator

    Returns:
      string with command line for running ORFS flow in docker container
    """

    cmd = ""

    if (use_docker_flow):
        if entrypoint == None:
            entrypoint = Label("//:docker_shell")
        entrypoint = " $(location " + str(entrypoint) + ")" + fmt_whitespace
    else:
        if entrypoint == None:
            entrypoint = Label("//:orfs")
        entrypoint = " $$(pwd)/$(location " + str(entrypoint) + ")" + fmt_whitespace

    if (docker_image != None):
        cmd += "\\\nOR_IMAGE=" + docker_image + fmt_whitespace + " "
    cmd += "DESIGN_CONFIG=" + get_location(design_config) + fmt_whitespace
    cmd += " STAGE_CONFIG=" + get_location(stage_config) + fmt_whitespace
    cmd += " MAKE_PATTERN=" + get_location(make_pattern) + fmt_whitespace
    if (mock_area):
        cmd += " MOCK_AREA_TCL=" + get_location(Label("//:mock_area.tcl")) + fmt_whitespace
    cmd += " RULEDIR=$(RULEDIR)" + fmt_whitespace
    if debug_prints:
        cmd += " DEBUG_PRINTS=1" + fmt_whitespace
    cmd += entrypoint
    if interactive:
        cmd += " --interactive"
    cmd += " make "
    if not debug_prints:
        cmd += "--silent "
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
        mock_area,
        docker_image,
        debug_prints = False,
        external_pdk = None):
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
      docker_image: name of the docker image used for running ORFS flow
      debug_prints: flag enabling make echo prints and shell trace prints
      external_pdk: label pointing to the external PDK dependency
    """

    # Write ORFS options for mock_area targets
    # Filter out floorplan options affecting Chip Area and default flow variant
    floorplan_args = [s for s in stage_args["floorplan"] if not any([sub in s for sub in ("DIE_AREA", "CORE_AREA", "CORE_UTILIZATION")])]
    generate_abstract_args = [s for s in stage_args["generate_abstract"] if not any(["ABSTRACT_SOURCE" in s])]
    mock_area_stage_args = dict(stage_args)
    mock_area_stage_args["floorplan"] = floorplan_args
    mock_area_stage_args["generate_abstract"] = generate_abstract_args

    # Add mock_area-specific options
    mock_area_env_list = ["DEFAULT_FLOW_VARIANT=" + variant]
    mock_area_env_list.append("MOCK_AREA=" + str(mock_area))
    mock_area_env_list.append("SYNTH_GUT=1")
    mock_area_env_list.append("ABSTRACT_SOURCE=2_floorplan")

    # Generate config for mock_area targets
    write_config(
        name = name + "_mock_area_config",
        design_name = design_name,
        variant = variant,
        additional_cfg = mock_area_env_list,
        external_pdk = external_pdk,
    )

    abstract_stages = ["clock_period", "synth", "synth_sdc", "floorplan", "generate_abstract"]

    for (previous, stage) in zip(["n/a"] + abstract_stages, abstract_stages):
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
            stage_args = mock_area_stage_args[stage] + ["FLOW_VARIANT=mock_area"],
        )
        make_pattern = Label("//:" + stage + "-bazel.mk")
        design_config = Label("@@//" + native.package_name() + ":" + name + "_mock_area_config.mk")
        stage_config = Label("@@//" + native.package_name() + ":" + name + "_" + stage + "_mock_area_config.mk")
        make_targets = get_make_targets(stage, True, mock_area)

        native.genrule(
            name = name + "_" + stage + "_mock_area",
            tools = select({
                "@bazel-orfs//:remote_exec": [Label("//:orfs")],
                "//conditions:default": [Label("//:docker_shell")],
            }),
            srcs = [make_pattern, design_config, stage_config] +
                   stage_sources[stage] +
                   ([name + "_" + stage, Label("//:mock_area.tcl")] if stage == "floorplan" else []) +
                   ([name + "_" + previous + "_mock_area"] if stage != "clock_period" else []) +
                   ([name + "_synth_mock_area"] if stage == "floorplan" else []),
            cmd = select({
                "@bazel-orfs//:remote_exec": "FLOW_HOME=/OpenROAD-flow-scripts/flow " + get_entrypoint_cmd(make_pattern, design_config, stage_config, False, make_targets, mock_area = (stage == "floorplan"), debug_prints = debug_prints, fmt_whitespace = " "),
                "//conditions:default": get_entrypoint_cmd(make_pattern, design_config, stage_config, True, make_targets, docker_image = docker_image, mock_area = (stage == "floorplan"), debug_prints = debug_prints, fmt_whitespace = " "),
            }),
            outs = [s.replace("/" + variant + "/", "/mock_area/") for s in outs.get(stage, [])],
            tags = ["supports-graceful-termination"],
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

def resolve_path(label):
    if native.package_name():
        return "/".join([native.package_name(), label])
    return label

def create_out_rule(name = "out_make_script"):
    """
    Spawns target which creates out script.

    Args:
        name: name of the created target
    """
    native.genrule(
        name = name,
        tools = ["@bazel-orfs//:out_script"],
        srcs = [],
        cmd = "cp $(location @bazel-orfs//:out_script) $@",
        visibility = [":__subpackages__"],
        outs = ["out"],
    )

def _resource_full_cpu(_os_name, _inputs):
    """
    Returns resource set for `cpu_heavy_genrule`.

    It has to be defined as top-level function.

    Args:
        _os_name: Name of the OS
        _inputs: Number of inputs provided for genrule

    Returns:
        Dictionary with required resources (cpu, memory or local_test)
    """
    return {
        "cpu": 512,
    }

def _cpu_heavy_genrule_impl(ctx):
    """
    Implementation of `cpu_heavy_genrule`.

    It should behave like the normal genrule, but uses whole CPU.

    Args:
        ctx: rule context

    Returns:
        List with information providers of this rule
    """
    converted_cmd = ctx.expand_location(ctx.attr.cmd)
    converted_cmd = ctx.expand_make_variables("cmd", converted_cmd, {
        "RULEDIR": ctx.var["BINDIR"] + ("/" + ctx.label.package if ctx.label.package else ""),
    })
    ctx.actions.run_shell(
        inputs = ctx.files.srcs,
        tools = ctx.files.tools,
        outputs = ctx.outputs.outs,
        command = converted_cmd,
        resource_set = _resource_full_cpu,
        mnemonic = "CPUHeavyGenrule",
        progress_message = "Executing CPUHeavyGenrule %{label}",
    )
    return [DefaultInfo(files = depset(ctx.outputs.outs))]

cpu_heavy_genrule = rule(
    implementation = _cpu_heavy_genrule_impl,
    attrs = {
        "tools": attr.label_list(mandatory = True, allow_files = True),
        "srcs": attr.label_list(mandatory = True, allow_files = True),
        "cmd": attr.string(mandatory = True),
        "outs": attr.output_list(mandatory = True),
    },
)

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
        abstract_stage = "generate_abstract",
        mock_area = None,
        platform = "asap7",
        macro_variant = "base",
        docker_image = "openroad/flow-ubuntu22.04-builder:latest",
        debug_prints = False,
        external_pdk = None,
        visibility = ["//visibility:private"]):
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
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      mock_area: floating point number, spawns additional _mock_area targets if set
      platform: string specifying target platform for running physical design flow. Supported platforms: https://openroad-flow-scripts.readthedocs.io/en/latest/user/FlowVariables.html#platform
      macro_variant: variant of the ORFS flow the macro was built with
      docker_image: docker image name or ID with ORFS environment. Referenced image must be available in local docker runtime. Defaults to `openroad/flow-ubuntu22.04-builder:latest` which can be obtained by running: `bazel run orfs_env` or building the image from ORFS sources
      debug_prints: flag enabling make echo prints and shell trace prints
      external_pdk: label pointing to the external PDK dependency
    """
    mock_abstract = abstract_stage != "generate_abstract"
    target_ext = ("_" + variant if variant != "base" else "")
    target_name = name + target_ext
    macros = set(macros + list(macro_variants.keys()))
    all_stages = [
        ("0", "clock_period"),
        ("0", "synth_sdc"),
        ("1", "synth"),
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

    x = map(lambda ext: map2(lambda m: "//" + native.package_name() + ":results/" + platform + "/%s/%s/%s.%s" % (m, macro_variants.get(m, macro_variant), m, ext), macros), ["lef", "lib"])
    macro_lef_targets, macro_lib_targets = x
    # macro_gds_targets = map(lambda m: "//:results/" + platform + "/%s/%s/6_final.gds" % (m, macro_variants.get(m, macro_variant)), macros)

    # Get only the first source from constraints
    io_constraints_args = ["IO_CONSTRAINTS=$$(echo '$(locations " + io_constraints + ")' | cut -d' ' -f 1)"] if io_constraints != None else []

    ADDITIONAL_LEFS = " ".join(map(resolve_path, macro_lef_targets))
    ADDITIONAL_LIBS = " ".join(map(resolve_path, macro_lib_targets))
    # ADDITIONAL_GDS_FILES = " ".join(map(lambda m: "$(RULEDIR)/results/" + platform + "/%s/%s/6_final.gds" % (m, macro_variants.get(m, macro_variant)), macros))

    lefs_args = (["ADDITIONAL_LEFS=" + ADDITIONAL_LEFS] if len(macros) > 0 else [])
    libs_args = (["ADDITIONAL_LIBS=" + ADDITIONAL_LIBS] if len(macros) > 0 else [])
    # gds_args = (["ADDITIONAL_GDS_FILES=" + ADDITIONAL_GDS_FILES] if len(macros) > 0 else [])

    SDC_FILE_CLOCK_PERIOD = outs["clock_period"][0]

    # Get only the first source from constraints
    SDC_FILE = ["SDC_FILE=$$(echo '$(locations " + sdc_constraints + ")' | cut -d' ' -f 1)"] if sdc_constraints != None else []

    abstract_source = str(name_to_stage[abstract_stage]) + "_" + abstract_stage

    stage_args = init_stage_dict(all_stage_names, stage_args)
    stage_args["clock_period"] = SDC_FILE
    stage_args["synth_sdc"] = SDC_FILE
    stage_args["synth"].append("VERILOG_FILES=" + " ".join(map(resolve_path, verilog_files)))
    stage_args["synth"].append("SDC_FILE_CLOCK_PERIOD=" + SDC_FILE_CLOCK_PERIOD)
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
    if io_constraints != None:
        stage_sources["floorplan"].append(io_constraints)
        stage_sources["place"].append(io_constraints)
    stage_sources["route"] += outs["cts"]
    for stage in ["synth", "floorplan", "final", "generate_abstract"]:
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
        if mock_abstract and stage == abstract_stage:
            skip = True
        stages.append(stage)

    # _scripts targets
    design_config = Label("@@//" + native.package_name() + ":" + target_name + "_config.mk")
    for stage in stages:
        make_pattern = Label("//:" + stage + "-bazel.mk")
        stage_config = Label("@@//" + native.package_name() + ":" + target_name + "_" + stage + "_config.mk")

        # For synth use config with additional options required for GUI
        if stage == "synth":
            stage_config = Label("@@//" + native.package_name() + ":" + target_name + "_gui_" + stage + "_config.mk")
        make_targets = get_make_targets(stage, False, mock_area)
        local_entrypoint_cmd = get_entrypoint_cmd(make_pattern, design_config, stage_config, False, debug_prints = debug_prints)
        docker_entrypoint_cmd = get_entrypoint_cmd(
            make_pattern,
            design_config,
            stage_config,
            True,
            entrypoint = Label("//:docker_shell"),
            docker_image = docker_image,
            interactive = True,
            debug_prints = debug_prints,
        )
        target_name_stage = target_name + "_" + stage

        # Local flow scripts
        native.genrule(
            name = target_name_stage + "_make_local_script",
            tools = [Label("//:orfs")],
            srcs = [design_config, stage_config, make_pattern],
            cmd = "cat <<EOF > $@ \n#!/bin/bash\n" + local_entrypoint_cmd + " \\$$@\nEOF",
            tags = ["no-remote", "no-remote-cache"],
            outs = ["logs/%s/%s/%s/make_script_%s.sh" % (platform, out_dir, variant, stage)],
        )
        native.sh_binary(
            name = target_name_stage + "_local_make",
            srcs = ["//" + native.package_name() + ":" + target_name_stage + "_make_local_script"],
            tags = ["no-remote", "no-remote-cache"],
            data = [Label("//:orfs"), design_config, stage_config, make_pattern],
        )

        # Docker flow scripts
        native.genrule(
            name = target_name_stage + "_make_docker_script",
            tools = [Label("//:docker_shell")],
            srcs = [design_config, stage_config, make_pattern],
            cmd = "cat <<EOF > $@ \n#!/bin/bash\n" + docker_entrypoint_cmd + " \\$$@\nEOF",
            tags = ["no-remote", "no-remote-cache"],
            outs = ["logs/%s/%s/%s/make_docker_script_%s.sh" % (platform, out_dir, variant, stage)],
        )
        native.sh_binary(
            name = target_name_stage + "_docker",
            srcs = ["//" + native.package_name() + ":" + target_name_stage + "_make_docker_script"],
            tags = ["no-remote", "no-remote-cache"],
            data = [Label("//:docker_shell"), design_config, stage_config, make_pattern],
        )

        # Scripts target
        # Specifies additional dependencies to ensure _local_make and _docker are printed at the end
        native.filegroup(
            name = target_name_stage + "_scripts",
            srcs = [
                "//:out",
                target_name_stage + "_make_local_script",
                target_name_stage + "_make_docker_script",
                target_name_stage + "_local_make",
                target_name_stage + "_docker",
            ],
        )

    # Generate general config for design stage targets
    write_config(
        name = target_name + "_config",
        design_name = name,
        variant = variant,
        external_pdk = external_pdk,
    )

    if mock_area != None:
        mock_area_stages(target_name, name, stage_sources, io_constraints, sdc_constraints, stage_args, outs, variant, mock_area, docker_image, external_pdk)

    # _make targets
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
        design_config = Label("@@//" + native.package_name() + ":" + target_name + "_config.mk")
        stage_config = Label("@@//" + native.package_name() + ":" + target_name + "_" + stage + "_config.mk")
        make_targets = get_make_targets(stage, False, mock_area)

        if stage == "route":
            genrule = cpu_heavy_genrule
        else:
            genrule = native.genrule

        # Target building `target_name` `stage` and its dependencies
        genrule(
            name = target_name + "_" + stage,
            tools = select({
                "@bazel-orfs//:remote_exec": [Label("//:orfs")],
                "//conditions:default": [Label("//:docker_shell")],
            }),
            srcs = [make_pattern, design_config, stage_config] + stage_sources[stage] +
                   ([target_name + "_" + previous] if stage not in ("clock_period", "synth_sdc") else []) +
                   ([target_name + "_synth_sdc"] if stage == "floorplan" else []) +
                   ([target_name + "_generate_abstract_mock_area"] if mock_area != None and stage == "generate_abstract" else []),
            cmd = select({
                "@bazel-orfs//:remote_exec": "FLOW_HOME=/OpenROAD-flow-scripts/flow " + get_entrypoint_cmd(make_pattern, design_config, stage_config, False, make_targets, debug_prints = debug_prints, fmt_whitespace = " "),
                "//conditions:default": get_entrypoint_cmd(make_pattern, design_config, stage_config, True, make_targets, docker_image = docker_image, debug_prints = debug_prints, fmt_whitespace = " "),
            }),
            outs = outs.get(stage, []),
            tags = ["supports-graceful-termination"],
            visibility = visibility,
        )

        # Target building `target_name` `stage` dependencies and generating `stage` scripts
        native.filegroup(
            name = target_name + "_" + stage + "_make",
            srcs = stage_sources[stage] + ([target_name + "_" + previous] if stage not in ("clock_period", "synth_sdc") else []) +
                   ([target_name + "_generate_abstract_mock_area"] if mock_area != None and stage == "generate_abstract" else []) +
                   ([target_name + "_synth_sdc"] if stage == "floorplan" else []) +
                   [target_name + "_" + stage + "_scripts"],
        )

        # Prepare GUI targets
        if stage in ("synth", "floorplan", "place", "cts", "grt", "route", "final"):
            base_targets = [target_name + "_" + stage]
            if stage == "synth":
                write_stage_config(
                    name = target_name + "_gui_" + stage + "_config",
                    stage = stage,
                    srcs = stage_cfg_srcs,
                    stage_args = stage_args["synth"] + stage_args["synth_sdc"] + lefs_args,
                )
                base_targets.append(target_name + "_synth_sdc")
                base_targets.extend(macro_lef_targets)
            elif stage == "grt":
                base_targets.append(target_name + "_cts_gui")
            native.filegroup(
                name = target_name + "_" + stage + "_gui",
                srcs = macro_lib_targets + base_targets + [target_name + "_" + stage + "_scripts"],
            )
