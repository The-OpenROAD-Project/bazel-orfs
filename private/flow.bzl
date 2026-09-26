"""Flow orchestration macros for OpenROAD-flow-scripts Bazel rules."""

load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load(
    "//private:rules.bzl",
    "ABSTRACT_IMPL",
    "FINAL_STAGE_IMPL",
    "GENERATE_METADATA_STAGE_IMPL",
    "STAGE_IMPLS",
    "create_deps_tar",
    "orfs_abstract_rule",
    "orfs_arguments",
    "orfs_cts_rule",
    "orfs_final_rule",
    "orfs_floorplan_rule",
    "orfs_gds_rule",
    "orfs_generate_metadata_rule",
    "orfs_grt_rule",
    "orfs_macro",
    "orfs_place_rule",
    "orfs_route_rule",
    "orfs_run",
    "orfs_run_executable",
    "orfs_squashed",
    "orfs_synth_rule",
    "orfs_variables",
)
load(
    "//private:stages.bzl",
    "ALL_STAGES_LIST",
    "STAGE_METADATA",
    "check_stage_variables",
    "check_user_stages",
    "get_sources",
    "get_stage_args",
)

# Stages with an ODB that open.tcl can load for web_save_report.
_HTML_STAGES = ["floorplan", "place", "cts", "grt", "route", "final"]

# Read only by mock_area.tcl and mock_pins.tcl, for the mocked variant.
MOCK_PIN_VARIABLES = ("MOCK_AREA_PIN_EDGES", "MOCK_AREA_PIN_MARGIN")

def _strip_tool_kwargs(**kwargs):
    """Strip stage-only kwargs for non-stage targets (orfs_macro, orfs_arguments).

    The tools, and user_stages: the variable scoping is a stage attribute,
    and a flow declared with it (every BLOCKS= flow of a design that names
    its knobs' stages) also declares these companions.
    """
    kwargs.pop("openroad", None)
    kwargs.pop("opensta", None)
    kwargs.pop("yosys", None)
    kwargs.pop("user_stages", None)
    return kwargs

def slang_arguments(macro, name, arguments, yosys_frontend_reason):
    """The synthesis frontend is slang, for every entry point that synthesises.

    yosys's own Verilog frontend is effectively deprecated for
    SystemVerilog and parses at a few MB/s -- XiangShan's flat core costs
    seven minutes of canonicalization on it against one on slang -- and a
    design that never named a frontend got yosys's, by ORFS's default.
    Here the default is slang, and a design that must stay on another
    frontend says why in yosys_frontend_reason, next to the setting, so
    the exception is visible where it is made.

    Applied by orfs_flow() and by orfs_synth(), the two public entry
    points that run synthesis, so the frontend does not depend on which
    macro declared the design. SYNTH_USE_SYN bypasses yosys altogether
    and is exempt.

    Args:
        macro: the macro's name, for the message.
        name: the target's name, for the message.
        arguments: the flow's arguments dict.
        yosys_frontend_reason: the caller's stated reason, or None.

    Returns:
        arguments, with SYNTH_HDL_FRONTEND set.
    """
    if arguments.get("SYNTH_USE_SYN") == "1":
        return arguments
    frontend = arguments.get("SYNTH_HDL_FRONTEND", "slang")
    if frontend != "slang" and not yosys_frontend_reason:
        fail(("{} {}: SYNTH_HDL_FRONTEND is \"{}\", not \"slang\". bazel-orfs " +
              "synthesises with slang; a design that must use another frontend " +
              "passes yosys_frontend_reason = \"<why>\" alongside the setting.").format(
            macro,
            name,
            frontend,
        ))
    return arguments | {"SYNTH_HDL_FRONTEND": frontend}

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

    # A `data` in kwargs here is PER-STAGE (an internal caller wiring one
    # stage's own inputs, e.g. generate_metadata's stage-target deps) and
    # passes through as the stage rule's data attr. The flow-level
    # fan-out — one dict concatenated into every stage — is rejected in
    # orfs_flow() itself; use stage_data= there instead.
    data = kwargs.pop("data", [])
    extra_arguments = kwargs.pop("extra_arguments", {})
    extra_configs = kwargs.pop("extra_configs", {})
    sources = kwargs.pop("sources", {})
    stage_arguments = kwargs.pop("stage_arguments", {})
    stage_data = kwargs.pop("stage_data", {})
    user_arguments = kwargs.pop("user_arguments", {})
    user_sources = kwargs.pop("user_sources", {})
    user_stages = kwargs.pop("user_stages", {})

    # Validate before merging: the escape hatches are exempt from the
    # spell-check, so they cannot be folded in first.  See "The two escape
    # hatches" in private/stages.bzl.
    check_stage_variables(arguments, sources, user_arguments, user_sources)
    check_user_stages(user_stages, user_arguments, user_sources)
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
    own = get_stage_args(
        [stage],
        arguments = arguments,
        sources = sources,
        stage_arguments = stage_arguments,
        user_stages = user_stages,
    )

    # What the stages after this one are configured with, for a deployed
    # tree of this stage run under ORFS_DEPLOY_ANY_STAGE=1. A tree carries
    # one stage's variables (docs/local-flow.md, the fence), so a later
    # stage run there otherwise silently takes the platform's defaults:
    # a study measured M7 and a 0.25 layer adjustment for a week because
    # of it. Only literal values travel. A value naming a file resolves
    # against the build's paths, and one produced by an earlier stage does
    # not exist until that stage runs, which is why the tree cannot simply
    # carry the union.
    later = ALL_STAGES_LIST[ALL_STAGES_LIST.index(stage) + 1:] if stage in ALL_STAGES_LIST else []
    later_args = {
        k: v
        for k, v in get_stage_args(
            later,
            arguments = arguments,
            stage_arguments = stage_arguments,
            user_stages = user_stages,
        ).items()
        if k not in own and "$(" not in v and "\n" not in v
    } if later else {}

    return _args(
        arguments = own,
        later_stage_arguments = later_args,
        data = get_sources([stage], sources, user_stages = user_stages) +
               stage_data.get(stage, []) +
               data,
        extra_arguments = extra_arguments.get(stage, []),
        extra_configs = extra_configs.get(stage, []),
        **kwargs
    )

