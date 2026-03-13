"""Flow orchestration macros for OpenROAD-flow-scripts Bazel rules."""

load("//private:providers.bzl", "LoggingInfo")
load(
    "//private:rules.bzl",
    "ABSTRACT_IMPL",
    "FINAL_STAGE_IMPL",
    "GENERATE_METADATA_STAGE_IMPL",
    "STAGE_IMPLS",
    "TEST_STAGE_IMPL",
    "UPDATE_RULES_IMPL",
    "orfs_deps",
    "orfs_macro",
    "orfs_run",
    "orfs_synth_rule",
)
load("//private:stages.bzl", "get_sources", "get_stage_args")
load("//private:utils.bzl", "map_fn")

def _filter_stage_args(stage, **kwargs):
    """Filter and prepare the arguments for a specific stage."""

    def _args(**kwargs):
        return kwargs

    arguments = kwargs.pop("arguments", {})
    data = kwargs.pop("data", [])
    settings = kwargs.pop("settings", {})
    extra_configs = kwargs.pop("extra_configs", {})
    sources = kwargs.pop("sources", {})
    stage_arguments = kwargs.pop("stage_arguments", {})
    stage_sources = kwargs.pop("stage_sources", {})
    stage_data = kwargs.pop("stage_data", {})

    return _args(
        arguments = get_stage_args(
            stage,
            arguments = arguments,
            sources = sources,
            stage_arguments = stage_arguments,
        ),
        data = get_sources(stage, stage_sources, sources) +
               stage_data.get(stage, []) +
               data,
        extra_configs = extra_configs.get(stage, []),
        settings = get_stage_args(
            stage,
            arguments = settings,
        ),
        **kwargs
    )

def orfs_synth(**kwargs):
    return orfs_synth_rule(**_filter_stage_args("synth", **kwargs))

def _step_name(name, variant, stage):
    if variant:
        name += "_" + variant
    return name + "_" + stage

def _variant_name(variant, suffix):
    return "_".join([part for part in [variant, suffix] if part])

