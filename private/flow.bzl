"""Flow orchestration macros for OpenROAD-flow-scripts Bazel rules."""

load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("//private:providers.bzl", "LoggingInfo")
load(
    "//private:rules.bzl",
    "ABSTRACT_IMPL",
    "FINAL_STAGE_IMPL",
    "GENERATE_METADATA_STAGE_IMPL",
    "STAGE_IMPLS",
    "TEST_STAGE_IMPL",
    "UPDATE_RULES_IMPL",
    "orfs_abstract_rule",
    "orfs_arguments",
    "orfs_cts_rule",
    "orfs_deploy_srcs",
    "orfs_final_rule",
    "orfs_floorplan_rule",
    "orfs_gds_rule",
    "orfs_generate_metadata_rule",
    "orfs_grt_rule",
    "orfs_macro",
    "orfs_place_rule",
    "orfs_route_rule",
    "orfs_run",
    "orfs_squashed",
    "orfs_synth_rule",
    "orfs_variables",
)
load(
    "//private:stages.bzl",
    "STAGE_METADATA",
    "check_stage_variables",
    "get_sources",
    "get_stage_args",
)

# Stages with an ODB that open.tcl can load for web_save_report.
_HTML_STAGES = ["floorplan", "place", "cts", "grt", "route", "final"]

def _strip_tool_kwargs(**kwargs):
    """Strip tool-specific kwargs for non-stage targets (orfs_macro, orfs_run)."""
    kwargs.pop("openroad", None)
    kwargs.pop("opensta", None)
    kwargs.pop("yosys", None)
    return kwargs

def _merge_extra_arguments(a, b):
    """Merge two {stage: [label, ...]} dicts, concatenating per-stage lists."""
    merged = dict(a)
    for stage, labels in b.items():
        merged[stage] = merged.get(stage, []) + labels
    return merged

def _filter_stage_args(stage, **kwargs):
    """Filter and prepare the arguments for a specific stage."""

    def _args(**kwargs):
        return kwargs

    arguments = kwargs.pop("arguments", {})
    data = kwargs.pop("data", [])
    extra_arguments = kwargs.pop("extra_arguments", {})
    extra_configs = kwargs.pop("extra_configs", {})
    sources = kwargs.pop("sources", {})
    stage_arguments = kwargs.pop("stage_arguments", {})
    stage_data = kwargs.pop("stage_data", {})
    user_arguments = kwargs.pop("user_arguments", {})
    user_sources = kwargs.pop("user_sources", {})

    # Validate before merging: the escape hatches are exempt from the
    # spell-check, so they cannot be folded in first.  See "The two escape
    # hatches" in private/stages.bzl.
    check_stage_variables(arguments, sources, user_arguments, user_sources)
    arguments = arguments | user_arguments
    sources = sources | user_sources

    # yosys attribute only applies to synth stage
    if stage != "synth":
        kwargs.pop("yosys", None)
        kwargs.pop("filter_script", None)

    # substeps attribute only applies to openroad stages, not synth
    if stage == "synth":
        kwargs.pop("substeps", None)

    # get_stage_args/get_sources take a LIST of stages (empty = no filtering);
    # a flow stage target filters by exactly one stage, so wrap [stage].
    return _args(
        arguments = get_stage_args(
            [stage],
            arguments = arguments,
            sources = sources,
            stage_arguments = stage_arguments,
        ),
        data = get_sources([stage], sources) +
               stage_data.get(stage, []) +
               data,
        extra_arguments = extra_arguments.get(stage, []),
        extra_configs = extra_configs.get(stage, []),
        **kwargs
    )

