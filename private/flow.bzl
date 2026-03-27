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
    "orfs_squashed",
    "orfs_step",
    "orfs_synth_rule",
)
load("//private:stages.bzl", "STAGE_METADATA", "STAGE_SUBSTEPS", "get_sources", "get_stage_args")

def _strip_tool_kwargs(**kwargs):
    """Strip tool-specific kwargs for non-stage targets (orfs_macro, orfs_run)."""
    kwargs.pop("openroad", None)
    kwargs.pop("yosys", None)
    return kwargs

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

    # yosys attribute only applies to synth stage
    if stage != "synth":
        kwargs.pop("yosys", None)

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
        last_stage = None,
        variant = None,
        mock_area = None,
        previous_stage = {},
        pdk = None,
        settings = {},
        stage_data = {},
        test_kwargs = {},
        squash = False,
        substeps = False,
        add_deps = True,
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
      last_stage: string with the last stage to run, stops the flow early without generating an abstract. Mutually exclusive with abstract_stage. Useful for fast testing.
      variant: name of the target variant, added right after the module name
      mock_area: floating point number, scale the die width/height by this amount, default no scaling
      previous_stage: a dictionary with the input for a stage, default is previous stage. Useful when running experiments that share preceeding stages, like share synthesis for floorplan variants.
      settings: dictionary with variable to BuildSettingInfo mappings
      pdk: name of the PDK to use, default is asap7
      stage_data: dictionary keyed by ORFS stages with lists of stage-specific data files
      test_kwargs: dictionary of arguments to pass to orfs_test
      squash: if True, combine all stages after synthesis into a single Bazel action.
        Reduces artifact size by avoiding intermediate ODB checkpoints. Useful for
        stable designs like RAM macros where intermediate stages don't need inspection.
      substeps: if True, generate manual-tagged per-substep targets for
        debugging and fast iteration. Default is False to keep the target count low.
        Set to True for designs where substep-level debugging is needed.
      add_deps: if True, create *_deps targets for GUI debugging. Set to False
        for lightweight flows (lint/mock) to reduce target count.
      **kwargs: forward named args
    """
    if abstract_stage and last_stage:
        fail("abstract_stage and last_stage are mutually exclusive")
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
        last_stage = last_stage,
        variant = variant,
        abstract_variant = abstract_variant,
        previous_stage = previous_stage,
        pdk = pdk,
        stage_data = stage_data,
        settings = settings,
        test_kwargs = test_kwargs,
        squash = squash,
        substeps = substeps,
        add_deps = add_deps,
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
        **_strip_tool_kwargs(**kwargs)
    )

    orfs_macro(
        name = _step_name(name, variant, ABSTRACT_IMPL.stage),
        lef = _step_name(name, mock_variant, ABSTRACT_IMPL.stage),
        lib = _step_name(name, abstract_variant, ABSTRACT_IMPL.stage),
        module_top = name,
        **_strip_tool_kwargs(**kwargs)
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
        last_stage = None,
        test_kwargs = {},
        mock_area = False,
        squash = False,
        substeps = False,
        add_deps = True,
        **kwargs):
    ALL_STAGES = [step.stage for step in STAGE_IMPLS]
    steps = []
    LEGAL_ABSTRACT_STAGES = ["place", "cts", "grt", "route", "final"]
    if abstract_stage != None and abstract_stage not in LEGAL_ABSTRACT_STAGES:
        fail(
            "Abstract stage {abstract_stage} must be one of: {legal}".format(
                abstract_stage = abstract_stage,
                legal = ", ".join(LEGAL_ABSTRACT_STAGES),
            ),
        )
    if last_stage != None and last_stage not in ALL_STAGES:
        fail(
            "last_stage {last_stage} must be one of: {legal}".format(
                last_stage = last_stage,
                legal = ", ".join(ALL_STAGES),
            ),
        )

    # Determine which stage truncates the flow
    stop_stage = abstract_stage or last_stage
    for step in STAGE_IMPLS:
        steps.append(step)
        if step.stage == stop_stage:
            break

    # Only add abstract generation when abstract_stage is set (not last_stage)
    if abstract_stage or not last_stage:
        steps.append(ABSTRACT_IMPL)

    # Prune stages unused due to previous_stage
    if len(previous_stage) > 1:
        fail("Maximum previous stages is 1")
    start_stage = 0
    if len(previous_stage) > 0:
        start_stage = [x.stage for x in STAGE_IMPLS].index(
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
        if add_deps:
            orfs_deps(
                name = "{}_deps".format(_step_name(name, variant, synth_step.stage)),
                src = _step_name(name, variant, synth_step.stage),
                **_add_manual(kwargs)
            )

    if start_stage == 0:
        # implemented stage 0 above, so skip stage 0 below
        start_stage = 1

    # Squashed mode: combine all non-synth stages into a single Bazel action
    if squash:
        squash_steps = [s for s in steps[start_stage:] if s.stage in STAGE_METADATA]
        if squash_steps:
            last_step = squash_steps[-1]
            last_meta = STAGE_METADATA[last_step.stage]
            squash_name = _step_name(name, variant, last_step.stage)
            src = previous_stage.get(
                squash_steps[0].stage,
                _step_name(name, variant, steps[start_stage - 1].stage),
            )

            # Accumulate make targets, logs, jsons, reports, drcs from all stages
            all_make_targets = []
            all_log_names = []
            all_json_names = []
            all_report_names = []
            all_drc_names = []
            all_arguments = {}
            all_data = []
            all_extra_configs = []
            all_settings = {}
            for s in squash_steps:
                meta = STAGE_METADATA[s.stage]
                all_make_targets.extend(meta.make_targets)
                all_log_names.extend(meta.log_names)
                all_json_names.extend(meta.json_names)
                all_report_names.extend(meta.report_names)
                all_drc_names.extend(meta.drc_names)

                # Accumulate per-stage arguments (each call needs its own
                # copy of the dicts because _filter_stage_args pops keys).
                stage_filtered = _filter_stage_args(
                    s.stage,
                    stage_arguments = dict(stage_arguments),
                    arguments = dict(arguments),
                    sources = dict(sources),
                    stage_sources = dict(stage_sources),
                    settings = dict(settings),
                    extra_configs = dict(extra_configs),
                    stage_data = dict(stage_data),
                )
                all_arguments.update(stage_filtered.get("arguments", {}))
                for d in stage_filtered.get("data", []):
                    if d not in all_data:
                        all_data.append(d)
                for c in stage_filtered.get("extra_configs", []):
                    if c not in all_extra_configs:
                        all_extra_configs.append(c)
                all_settings.update(stage_filtered.get("settings", {}))

            orfs_squashed(
                name = squash_name,
                stage_name = last_meta.stage_name,
                make_targets = all_make_targets,
                log_names = all_log_names,
                json_names = all_json_names,
                report_names = all_report_names,
                result_names = last_meta.result_names,
                drc_names = all_drc_names,
                src = src,
                variant = variant,
                arguments = all_arguments,
                data = all_data,
                extra_configs = all_extra_configs,
                settings = all_settings,
                **kwargs
            )
            step_names.append(squash_name)
            if add_deps:
                orfs_deps(
                    name = "{}_deps".format(squash_name),
                    src = squash_name,
                    **_add_manual(kwargs)
                )

            # Generate substep targets for all squashed stages
            if substeps:
                for s in squash_steps:
                    stage_substeps = STAGE_SUBSTEPS.get(s.stage, [])
                    if len(stage_substeps) > 1:
                        for substep_name in stage_substeps:
                            orfs_step(
                                name = "{}_{}".format(squash_name, substep_name),
                                src = squash_name,
                                stage_name = substep_name,
                                deploy_name = "{}_deps".format(squash_name),
                                **_add_manual(kwargs)
                            )

            # Handle abstract generation for squashed flow
            if ABSTRACT_IMPL in steps:
                abstract_step_name = _step_name(
                    name,
                    abstract_variant if abstract_variant else variant,
                    ABSTRACT_IMPL.stage,
                )
                ABSTRACT_IMPL.impl(
                    **_filter_stage_args(
                        ABSTRACT_IMPL.stage,
                        name = abstract_step_name,
                        stage_arguments = stage_arguments,
                        arguments = arguments,
                        sources = sources,
                        stage_sources = stage_sources,
                        settings = settings,
                        extra_configs = extra_configs,
                        src = squash_name,
                        variant = variant,
                        stage_data = stage_data,
                        **kwargs
                    )
                )
                if add_deps:
                    orfs_deps(
                        name = "{}_deps".format(abstract_step_name),
                        src = abstract_step_name,
                        **_add_manual(kwargs)
                    )
            return

    def do_step(step, prev, kwargs, add_deps = add_deps, more_kwargs = {}, data = []):
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

            # Generate manual-tagged substep targets for stages with multiple substeps
            if substeps:
                stage_substeps = STAGE_SUBSTEPS.get(step.stage, [])
                if len(stage_substeps) > 1:
                    for substep_name in stage_substeps:
                        orfs_step(
                            name = "{}_{}".format(step_name, substep_name),
                            src = step_name,
                            stage_name = substep_name,
                            deploy_name = "{}_deps".format(step_name),
                            **_add_manual(kwargs)
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