def orfs_flow(
        name,
        top = None,
        verilog_files = [],
        macros = [],
        sources = {},
        stage_sources = {},
        stage_arguments = {},
        renamed_inputs = {},
        arguments = {},
        extra_configs = {},
        abstract_stage = None,
        variant = None,
        mock_area = None,
        previous_stage = {},
        pdk = None,
        settings = {},
        stage_data = {},
        test_kwargs = {},
        **kwargs):
    """
    Creates targets for running physical design flow with OpenROAD-flow-scripts.

    Args:
      name: base name of bazel targets
      top: Verilog top level module name, default is 'name'
      verilog_files: list of verilog sources of the design
      macros: list of macros required to run physical design flow for this design
      sources: dictionary keyed by ORFS variables with lists of sources
      stage_sources: dictionary keyed by ORFS stages with lists of stage-specific sources
      stage_arguments: dictionary keyed by ORFS stages with lists of stage-specific arguments.
        Prefer 'arguments' which automatically assigns variables to the correct stages.
        Use stage_arguments only to override the automatic stage assignment.
      renamed_inputs: dictionary keyed by ORFS stages to rename inputs
      arguments: dictionary of additional arguments to the flow, automatically assigned to stages
      extra_configs: dictionary keyed by ORFS stages with list of additional configuration files
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      variant: name of the target variant, added right after the module name
      mock_area: floating point number, scale the die width/height by this amount, default no scaling
      previous_stage: a dictionary with the input for a stage, default is previous stage. Useful when running experiments that share preceeding stages, like share synthesis for floorplan variants.
      settings: dictionary with variable to BuildSettingInfo mappings
      pdk: name of the PDK to use, default is asap7
      stage_data: dictionary keyed by ORFS stages with lists of stage-specific data files
      test_kwargs: dictionary of arguments to pass to orfs_test
      **kwargs: forward named args
    """
    if variant == "base":
        variant = None
    if top == None:
        top = name
    abstract_variant = _variant_name(variant, "unmocked" if mock_area else None)
    _orfs_pass(
        name = name,
        top = top,
        verilog_files = verilog_files,
        macros = macros,
        sources = sources,
        stage_sources = stage_sources,
        stage_arguments = stage_arguments,
        renamed_inputs = renamed_inputs,
        arguments = arguments,
        extra_configs = extra_configs,
        abstract_stage = abstract_stage,
        variant = variant,
        abstract_variant = abstract_variant,
        previous_stage = previous_stage,
        pdk = pdk,
        stage_data = stage_data,
        settings = settings,
        test_kwargs = test_kwargs,
        **kwargs
    )

    if not mock_area:
        return

    mock_variant = _variant_name(variant, "mocked")
    mock_area_name = _step_name(name, mock_variant, "generate_area")
    mock_configs = {
        "floorplan": [mock_area_name],
    }

    _orfs_pass(
        name = name,
        top = top,
        verilog_files = verilog_files,
        macros = macros,
        sources = sources,
        stage_sources = stage_sources,
        stage_arguments = stage_arguments,
        renamed_inputs = {},
        arguments = arguments | {"SYNTH_GUT": "1"},
        extra_configs = extra_configs | mock_configs,
        abstract_stage = "place",
        variant = mock_variant,
        abstract_variant = None,
        previous_stage = {},
        pdk = pdk,
        stage_data = stage_data,
        mock_area = True,
        settings = settings,
        **kwargs
    )

    orfs_run(
        name = mock_area_name,
        src = _step_name(name, variant, "floorplan"),
        arguments = {
            "MOCK_AREA": str(mock_area),
            "OUTPUT": "{}.mk".format(mock_area_name),
        },
        outs = ["{}.mk".format(mock_area_name)],
        script = "@bazel-orfs//:mock_area.tcl",
        **kwargs
    )

    orfs_macro(
        name = _step_name(name, variant, ABSTRACT_IMPL.stage),
        lef = _step_name(name, mock_variant, ABSTRACT_IMPL.stage),
        lib = _step_name(name, abstract_variant, ABSTRACT_IMPL.stage),
        module_top = name,
        **kwargs
    )

def _kwargs(stage, **kwargs):
    return {k: v[stage] for k, v in kwargs.items() if stage in v and v[stage]}

def _update_rules_impl(ctx):
    script = ctx.actions.declare_file(ctx.attr.name + "_update.sh")

    ctx.actions.write(
        output = script,
        is_executable = True,
        content = """
#!/bin/bash
set -e
rules_json="{rules_json}"
logs="{logs}"
cp $logs $BUILD_WORKSPACE_DIRECTORY/$rules_json
""".format(
            rules_json = ctx.file.rules_json.path,
            logs = " ".join([log.short_path for log in ctx.files.logs]),
        ),
    )

    return [
        DefaultInfo(
            executable = script,
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    [],
                    transitive = [
                        depset(ctx.files.rules_json),
                        depset(ctx.files.logs),
                    ],
                ),
            ),
        ),
    ]

orfs_update = rule(
    implementation = _update_rules_impl,
    attrs = {
        "logs": attr.label_list(
            allow_files = True,
            providers = [LoggingInfo],
        ),
        "rules_json": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
    },
    executable = True,
)

def _add_manual(kwargs):
    """Adds manual arguments to the kwargs dictionary."""
    return kwargs | {"tags": kwargs.get("tags", ["manual"])}