def _orfs_html_report(name, src, variant = None, openroad = None, visibility = None):
    """Emit an HTML timing report plus a runnable opener for a single stage.

    Creates {name}_gen (builds {name}_gen.html via OpenROAD's
    web_save_report with 1000 setup + 1000 hold paths; requires OpenROAD
    built with PR #10087) and {name} (sh_binary whose `bazel run` builds
    the .html and opens it in the default browser via xdg-open).

    Both targets are tagged "manual" so wildcard builds don't fail on
    OpenROAD builds that lack web_save_report.
    """
    gen_name = name + "_gen"
    run_kwargs = {}
    if openroad != None:
        run_kwargs["openroad"] = openroad
    if visibility != None:
        run_kwargs["visibility"] = visibility
    orfs_run(
        name = gen_name,
        src = src,
        outs = [gen_name + ".html"],
        arguments = {
            "GUI_TIMING": "1",
            "OUTPUT": gen_name + ".html",
        },
        script = "@bazel-orfs//:html_timing_report.tcl",
        variant = variant or "base",
        tags = ["manual"],
        **run_kwargs
    )
    sh_binary(
        name = name,
        srcs = ["@bazel-orfs//:open_html.sh"],
        args = ["$(rootpath :" + gen_name + ")"],
        data = [":" + gen_name],
        tags = ["manual"],
        visibility = visibility,
    )

def _create_deps_tar(stage_name, **kwargs):
    """Generate pkg_tar companion targets for a stage target.

    Creates:
      {stage_name}_deploy_srcs — thin rule exposing OrfsDepInfo.runfiles
      {stage_name}_deps — pkg_tar with include_runfiles=True

    Both targets are tagged "manual" so they are excluded from wildcard
    builds (bazel build //pkg:all) and only built when explicitly requested.
    """
    visibility = kwargs.get("visibility", None)
    orfs_deploy_srcs(
        name = stage_name + "_deps",
        src = ":" + stage_name,
        visibility = visibility,
        tags = ["manual"],
    )
    pkg_tar(
        name = stage_name + "_deps_tar",
        srcs = [":" + stage_name + "_deps"],
        extension = "tar.gz",
        include_runfiles = True,
        visibility = visibility,
        tags = ["manual"],
    )

def _orfs_stage(stage, impl, **kwargs):
    """Instantiates one stage target the way orfs_flow does.

    The whole point of the public stage macros: a standalone
    orfs_floorplan() gets exactly what a floorplan target inside an
    orfs_flow() gets — arguments/sources filtered to this stage,
    extra_arguments/extra_configs narrowed by stage key, the ORFS variable
    spell-check, the escape-hatch guard, and the companion _deps targets.

    Args:
        stage: canonical stage key, e.g. "floorplan".
        impl: the underlying *_rule for that stage.
        **kwargs: forwarded to _filter_stage_args and the rule.
    """
    impl(**_filter_stage_args(stage, **kwargs))
    _create_deps_tar(kwargs.get("name"), **kwargs)

def orfs_synth(**kwargs):
    """Instantiates a standalone synthesis stage target.

    Args:
        **kwargs: forwarded to _orfs_stage and orfs_synth_rule.
    """

    # Normalise the kept_macros sentinel: None / absent → feature off
    # (existing all-macros-to-all-partitions behaviour); any value
    # passed in (including {}) → enabled. The rule has two attrs to
    # encode this because attr.string_list_dict can't represent None.
    if "kept_macros" in kwargs:
        km = kwargs.pop("kept_macros")
        kwargs["kept_macros"] = km if km != None else {}
        kwargs["kept_macros_enabled"] = km != None
    _orfs_stage("synth", orfs_synth_rule, **kwargs)

# Public per-stage macros.  Written out one by one because Starlark has no
# nested def and no way to synthesise a function, so a loop over
# STAGE_IMPLS cannot produce them.  Each forwards to the rule that declares
# the matching `_stage` default — never to a rule whose stage has to be
# inferred, which _make_impl now rejects with a fail().
def orfs_floorplan(**kwargs):
    _orfs_stage("floorplan", orfs_floorplan_rule, **kwargs)

def orfs_place(**kwargs):
    _orfs_stage("place", orfs_place_rule, **kwargs)

def orfs_cts(**kwargs):
    _orfs_stage("cts", orfs_cts_rule, **kwargs)

def orfs_grt(**kwargs):
    _orfs_stage("grt", orfs_grt_rule, **kwargs)