def _orfs_estimate_report(name, src, arguments = {}, sources = {}, variant = None, openroad = None, visibility = None):
    """Emit the fast estimate oracle for a flow's synthesis output.

    Creates {name} (an orfs_run producing {name}.json): a deterministic,
    ~one-to-two-minute estimate of what the design can achieve at a
    given set of floorplan parameters -- the floorplan is built
    in-script from the same variables the production stage reads, so
    one estimate is one point in floorplan-parameter space. Also
    creates {name}_run (an orfs_run_executable): the same script with
    run-time KEY=VALUE parameter overrides, one Pareto point per
    invocation. Estimated achievable clock period is pre-route
    optimistic, for differential and ranking use where the bias
    cancels. Parallel to the entire physical flow by DAG construction;
    cannot perturb flow artifacts. Thesis, the division of labor with
    ORFS's config.mk pin machinery, calibration and limits:
    docs/estimate.md.
    """
    run_kwargs = {}
    if openroad != None:
        run_kwargs["openroad"] = openroad
    if visibility != None:
        run_kwargs["visibility"] = visibility

    # The oracle is a diagnostic, not part of anyone's build: a wildcard
    # pattern that swept it up would run place_pins on whatever die the
    # flow's variables imply, which fails outright for a mocked macro whose
    # stub die cannot hold the module's ports.
    run_kwargs["tags"] = ["manual"]
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".json"],
        arguments = arguments,
        script = "@bazel-orfs//:estimate.tcl",
        sources = sources,
        # Read by estimate.tcl, not by ORFS.
        user_arguments = {
            "OUTPUT": name + ".json",
        },
        stages = [
            "synth",
            "floorplan",
            "place",
        ],
        variant = variant or "base",
        **run_kwargs
    )
    orfs_run_executable(
        name = name + "_run",
        src = src,
        arguments = arguments,
        script = "@bazel-orfs//:estimate.tcl",
        sources = sources,
        # Read by estimate.tcl, not by ORFS.
        user_arguments = {
            "OUTPUT": name + ".json",
        },
        stages = [
            "synth",
            "floorplan",
            "place",
        ],
        variant = variant or "base",
        **run_kwargs
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
        },
        script = "@bazel-orfs//:html_timing_report.tcl",
        # Read by html_timing_report.tcl, not by ORFS.
        user_arguments = {
            "OUTPUT": gen_name + ".html",
        },
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
    create_deps_tar(kwargs.get("name"), kwargs.get("visibility", None))