def _orfs_pass(
        name,
        top,
        verilog_files,
        macros,
        sources,
        stage_sources,
        stage_arguments,
        renamed_inputs,
        arguments,
        extra_configs,
        abstract_stage,
        variant,
        abstract_variant,
        previous_stage,
        pdk,
        settings,
        stage_data,
        test_kwargs = {},
        mock_area = False,
        **kwargs):
    steps = []
    LEGAL_ABSTRACT_STAGES = ["place", "cts", "grt", "route", "final"]
    if abstract_stage != None and abstract_stage not in LEGAL_ABSTRACT_STAGES:
        fail(
            "Abstract stage {abstract_stage} must be one of: {legal}".format(
                abstract_stage = abstract_stage,
                legal = ", ".join(LEGAL_ABSTRACT_STAGES),
            ),
        )
    for step in STAGE_IMPLS:
        steps.append(step)
        if step.stage == abstract_stage:
            break
    steps.append(ABSTRACT_IMPL)

    # Prune stages unused due to previous_stage
    if len(previous_stage) > 1:
        fail("Maximum previous stages is 1")
    start_stage = 0
    if len(previous_stage) > 0:
        start_stage = map_fn(lambda x: x.stage, STAGE_IMPLS).index(
            previous_stage.keys()[0],
        )

    step_names = []
    if start_stage < 1:
        synth_step = steps[0]
        step_name = _step_name(name, variant, synth_step.stage)
        step_names.append(step_name)
        synth_step.impl(
            **_filter_stage_args(
                synth_step.stage,
                name = step_name,
                stage_arguments = stage_arguments,
                arguments = arguments,
                sources = sources,
                deps = macros,
                module_top = top,
                variant = variant,
                verilog_files = verilog_files,
                pdk = pdk,
                stage_sources = stage_sources,
                settings = settings,
                extra_configs = extra_configs,
                stage_data = stage_data,
                **kwargs
            )
        )
        orfs_deps(
            name = "{}_deps".format(_step_name(name, variant, synth_step.stage)),
            src = _step_name(name, variant, synth_step.stage),
            **_add_manual(kwargs)
        )

    if start_stage == 0:
        # implemented stage 0 above, so skip stage 0 below
        start_stage = 1

    def do_step(step, prev, kwargs, add_deps = True, more_kwargs = {}, data = []):
        stage_variant = (
            abstract_variant if step.stage == ABSTRACT_IMPL.stage and abstract_variant else variant
        )
        step_name = _step_name(name, stage_variant, step.stage)
        src = previous_stage.get(step.stage, _step_name(name, variant, prev.stage))
        step.impl(
            **_filter_stage_args(
                step.stage,
                name = step_name,
                stage_arguments = stage_arguments,
                arguments = arguments,
                sources = sources,
                stage_sources = stage_sources,
                settings = settings,
                extra_configs = extra_configs,
                src = src,
                variant = variant,
                stage_data = stage_data,
                data = data,
                **(
                    kwargs |
                    _kwargs(
                        step.stage,
                        renamed_inputs = renamed_inputs,
                    ) |
                    more_kwargs
                )
            )
        )
        if add_deps:
            orfs_deps(
                name = "{}_deps".format(step_name),
                src = step_name,
                **_add_manual(kwargs | more_kwargs)
            )
        return step_name

    for step, prev in zip(steps[start_stage:], steps[start_stage - 1:]):
        step_names.append(do_step(step, prev, kwargs))

    if FINAL_STAGE_IMPL in steps:
        do_step(
            GENERATE_METADATA_STAGE_IMPL,
            FINAL_STAGE_IMPL,
            data = [
                # Need 2_floorplan.sdc
                _step_name(name, variant, "floorplan"),
            ],
            kwargs = kwargs,
        )

        test_args = get_stage_args(
            TEST_STAGE_IMPL.stage,
            stage_arguments,
            arguments,
            sources,
        )
        if "RULES_JSON" in test_args and not mock_area:
            do_step(
                TEST_STAGE_IMPL,
                GENERATE_METADATA_STAGE_IMPL,
                add_deps = False,
                kwargs = kwargs | {"tags": []} | test_kwargs,
            )
            rules_name = do_step(
                UPDATE_RULES_IMPL,
                GENERATE_METADATA_STAGE_IMPL,
                kwargs = kwargs,
                more_kwargs = kwargs,
            )
            orfs_update(
                name = _step_name(name, variant, "update"),
                rules_json = sources["RULES_JSON"][0],
                logs = [rules_name],
                **kwargs
            )