def orfs_route(**kwargs):
    _orfs_stage("route", orfs_route_rule, **kwargs)

def orfs_final(**kwargs):
    _orfs_stage("final", orfs_final_rule, **kwargs)

# orfs_gds runs KLayout over the final stage's results, so it declares
# _stage = "final" — there is no "gds" key in ALL_STAGES_LIST.
def orfs_gds(**kwargs):
    _orfs_stage("final", orfs_gds_rule, **kwargs)

def orfs_abstract(**kwargs):
    _orfs_stage("generate_abstract", orfs_abstract_rule, **kwargs)

def orfs_generate_metadata(**kwargs):
    _orfs_stage("generate_metadata", orfs_generate_metadata_rule, **kwargs)

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
        kept_macros = None,
        canon_blackbox_macros = [],
        sources = {},
        user_sources = {},
        stage_arguments = {},
        renamed_inputs = {},
        arguments = {},
        user_arguments = {},
        extra_arguments = {},
        extra_configs = {},
        abstract_stage = None,
        last_stage = None,
        variant = None,
        mock_area = None,
        previous_stage = {},
        pdk = None,
        stage_data = {},
        test_kwargs = {},
        squash = False,
        substeps = False,
        save_odb = True,
        quick_pins = False,
        html = False,
        **kwargs):
    """
    Creates targets for running physical design flow with OpenROAD-flow-scripts.

    Args:
      name: base name of bazel targets
      top: Verilog top level module name, default is 'name'
      verilog_files: list of verilog sources of the design
      macros: list of macros required to run physical design flow for this design
      kept_macros: optional dict mapping kept-module name → list of macro short names
        the module instantiates (transitively, stopping at descendant kept modules).
        Default None disables the feature and preserves the existing behaviour where
        every parallel synth partition depends on every macro. Set to {} to opt into
        a pre-synth validation that prints the correct dict and errors out. Set to a
        non-empty dict to scope each partition's macro inputs — partitions that
        don't need a macro no longer wait on that macro's upstream PnR.
      canon_blackbox_macros: list of macro module names to blackbox during
        canonicalization via slang --blackboxed-module instead of reading their
        Verilog.
      sources: dictionary keyed by ORFS variables with lists of sources
      stage_arguments: dictionary keyed by ORFS stages with lists of stage-specific arguments.
        Prefer 'arguments' which automatically assigns variables to the correct stages.
        Use stage_arguments only to override the automatic stage assignment.
      renamed_inputs: dictionary keyed by ORFS stages to rename inputs
      arguments: dictionary of additional arguments to the flow, automatically assigned to stages
      user_arguments: dictionary of project-specific env vars to expose to every stage without
        validating against ORFS variables.yaml. Use for vars read only by user-supplied .tcl/.mk
        (e.g. ARRAY_COLS in a project's MACRO_PLACEMENT_TCL). Keys that collide with known ORFS
        variables are rejected — route those through 'arguments' instead.
      user_sources: dictionary of project-specific source-typed (path-label) env vars to expose
        to every stage without validating against ORFS variables.yaml. The path is still staged
        into the sandbox like a normal source — only the variable name skips the validator.
        Use for path hooks read only by user-supplied .tcl/.mk (e.g. an extra-SDC hook
        source'd from the design's own io.tcl). Keys that collide with known ORFS variables
        are rejected — route those through 'sources' instead.
      extra_arguments: dictionary keyed by ORFS stages with lists of .json argument file labels.
        These .json files are merged into the stage config, providing computed arguments
        that flow through OrfsInfo to subsequent stages.
      extra_configs: dictionary keyed by ORFS stages with list of additional configuration files
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      last_stage: string with the last stage to run, stops the flow early without generating an abstract. Mutually exclusive with abstract_stage. Useful for fast testing.
      variant: name of the target variant, added right after the module name
      mock_area: floating point number, scale the die width/height by this amount, default no scaling
      previous_stage: a dictionary with the input for a stage, default is previous stage. Useful when running experiments that share preceeding stages, like share synthesis for floorplan variants.
      pdk: name of the PDK to use, default is asap7
      stage_data: dictionary keyed by ORFS stages with lists of stage-specific data files
      test_kwargs: dictionary of arguments to pass to orfs_test
      squash: if True, combine all stages after synthesis into a single Bazel action.
        Reduces artifact size by avoiding intermediate ODB checkpoints. Useful for
        stable designs like RAM macros where intermediate stages don't need inspection.
      substeps: if True, capture intermediate substep .odb files as additional
        action outputs in per-substep output groups. Enables shared cache of
        substep intermediates for debugging via //:deps. Default False to
        control cache budget -- enable for designs under active development.
      save_odb: if False, skip synth_odb generation. Needed when SYNTH_BLACKBOXES
        includes modules without LEF masters. Default True.
      html: if True, emit per-stage runnable HTML timing report targets
        `<name>[_<variant>]_<stage>_html`. `bazel run` builds the report
        and opens it in the default browser via xdg-open. The report uses
        OpenROAD's web_save_report command (PR #10087) with 1000 setup
        and 1000 hold paths. Targets are tagged "manual". Default False.
      quick_pins: if True, skip `global_placement -skip_io` and place pins
        directly via PRE_GLOBAL_PLACE_SKIP_IO_TCL. Trades suboptimal pin
        placement for a large wall-time saving on the GP-skip-io step on
        big designs. Suitable for RTL exploration; not for tape-out.
        Default False.
      **kwargs: forward named args
    """
    if quick_pins:
        sources = sources | {
            "PRE_GLOBAL_PLACE_SKIP_IO_TCL": ["@bazel-orfs//:quick_pins.tcl"],
            "FOOTPRINT_TCL": ["@bazel-orfs//:quick_pins_footprint_stub.tcl"],
        }

    # Validated per-stage by _filter_stage_args via check_stage_variables(),
    # the same guard a bare orfs_floorplan() gets.  Validate here too so a
    # typo in a flow that instantiates no stage (last_stage past its own
    # start) still fails loudly.
    check_stage_variables(arguments, sources, user_arguments, user_sources)
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
        kept_macros = kept_macros,
        canon_blackbox_macros = canon_blackbox_macros,
        sources = sources,
        user_sources = user_sources,
        stage_arguments = stage_arguments,
        renamed_inputs = renamed_inputs,
        arguments = arguments,
        user_arguments = user_arguments,
        extra_arguments = extra_arguments,
        extra_configs = extra_configs,
        abstract_stage = abstract_stage,
        last_stage = last_stage,
        variant = variant,
        abstract_variant = abstract_variant,
        previous_stage = previous_stage,
        pdk = pdk,
        stage_data = stage_data,
        test_kwargs = test_kwargs,
        squash = squash,
        substeps = substeps,
        save_odb = save_odb,
        html = html,
        **kwargs
    )

    orfs_variables(
        name = _step_name(name, variant, "variables"),
        arguments = arguments | user_arguments,
        data = depset(
            kwargs.get("data", []) +
            [v for vs in (sources | user_sources).values() for v in vs] +
            [v for vs in sources.values() for v in vs],
        ).to_list(),
    )

    if not mock_area:
        return

    mock_variant = _variant_name(variant, "mocked")
    mock_area_name = _step_name(name, mock_variant, "generate_area")
    mock_extra_arguments = {
        "floorplan": [mock_area_name],
    }

    _orfs_pass(
        name = name,
        top = top,
        verilog_files = verilog_files,
        macros = macros,
        kept_macros = kept_macros,
        canon_blackbox_macros = canon_blackbox_macros,
        sources = sources,
        user_sources = user_sources,
        stage_arguments = stage_arguments,
        renamed_inputs = {},
        arguments = arguments | {"SYNTH_GUT": "1"},
        user_arguments = user_arguments,
        extra_arguments = _merge_extra_arguments(extra_arguments, mock_extra_arguments),
        extra_configs = extra_configs,
        abstract_stage = "place",
        variant = mock_variant,
        abstract_variant = None,
        previous_stage = {},
        pdk = pdk,
        stage_data = stage_data,
        mock_area = True,
        html = html,
        **kwargs
    )
    orfs_arguments(
        name = mock_area_name,
        src = _step_name(name, variant, "floorplan"),
        arguments = {"MOCK_AREA": str(mock_area)},
        script = "@bazel-orfs//:mock_area.tcl",
        variant = variant or "base",
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
            # The update_rules stage's DefaultInfo carries rules.json plus
            # bookkeeping files (update_rules.args.mk); only rules.json may
            # be copied — cp with several sources needs a directory target.
            logs = " ".join([
                log.short_path
                for log in ctx.files.logs
                if log.basename == "rules.json"
            ]),
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

def _orfs_pass(
        name,
        top,
        verilog_files,
        macros,
        sources,
        stage_arguments,
        renamed_inputs,
        arguments,
        user_arguments,
        user_sources,
        extra_arguments,
        extra_configs,
        abstract_stage,
        variant,
        abstract_variant,
        previous_stage,
        pdk,
        stage_data,
        kept_macros = None,
        canon_blackbox_macros = [],
        last_stage = None,
        test_kwargs = {},
        mock_area = False,
        squash = False,
        save_odb = True,
        html = False,
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

    # Post-synth stages consume the previous stage's written .odb/.sdc
    # (for floorplan, the canonicalized 1_synth.odb/.sdc) — never the raw
    # SDC_FILE. save_odb = False generates neither, so a flow that
    # continues past synth would fail obscurely at floorplan; fail loudly
    # here instead.
    if not save_odb and len(steps) > 1:
        fail(
            "save_odb = False generates no 1_synth.odb/.sdc, but this " +
            "flow has post-synth stages ({stages}) that consume them. " +
            "Set last_stage = 'synth' or drop save_odb = False.".format(
                stages = ", ".join([s.stage for s in steps[1:]]),
            ),
        )

    # Prune stages unused due to previous_stage
    if len(previous_stage) > 1:
        fail("Maximum previous stages is 1")
    start_stage = 0
    if len(previous_stage) > 0:
        start_stage = [x.stage for x in STAGE_IMPLS].index(
            previous_stage.keys()[0],
        )

    step_names = []
    synth_target = None
    if start_stage < 1:
        synth_step = steps[0]
        step_name = _step_name(name, variant, synth_step.stage)
        synth_target = step_name
        step_names.append(step_name)
        synth_step.impl(
            **_filter_stage_args(
                synth_step.stage,
                name = step_name,
                stage_arguments = stage_arguments,
                arguments = arguments,
                user_arguments = user_arguments,
                sources = sources,
                user_sources = user_sources,
                deps = macros,
                kept_macros = kept_macros if kept_macros != None else {},
                kept_macros_enabled = kept_macros != None,
                canon_blackbox_macros = canon_blackbox_macros,
                module_top = top,
                variant = variant,
                verilog_files = verilog_files,
                pdk = pdk,
                extra_arguments = extra_arguments,
                extra_configs = extra_configs,
                stage_data = stage_data,
                save_odb = save_odb,
                **kwargs
            )
        )
        _create_deps_tar(step_name, **kwargs)
        if html:
            _orfs_html_report(
                name = step_name + "_html",
                src = step_name,
                variant = variant,
                openroad = kwargs.get("openroad"),
                visibility = kwargs.get("visibility"),
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
            all_extra_arguments = []
            all_extra_configs = []
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
                    user_arguments = dict(user_arguments),
                    sources = dict(sources),
                    user_sources = dict(user_sources),
                    extra_arguments = dict(extra_arguments),
                    extra_configs = dict(extra_configs),
                    stage_data = dict(stage_data),
                )
                all_arguments.update(stage_filtered.get("arguments", {}))
                for d in stage_filtered.get("data", []):
                    if d not in all_data:
                        all_data.append(d)
                for ea in stage_filtered.get("extra_arguments", []):
                    if ea not in all_extra_arguments:
                        all_extra_arguments.append(ea)
                for c in stage_filtered.get("extra_configs", []):
                    if c not in all_extra_configs:
                        all_extra_configs.append(c)

            orfs_squashed(
                name = squash_name,
                stage_name = last_meta.stage_name,
                stages = [s.stage for s in squash_steps],
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
                extra_arguments = all_extra_arguments,
                extra_configs = all_extra_configs,
                **kwargs
            )
            step_names.append(squash_name)
            _create_deps_tar(squash_name, **kwargs)
            if html:
                _orfs_html_report(
                    name = squash_name + "_html",
                    src = squash_name,
                    variant = variant,
                    openroad = kwargs.get("openroad"),
                    visibility = kwargs.get("visibility"),
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
                        user_arguments = user_arguments,
                        sources = sources,
                        user_sources = user_sources,
                        extra_arguments = extra_arguments,
                        extra_configs = extra_configs,
                        src = squash_name,
                        variant = variant,
                        stage_data = stage_data,
                        **kwargs
                    )
                )
            return

    def do_step(step, prev, kwargs, more_kwargs = {}, data = [], variant_override = None, src = None):
        stage_variant = variant_override or (
            abstract_variant if step.stage == ABSTRACT_IMPL.stage and abstract_variant else variant
        )
        step_name = _step_name(name, stage_variant, step.stage)
        if src == None:
            src = previous_stage.get(step.stage, _step_name(name, variant, prev.stage))
        step.impl(
            **_filter_stage_args(
                step.stage,
                name = step_name,
                stage_arguments = stage_arguments,
                arguments = arguments,
                user_arguments = user_arguments,
                sources = sources,
                user_sources = user_sources,
                extra_arguments = extra_arguments,
                extra_configs = extra_configs,
                src = src,
                variant = variant_override or variant,
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
        return step_name

    def _place_target_label():
        """Label of this flow's place stage (local or previous_stage), or None.

        Only considers stages actually instantiated in this flow — if the
        flow starts past place via `previous_stage`, the local place target
        does not exist.
        """
        if "place" in previous_stage:
            return previous_stage["place"]
        for s in steps[start_stage:]:
            if s.stage == "place":
                return _step_name(name, variant, "place")
        return None

    def _emit_pre_layout_abstract():
        """Emit a sibling abstract target fed from the post-place .odb.

        Returns the bare target name (callers prefix with ':' for label use)
        or None if no place target is available in this flow.
        """
        place_src = _place_target_label()
        if not place_src:
            return None
        base_variant = abstract_variant if abstract_variant else variant
        pre_layout_variant = _variant_name(base_variant, "pre_layout")
        pre_layout_name = _step_name(
            name,
            pre_layout_variant,
            "generate_abstract",
        )
        ABSTRACT_IMPL.impl(
            **_filter_stage_args(
                ABSTRACT_IMPL.stage,
                name = pre_layout_name,
                stage_arguments = stage_arguments,
                arguments = arguments,
                user_arguments = user_arguments,
                sources = sources,
                user_sources = user_sources,
                extra_arguments = extra_arguments,
                extra_configs = extra_configs,
                src = place_src,
                variant = pre_layout_variant,
                stage_data = stage_data,
                **(
                    kwargs |
                    _kwargs(ABSTRACT_IMPL.stage, renamed_inputs = renamed_inputs)
                )
            )
        )
        _create_deps_tar(pre_layout_name, **kwargs)
        return pre_layout_name

    for step, prev in zip(steps[start_stage:], steps[start_stage - 1:]):
        more_kwargs = {}

        # When the abstract runs past place, also emit a sibling abstract at
        # post-place so parent flows can feed ideal-clock .lib to their
        # synth/floorplan/place and the canonical propagated one from CTS on.
        if step == ABSTRACT_IMPL and abstract_stage and abstract_stage != "place":
            pre_layout_name = _emit_pre_layout_abstract()
            if pre_layout_name:
                more_kwargs = {"pre_layout_abstract": ":" + pre_layout_name}

        sn = do_step(step, prev, kwargs, more_kwargs = more_kwargs)
        step_names.append(sn)
        _create_deps_tar(sn, **kwargs)
        if html and step.stage in _HTML_STAGES:
            _orfs_html_report(
                name = sn + "_html",
                src = sn,
                variant = variant,
                openroad = kwargs.get("openroad"),
                visibility = kwargs.get("visibility"),
            )
    if FINAL_STAGE_IMPL in steps:
        do_step(
            GENERATE_METADATA_STAGE_IMPL,
            FINAL_STAGE_IMPL,
            data = [
                # Need 2_floorplan.sdc
                _step_name(name, variant, "floorplan"),
                # Need 1_2_yosys.v for `synth__netlist__hash` and any
                # other genMetrics.py field that reads synth results
                # past the canonicalize RTLIL.  Only canonicalize is
                # threaded through `forwarded_names = [CANON_OUTPUT]`
                # along the floorplan→cts chain; the post-ABC netlist
                # is not.  Pulling synth's outputs in via `data =`
                # gives metadata access without touching every stage.
                _step_name(name, variant, "synth"),
            ],
            kwargs = kwargs,
        )

        test_args = get_stage_args(
            [TEST_STAGE_IMPL.stage],
            stage_arguments,
            arguments,
            sources,
        )
        if "RULES_JSON" in test_args and not mock_area:
            do_step(
                TEST_STAGE_IMPL,
                GENERATE_METADATA_STAGE_IMPL,
                kwargs = kwargs | {"tags": []} | test_kwargs,
            )
            rules_name = do_step(
                UPDATE_RULES_IMPL,
                GENERATE_METADATA_STAGE_IMPL,
                kwargs = kwargs,
                more_kwargs = kwargs,
            )
            update_kwargs = dict(kwargs)
            update_kwargs.pop("substeps", None)
            update_kwargs.pop("lint", None)
            orfs_update(
                name = _step_name(name, variant, "update"),
                rules_json = sources["RULES_JSON"][0],
                logs = [rules_name],
                **_strip_tool_kwargs(**update_kwargs)
            )

    # Fast synthesis-stage QoR pre-check: any flow that runs its own synth
    # stage and has RULES_JSON also gets <synth>_generate_metadata (a
    # metadata.json built from the synth stage alone — genMetrics.py
    # tolerates a synthesis-only tree) and <synth>_test, which gates it
    # with `make metadata-check-synth`: only the synth__/constraints__
    # subset of the same rules file the full-flow test checks. It shares
    # the flow's synth action, so it is a minutes-scale proxy for the
    # full-flow test — same rules, same checker, subset of the fields.
    # QoR only: without LEC it says nothing about functional correctness,
    # so the full-flow test remains the real gate.
    #
    # The pair lives in its own "<variant>_synth" sub-variant so its
    # metadata.json and config artifacts cannot collide with the
    # full-flow chain's (both would otherwise be declared under the same
    # variant-scoped paths). The synth inputs staged under the parent
    # variant's tree are remapped by the stage's cross-variant renaming
    # (rename_data on orfs_generate_metadata).
    if synth_target != None and not mock_area:
        test_args = get_stage_args(
            [TEST_STAGE_IMPL.stage],
            stage_arguments,
            arguments,
            sources,
        )
        if "RULES_JSON" in test_args:
            fast_variant = _variant_name(variant, "synth")
            fast_metadata_name = do_step(
                GENERATE_METADATA_STAGE_IMPL,
                steps[0],
                data = [
                    # Stage synth's logs (1_synth.log, 1_synth.json) via
                    # data_runfiles; source_inputs deliberately omits
                    # LoggingInfo.logs, and genMetrics.py reads both.
                    synth_target,
                ],
                kwargs = kwargs,
                variant_override = fast_variant,
                src = synth_target,
            )
            do_step(
                TEST_STAGE_IMPL,
                GENERATE_METADATA_STAGE_IMPL,
                kwargs = kwargs | {"tags": []} | test_kwargs,
                more_kwargs = {"cmd": "metadata-check-synth"},
                variant_override = fast_variant,
                src = fast_metadata_name,
            )