def orfs_synth(**kwargs):
    """Instantiates a standalone synthesis stage target.

    Args:
        **kwargs: forwarded to _orfs_stage and orfs_synth_rule, plus
            yosys_frontend_reason, which is consumed here: why this
            target does not synthesise with slang, when
            SYNTH_HDL_FRONTEND names another frontend. Same rule and
            same wording as orfs_flow().
    """

    # Normalise the kept_macros sentinel: None / absent → feature off
    # (existing all-macros-to-all-partitions behaviour); any value
    # passed in (including {}) → enabled. The rule has two attrs to
    # encode this because attr.string_list_dict can't represent None.
    if "kept_macros" in kwargs:
        km = kwargs.pop("kept_macros")
        kwargs["kept_macros"] = km if km != None else {}
        kwargs["kept_macros_enabled"] = km != None

    # A standalone synth stage is synthesis too, so it takes the same
    # frontend an orfs_flow() would give it. yosys_frontend_reason is a
    # macro argument, not an attribute of the rule, so it is popped here.
    kwargs["arguments"] = slang_arguments(
        "orfs_synth",
        kwargs.get("name"),
        kwargs.get("arguments", {}),
        kwargs.pop("yosys_frontend_reason", None),
    )
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
        yosys_frontend_reason = None,
        extra_configs = {},
        abstract_stage = None,
        last_stage = None,
        variant = None,
        mock_area = None,
        previous_stage = {},
        pdk = None,
        stage_data = {},
        squash = False,
        substeps = False,
        save_odb = True,
        quick_pins = False,
        html = False,
        **kwargs):
    # buildifier: disable=function-docstring-args
    #
    # user_stages is documented below but stays in **kwargs on purpose.
    # It has to arrive at _strip_tool_kwargs still inside the kwargs
    # dict, because that function is the single place that decides which
    # non-stage companions (orfs_arguments, orfs_macro) must
    # not see it -- an attribute none of those rules has. Lifting it into
    # the signature would take it out of that dict and put the decision
    # back at each call site, which is the shape that failed at analysis
    # for every design with both user_stages and a mock_area.
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
      user_stages: additive sidecar scoping user_arguments/user_sources variables to the
        stages that read them, e.g. {"MY_HOOK": ["floorplan"]}. Unlisted user variables keep
        the default kept-in-every-stage behavior. Scoping a user source stops its file edits
        from re-running stages that never read it. (Passed via **kwargs.)
      extra_arguments: dictionary keyed by ORFS stages with lists of .json argument file labels.
        These .json files are merged into the stage config, providing computed arguments
        that flow through OrfsInfo to subsequent stages.
      yosys_frontend_reason: why this flow does not synthesise with slang, when
        SYNTH_HDL_FRONTEND is set to another frontend. Without it the flow
        is refused: bazel-orfs forces slang.
      extra_configs: dictionary keyed by ORFS stages with list of additional configuration files
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      last_stage: string with the last stage to run, stops the flow early without generating an abstract. Mutually exclusive with abstract_stage. Useful for fast testing.
      variant: name of the target variant, added right after the module name
      mock_area: floating point number, scale the die width/height by this amount, default no scaling.
        "pins" fits the mocked die to the block's pins instead (mock_area.tcl): the smallest
        square whose MOCK_AREA_PIN_EDGES adjacent edges (default 2, see mock_pins.tcl) hold every
        pin at place_pins' spacing, times MOCK_AREA_PIN_MARGIN (default 1.5), never larger than
        the real die. Those two knobs reach the mocked variant only.
      previous_stage: a dictionary with the input for a stage, default is previous stage. Useful when running experiments that share preceeding stages, like share synthesis for floorplan variants.
      pdk: name of the PDK to use, default is asap7
      stage_data: dictionary keyed by ORFS stages with lists of stage-specific data files
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

    arguments = slang_arguments("orfs_flow", name, arguments, yosys_frontend_reason)

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
    check_user_stages(kwargs.get("user_stages", {}), user_arguments, user_sources)
    if "data" in kwargs:
        fail(
            "orfs_flow(data = ...) fans the files out to every stage — " +
            "any edit re-runs the whole flow. Use " +
            'stage_data = {"<stage>": [...]} to scope them to the ' +
            "stage(s) that read them.",
        )
    if abstract_stage and last_stage:
        fail("abstract_stage and last_stage are mutually exclusive")
    if variant == "base":
        variant = None
    if top == None:
        top = name

    # The mock pin knobs size and constrain the mocked variant only. The
    # real flow never reads them, and carrying them in its arguments made
    # every block re-floorplan when a parent changed the mock margin.
    mock_pin_arguments = {k: v for k, v in arguments.items() if k in MOCK_PIN_VARIABLES}
    arguments = {k: v for k, v in arguments.items() if k not in MOCK_PIN_VARIABLES}

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
        squash = squash,
        substeps = substeps,
        save_odb = save_odb,
        html = html,
        **kwargs
    )

    orfs_variables(
        name = _step_name(name, variant, "variables"),
        # Same tags as the flow it describes. Without this a manual flow
        # still emits a non-manual sidecar, so a wildcard build picks up
        # the one target of a design that was deliberately opted out.
        tags = kwargs.get("tags", []),
        arguments = arguments | user_arguments,
        data = depset(
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

    # A pin-fitted mock puts its pins on adjacent edges (mock_pins.tcl), so
    # the parent's placer has an orientation to choose; the block's own IO
    # constraints, written for its real outline, do not apply to the mock.
    mock_sources = sources
    if mock_area == "pins":
        mock_sources = sources | {"IO_CONSTRAINTS": ["@bazel-orfs//:mock_pins.tcl"]}
    _orfs_pass(
        name = name,
        top = top,
        verilog_files = verilog_files,
        macros = macros,
        kept_macros = kept_macros,
        canon_blackbox_macros = canon_blackbox_macros,
        sources = mock_sources,
        user_sources = user_sources,
        stage_arguments = stage_arguments,
        renamed_inputs = {},
        arguments = arguments | mock_pin_arguments | {"SYNTH_GUT": "1"},
        user_arguments = user_arguments,
        extra_arguments = _merge_extra_arguments(extra_arguments, mock_extra_arguments),
        extra_configs = extra_configs,
        abstract_stage = "place",
        variant = mock_variant,
        abstract_variant = None,
        previous_stage = {},
        pdk = pdk,
        stage_data = stage_data,
        html = html,
        **kwargs
    )

    # mock_area.tcl runs in the floorplan stage's environment, where the
    # place-scoped pin settings are filtered out; the pin-fit sizing needs
    # the pin layers and place_pins' spacing the mocked flow will use, so
    # hand them over from the flow's own arguments.
    mock_area_arguments = {"MOCK_AREA": str(mock_area)}
    if mock_area == "pins":
        for var in ("IO_PLACER_H", "IO_PLACER_V", "PLACE_PINS_ARGS"):
            if var in arguments:
                mock_area_arguments[var] = arguments[var]
        mock_area_arguments |= mock_pin_arguments
    orfs_arguments(
        name = mock_area_name,
        src = _step_name(name, variant, "floorplan"),
        arguments = mock_area_arguments,
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
        create_deps_tar(step_name, kwargs.get("visibility", None))
        if save_odb and not kwargs.get("lint"):
            _orfs_estimate_report(
                name = _step_name(name, variant, "estimate"),
                src = step_name,
                arguments = arguments,
                sources = sources,
                variant = variant,
                openroad = kwargs.get("openroad"),
                visibility = kwargs.get("visibility"),
            )
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
            create_deps_tar(squash_name, kwargs.get("visibility", None))
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

    def do_step(step, prev, kwargs, more_kwargs = {}, data = []):
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
                user_arguments = user_arguments,
                sources = sources,
                user_sources = user_sources,
                extra_arguments = extra_arguments,
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
        create_deps_tar(pre_layout_name, kwargs.get("visibility", None))
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
        create_deps_tar(sn, kwargs.get("visibility", None))
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
