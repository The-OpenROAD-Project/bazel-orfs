"""Rule implementations and declarations for OpenROAD-flow-scripts Bazel rules."""

load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load(
    "//private:attrs.bzl",
    "flow_attrs",
    "flow_provides",
    "fork_attrs",
    "openroad_attrs",
    "openroad_only_attrs",
    "orfs_attrs",
    "renamed_inputs_attr",
    "synth_attrs",
    "yosys_attrs",
    "yosys_only_attrs",
)
load(
    "//private:environment.bzl",
    "EXPAND_VERILOG_DIRS",
    "artifact_dir",
    "config_arguments",
    "config_environment",
    "data_arguments",
    "data_inputs",
    "data_inputs_excluding",
    "declare_artifact",
    "declare_artifacts",
    "deps_inputs",
    "environment_string",
    "extensionless_basename",
    "flow_environment",
    "flow_inputs",
    "flow_runfiles",
    "flow_substitutions",
    "fork_arguments",
    "generation_commands",
    "hack_away_prefix",
    "input_commands",
    "log_dir_arguments",
    "log_timestamps_make_arg",
    "merge_and_filter_arguments",
    "merge_arguments",
    "module_top",
    "odb_arguments",
    "orfs_additional_arguments",
    "out_dir_arguments",
    "pdk_inputs",
    "rename_inputs",
    "renames",
    "required_arguments",
    "run_arguments",
    "sdc_arguments",
    "source_inputs",
    "test_inputs",
    "verilog_arguments",
    "work_home_relative",
    "write_stage_filter",
    "yosys_environment",
    "yosys_inputs",
    "yosys_substitutions",
)
load(
    "//private:providers.bzl",
    "LoggingInfo",
    "OrfsDepInfo",
    "OrfsInfo",
    "PdkInfo",
    "TopInfo",
)
load(
    "//private:stages.bzl",
    "ALL_STAGES",
    "ALL_STAGE_TO_VARIABLES",
    "STAGE_SUBSTEPS",
    "get_sources",
    "get_stage_args",
    "keep_modules",
)

# --- Shared helpers ---

# buildifier: disable=external-path
#
# The external-path warning exists to catch code that reaches into another
# repository's layout by hand, which is fragile. This function is the one
# place where that layout is the subject rather than an assumption: it
# builds a portable tar whose entries have to match bazel's own runfiles
# layout, in which an external repo's files appear under
# external/<repo>/. Spelling that prefix out is what makes the archive
# loadable by a consumer using either short_path or path references, so
# the literal is the contract, not a shortcut around one.
def _tar_paths(f):
    """Map a file to its archive path(s).

    External repo files need two entries:
    - <repo>/path — for short_path refs from _main/ (../repo/path)
    - _main/external/<repo>/path — for path refs (external/repo/path)
    Everything else goes under _main/<short_path>.
    """
    sp = f.short_path
    if sp.startswith("../"):
        rel = sp[3:]
        return [rel, "_main/external/" + rel]
    return ["_main/" + sp]

def _package_stage(ctx, config, make, runfiles_depset, renames = []):
    """Create a portable .tar.gz from stage dependencies.

    Returns the tar File.
    """
    tar = declare_artifact(ctx, "results", ctx.attr.name + "_deps.tar.gz")
    manifest = declare_artifact(ctx, "results", ctx.attr.name + "_deps_manifest.txt")

    # Generate top-level make wrapper script.
    make_wrapper = declare_artifact(ctx, "results", ctx.attr.name + "_deps_make")
    ctx.actions.write(
        output = make_wrapper,
        is_executable = True,
        content = "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")/_main\"\n# Point rules_cc runfiles library at the deployed runfiles tree\nexport RUNFILES_DIR=\"$(pwd)/..\"\nexec ./{} \"$@\"\n".format(
            make.short_path,
        ),
    )

    # Build manifest: src_path\tdst_path
    all_files = runfiles_depset.to_list()
    lines = []
    for f in all_files:
        for dst in _tar_paths(f):
            lines.append("{}\t{}".format(f.path, dst))

    # Config goes to _main/config.mk
    lines.append("{}\t_main/config.mk".format(config.path))

    # Renames: r.src is a short_path string; resolve to actual path.
    short_to_path = {f.short_path: f.path for f in all_files}
    for r in renames:
        real_src = short_to_path.get(r.src, r.src)
        lines.append("{}\t_main/{}".format(real_src, r.dst))

    # Make wrapper at top level
    lines.append("{}\tmake".format(make_wrapper.path))

    ctx.actions.write(
        output = manifest,
        content = "\n".join(lines) + "\n",
    )

    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = [
            ctx.file._package_stage.path,
            manifest.path,
            tar.path,
        ],
        inputs = depset([manifest, ctx.file._package_stage, config, make_wrapper] + all_files),
        outputs = [tar],
        mnemonic = "OrfsPackage",
        progress_message = "Packaging %s" % ctx.label,
    )

    return tar

def _expand_deploy_template(ctx, exe, config, make, genfiles, name = "", renames = []):
    """Expands the deploy template for a stage.

    Args:
      ctx: Rule context.
      exe: Output File for the shell script.
      config: The config File (short version for deploy).
      make: The make script File.
      genfiles: List of Files to include in the deploy directory.
      name: Deploy folder name. Only deps targets set this to get per-target folders.
      renames: List of rename structs (src, dst). Only used by deps rule.
    """
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = {
            "${CONFIG}": config.short_path,
            "${GENFILES}": " ".join(sorted([f.short_path for f in genfiles])),
            "${MAKE}": make.short_path,
            "${NAME}": name,
            "${PACKAGE}": ctx.label.package,
            "${RENAMES}": " ".join(
                ["{}:{}".format(r.src, r.dst) for r in renames],
            ),
        },
    )

def _make_cmd(ctx):
    """Returns the make command prefix, with --silent in lint mode."""
    silent = "--silent " if getattr(ctx.attr, "lint", False) else ""
    return "{make} {silent}{stamp}$@".format(
        make = ctx.executable._make.path,
        silent = silent,
        stamp = log_timestamps_make_arg(ctx),
    )

def _create_make_script(ctx, name, extra_substitutions = {}):
    """Creates the make wrapper script via template expansion.

    Args:
      ctx: Rule context.
      name: Filename for the declared make script.
      extra_substitutions: Additional substitutions beyond flow_substitutions.

    Returns:
      The declared make File.
    """
    make = ctx.actions.declare_file(name)
    silent = "--silent " if getattr(ctx.attr, "lint", False) else ""
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = flow_substitutions(ctx) |
                        {'"$@"': '{}DESIGN_CONFIG="config.mk" "$@"'.format(silent)} |
                        extra_substitutions,
    )
    return make

# --- PDK rule ---

def _pdk_impl(ctx):
    return [
        DefaultInfo(
            files = depset(ctx.files.srcs),
        ),
        PdkInfo(
            name = ctx.attr.name,
            files = depset(ctx.files.srcs),
            libs = depset(ctx.files.libs),
            config = ctx.attr.config,
        ),
    ]

orfs_pdk = rule(
    implementation = _pdk_impl,
    attrs = {
        "config": attr.label(
            allow_single_file = ["config.mk"],
        ),
        "srcs": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "libs": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
    },
)

# --- Macro rule ---

def _macro_impl(ctx):
    info = {}
    for field in ["odb", "gds", "lef", "lib"]:
        if not getattr(ctx.attr, field):
            continue
        for file in getattr(ctx.attr, field).files.to_list():
            if file.extension != field:
                continue
            info[file.extension] = file

    lib_pre_layout = None
    if ctx.attr.lib and OrfsInfo in ctx.attr.lib:
        lib_pre_layout = ctx.attr.lib[OrfsInfo].lib_pre_layout

    return [
        DefaultInfo(
            files = depset(ctx.files.odb + ctx.files.gds + ctx.files.lef + ctx.files.lib),
        ),
        OutputGroupInfo(
            **{
                f.basename: depset([f])
                for f in ctx.files.odb + ctx.files.gds + ctx.files.lef + ctx.files.lib
            }
        ),
        OrfsInfo(
            odb = info.get("odb"),
            sdc = info.get("sdc"),
            gds = info.get("gds"),
            lef = info.get("lef"),
            lib = info.get("lib"),
            lib_pre_layout = lib_pre_layout,
            additional_gds = depset([]),
            additional_lefs = depset([]),
            additional_libs = depset([]),
            additional_libs_pre_layout = depset([]),
            arguments = depset([]),
        ),
        TopInfo(
            module_top = ctx.attr.module_top,
        ),
    ]

orfs_macro = rule(
    implementation = _macro_impl,
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, TopInfo],
    attrs = {
                "module_top": attr.string(mandatory = True),
            } |
            {
                field: attr.label(
                    allow_files = [field],
                    providers = [DefaultInfo],
                )
                for field in [
                    "odb",
                    "gds",
                    "lef",
                    "lib",
                ]
            },
)

# --- Deps rule ---

def _deps_impl(ctx):
    return [
        DefaultInfo(
            runfiles = ctx.attr.src[OrfsDepInfo].runfiles,
        ),
        ctx.attr.src[OrfsInfo],
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        LoggingInfo(
            log_dir = ctx.attr.src[LoggingInfo].log_dir,
            logs = depset(),
            reports = depset(),
            drcs = depset([]),
            jsons = depset([]),
        ),
        ctx.attr.src[OrfsDepInfo],
    ]

orfs_deps = rule(
    implementation = _deps_impl,
    attrs = flow_attrs() | openroad_only_attrs() | yosys_only_attrs(),
)

# --- Deploy sources rule ---
# Thin rule that exposes OrfsDepInfo.runfiles as DefaultInfo so that
# pkg_tar(include_runfiles=True) can package them.

def _deploy_srcs_impl(ctx):
    dep = ctx.attr.src[OrfsDepInfo]
    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    _expand_deploy_template(
        ctx,
        exe,
        config = dep.config,
        make = dep.make,
        genfiles = dep.files.to_list(),
        name = ctx.attr.name,
        renames = dep.renames,
    )
    wrapper = ctx.actions.declare_file(ctx.attr.name + "_run.sh")
    ctx.actions.write(
        output = wrapper,
        is_executable = True,
        content = """\
#!/bin/bash
RUNFILES="${{RUNFILES_DIR:-$0.runfiles}}"
DEPLOY="$RUNFILES/_main/{deploy}"
ln -sfn "$RUNFILES" "$DEPLOY.runfiles"
"$DEPLOY" "$@"
echo "Reproducer installed to: ${{BUILD_WORKSPACE_DIRECTORY:-$PWD}}/tmp/{package}/{name}"
""".format(
            deploy = exe.short_path,
            package = ctx.label.package,
            name = ctx.attr.name,
        ),
    )
    return [DefaultInfo(
        executable = wrapper,
        files = depset([exe, wrapper], transitive = [dep.files]),
        runfiles = ctx.runfiles(files = [exe, wrapper]).merge(dep.runfiles),
    )]

orfs_deploy_srcs = rule(
    implementation = _deploy_srcs_impl,
    executable = True,
    attrs = {
        "src": attr.label(
            mandatory = True,
            providers = [OrfsDepInfo],
        ),
        "_deploy_template": attr.label(
            default = Label("//:deploy.tpl"),
            allow_single_file = True,
        ),
    },
)

def create_deps_tar(name, visibility = None):
    """Generate the _deps reproducer companions for an ORFS target.

    Creates:
      {name}_deps — runnable orfs_deploy_srcs wrapper that installs a
        self-contained reproducer under ./tmp
      {name}_deps_tar — pkg_tar of the same runfiles, for offline
        archives and upstream bug reports

    Both are tagged "manual" so wildcard builds (bazel build //pkg:all) skip
    them; they build only when named. The target must provide OrfsDepInfo.

    Args:
      name: the ORFS target to deploy, in this package. The companions are
        named after it.
      visibility: visibility for the generated companions.
    """
    orfs_deploy_srcs(
        name = name + "_deps",
        src = ":" + name,
        visibility = visibility,
        tags = ["manual"],
    )
    pkg_tar(
        name = name + "_deps_tar",
        srcs = [":" + name + "_deps"],
        extension = "tar.gz",
        include_runfiles = True,
        visibility = visibility,
        tags = ["manual"],
    )

# --- Run rule ---

def _run_impl(ctx):
    if OrfsInfo in ctx.attr.src:
        config = ctx.attr.src[OrfsInfo].config
    else:
        config = ctx.attr.src[OrfsDepInfo].config
    outs = []
    for k in dir(ctx.outputs):
        outs.extend(getattr(ctx.outputs, k))

    out_dir = None
    if ctx.attr.out_dir:
        out_dir = ctx.actions.declare_directory(ctx.attr.out_dir)
        outs.append(out_dir)
    if not outs:
        fail("orfs_run requires at least one of `outs` or `out_dir`")

    original_config = config
    all_jsons = ctx.files.extra_arguments
    inherited_jsons = ctx.attr.src[OrfsInfo].arguments.to_list() if OrfsInfo in ctx.attr.src else []

    config, extra_files = merge_and_filter_arguments(
        ctx,
        category = "results",
        name = ctx.attr.name,
        original_config = original_config,
        inherited_jsons = inherited_jsons,
        extra_jsons = all_jsons,
        stages = getattr(ctx.attr, "stages", []),
    )

    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile.path,
        ],
        command = " ".join(
            [
                ctx.executable._make.path,
                ctx.expand_location(ctx.attr.cmd, ctx.attr.data),
                ctx.expand_location(ctx.attr.extra_args, ctx.attr.data),
                # A make command-line variable, not an environment one:
                # variables.mk assigns LOG_DIR with `=`, which beats the
                # environment. Same form the deploy script passes it in.
                environment_string(log_dir_arguments(ctx)),
                "$@",
            ],
        ),
        env = flow_environment(ctx) |
              yosys_environment(ctx) |
              config_environment(config) |
              odb_arguments(ctx) |
              sdc_arguments(ctx) |
              data_arguments(ctx) |
              run_arguments(ctx) |
              fork_arguments(ctx) |
              out_dir_arguments(out_dir),
        inputs = depset(
            [config, ctx.file.script, ctx.file._fork_tcl, ctx.file._fork_lib] + extra_files,
            transitive = [
                data_inputs(ctx),
                source_inputs(ctx),
                # The src stage's accumulated logs, opt-in via src_logs=
                # for run scripts that read e.g. stage elapsed times.
                # Sandbox-safe here, unlike in source_inputs: the run
                # action writes only run.log, never a stage log name.
                # Opt-in because logs are never byte-stable (every one
                # carries Elapsed/CPU/Peak-memory lines), so as a default
                # input they re-ran every orfs_run whenever any upstream
                # stage re-executed, byte-identical artifacts or not.
                ctx.attr.src[LoggingInfo].logs if (
                    ctx.attr.src_logs and LoggingInfo in ctx.attr.src
                ) else depset(),
            ],
        ),
        outputs = outs,
        tools = depset(
            transitive = [
                flow_inputs(ctx),
                yosys_inputs(ctx),
            ],
        ),
    )

    make = ctx.actions.declare_file(
        "make_{}_{}_run".format(ctx.attr.name, ctx.attr.variant),
    )
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = flow_substitutions(ctx) |
                        {
                            '"$@"': environment_string(
                                        hack_away_prefix(
                                            arguments = odb_arguments(ctx) |
                                                        sdc_arguments(ctx) |
                                                        data_arguments(ctx) |
                                                        run_arguments(ctx) |
                                                        log_dir_arguments(ctx) |
                                                        fork_arguments(ctx) |
                                                        out_dir_arguments(out_dir),
                                            prefix = config.root.path,
                                        ) |
                                        {
                                            "DESIGN_CONFIG": "config.mk",
                                        },
                                    ) +
                                    ' "$@"',
                        },
    )

    return [
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        DefaultInfo(
            files = depset(outs),
        ),
        OutputGroupInfo(**{f.basename: depset([f]) for f in outs}),
        OrfsDepInfo(
            make = make,
            config = config,
            renames = [],
            files = depset([config, ctx.file.script, ctx.file._fork_tcl, ctx.file._fork_lib] + extra_files),
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    [config, make, ctx.file.script, ctx.file._fork_tcl, ctx.file._fork_lib] + extra_files,
                    transitive = [
                        flow_inputs(ctx),
                        data_inputs(ctx),
                        source_inputs(ctx),
                    ],
                ),
            ),
        ),
    ]

_orfs_run_rule = rule(
    implementation = _run_impl,
    attrs = yosys_attrs() |
            openroad_attrs() |
            fork_attrs() |
            {
                "cmd": attr.string(
                    mandatory = False,
                    default = "run",
                ),
                "extra_args": attr.string(
                    mandatory = False,
                    default = "",
                ),
                "out_dir": attr.string(
                    mandatory = False,
                    default = "",
                    doc = "Name of a declared output directory (a tree " +
                          "artifact). Its path reaches the run script as " +
                          "$RUN_OUTPUT_DIR; the script decides what files " +
                          "to put there. Use for scripts whose set of " +
                          "output files is not known in advance (e.g. a " +
                          "fork/join tree walk writing one JSON per leaf).",
                ),
                "outs": attr.output_list(
                    mandatory = False,
                    allow_empty = True,
                ),
                "script": attr.label(
                    mandatory = True,
                    allow_single_file = ["tcl"],
                ),
                "src_logs": attr.bool(
                    default = False,
                    doc = "Stage the src stage's accumulated logs into the " +
                          "run action's inputs, for scripts that read them " +
                          "(e.g. stage elapsed times from $LOG_DIR/*.log, " +
                          "which names the src flow's log directory). " +
                          "Off by default: every log carries wall-clock/" +
                          "CPU/memory lines, so a log input re-runs this " +
                          "action whenever ANY upstream stage re-executes — " +
                          "even when the artifacts it actually reads are " +
                          "byte-identical — and guarantees remote-cache " +
                          "misses across machines.",
                ),
                "stages": attr.string_list(
                    mandatory = False,
                    default = [],
                ),
            },
)

def _expand_sources(kwargs):
    """Processes the 'sources' attribute into 'data' and 'arguments'.

    Runs at MACRO-EXPANSION time: it mutates raw kwargs before the rule is
    instantiated, so `data`/`arguments` are set as attributes and Bazel
    expands `$(locations ...)` later.

    Source filtering is done at ANALYSIS time via the shared stages.bzl
    helpers, keyed by the target's `stages` (empty = no filtering):
      * sources -> data and sources -> $(locations) args are filtered
        together, by the same predicate (you cannot emit $(locations X) for a
        label pruned from data — see MORATORIUM(source-filtering-is-analysis-time)
        in private/stages.bzl);
      * plain string `arguments` are left UNTOUCHED here and filtered at
        EXECUTION time by merge_and_filter_arguments (more code under test).
        Do NOT route them through get_stage_args.
    """
    sources = kwargs.pop("sources", {})
    if sources:
        # Normalize scalar source values to lists; the helpers expect lists.
        sources = {
            var: (labels if type(labels) == "list" else [labels])
            for var, labels in sources.items()
        }
        stages = kwargs.get("stages", [])

        data = kwargs.pop("data", [])
        if type(data) != "list":
            data = list(data)
        for label in get_sources(stages, sources):
            if label not in data:
                data.append(label)

        # get_stage_args(sources=...) returns ONLY the source-derived
        # $(locations) args, filtered by stage. Plain args stay as-is; append
        # source locs to any plain arg that shares a variable name.
        arguments = dict(kwargs.pop("arguments", {}))
        for var, locs in get_stage_args(stages, sources = sources).items():
            if var in arguments:
                arguments[var] = arguments[var] + " " + locs
            else:
                arguments[var] = locs

        kwargs["data"] = data
        kwargs["arguments"] = arguments
    return kwargs

def orfs_run(deps = False, **kwargs):
    """Rule wrapper for orfs_run to populate data dependencies and CLI arguments from explicitly specified sources.

    Args:
        deps: Also emit the {name}_deps / {name}_deps_tar reproducer
            companions, the way the flow stage macros do. Opt-in: most
            orfs_run targets are build steps nobody reproduces by hand, and
            the companions would be dead targets in every package. Turn it
            on for a run whose failures get debugged interactively or filed
            upstream.
        **kwargs: The keyword arguments to pass to the underlying _orfs_run_rule.
    """
    _orfs_run_rule(**_expand_sources(kwargs))
    if deps:
        create_deps_tar(kwargs.get("name"), kwargs.get("visibility", None))

def _variables_impl(ctx):
    out = ctx.actions.declare_file(ctx.attr.name + ".json")
    ctx.actions.write(out, json.encode(data_arguments(ctx)))
    return [DefaultInfo(files = depset([out]))]

orfs_variables = rule(
    implementation = _variables_impl,
    attrs = orfs_attrs(),
)

# --- Arguments rule ---

def _arguments_impl(ctx):
    """Runs a Tcl script to compute flow arguments, outputs OrfsInfo with modified arguments."""
    src_info = ctx.attr.src[OrfsInfo]

    # Put the computed .json under the variant-keyed results/ path so
    # extra_arguments consumers see a .json in DefaultInfo.files.
    computed_json = declare_artifact(ctx, "results", ctx.attr.name + ".json")

    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile.path,
        ],
        command = " ".join(
            [
                ctx.executable._make.path,
                "run",
                "$@",
            ],
        ),
        env = flow_environment(ctx) |
              yosys_environment(ctx) |
              config_environment(src_info.config) |
              odb_arguments(ctx) |
              sdc_arguments(ctx) |
              data_arguments(ctx) |
              run_arguments(ctx) |
              {"OUTPUT": computed_json.path},
        inputs = depset(
            [src_info.config, ctx.file.script],
            transitive = [
                data_inputs(ctx),
                source_inputs(ctx),
            ],
        ),
        outputs = [computed_json],
        tools = depset(
            transitive = [
                flow_inputs(ctx),
                yosys_inputs(ctx),
            ],
        ),
    )

    return [
        DefaultInfo(files = depset([computed_json])),
        OrfsInfo(
            stage = src_info.stage,
            config = src_info.config,
            variant = src_info.variant,
            odb = src_info.odb,
            sdc = src_info.sdc,
            gds = src_info.gds,
            lef = src_info.lef,
            lib = src_info.lib,
            lib_pre_layout = src_info.lib_pre_layout,
            additional_gds = src_info.additional_gds,
            additional_lefs = src_info.additional_lefs,
            additional_libs = src_info.additional_libs,
            additional_libs_pre_layout = src_info.additional_libs_pre_layout,
            arguments = depset(
                [computed_json],
                transitive = [src_info.arguments],
            ),
        ),
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        ctx.attr.src[LoggingInfo],
        ctx.attr.src[OrfsDepInfo],
    ]

orfs_arguments = rule(
    implementation = _arguments_impl,
    attrs = yosys_attrs() |
            openroad_attrs() |
            {
                "script": attr.label(
                    mandatory = True,
                    allow_single_file = ["tcl"],
                ),
                "stages": attr.string_list(
                    mandatory = False,
                    default = [],
                ),
            },
)

# --- Test rule ---

def _test_impl(ctx):
    config = ctx.attr.src[OrfsDepInfo].config

    inherited_jsons = ctx.attr.src[OrfsInfo].arguments.to_list() if OrfsInfo in ctx.attr.src else []

    config, extra_files = merge_and_filter_arguments(
        ctx,
        category = "results",
        name = ctx.attr.name,
        original_config = config,
        inherited_jsons = inherited_jsons,
        extra_jsons = getattr(ctx.files, "extra_arguments", []),
        stages = getattr(ctx.attr, "stages", []),
    )

    test = ctx.actions.declare_file(
        "make_{}_{}_test".format(ctx.attr.name, ctx.attr.variant),
    )

    script_inputs = []

    if ctx.attr.lint:
        # Lint mode: test just verifies the dependency chain builds.
        # No metadata-check since mock-openroad doesn't produce real metrics.
        ctx.actions.write(
            output = test,
            is_executable = True,
            content = "#!/bin/sh\nexit 0\n",
        )
    else:
        # For external repo targets, WORK_HOME must include the external/<repo>/
        # prefix so Make finds results/reports at the correct runfiles path.
        work_home = work_home_relative(ctx) if ctx.label.workspace_name else None

        if hasattr(ctx.attr, "script") and ctx.file.script:
            script_inputs = [ctx.file.script]
            script_arg = {"RUN_SCRIPT": ctx.file.script.path}
        else:
            script_inputs = []
            script_arg = {}

        tool_env = {
            "OPENROAD_EXE": ctx.executable.openroad.short_path,
            "OPENSTA_EXE": ctx.executable.opensta.short_path,
            "YOSYS_EXE": ctx.executable.yosys.short_path,
            "KLAYOUT_CMD": ctx.executable._klayout.short_path if hasattr(ctx.executable, "_klayout") and ctx.executable._klayout else "",
            "PYTHON_EXE": ctx.executable._python.short_path,
            "ABC": ctx.executable._abc.short_path,
            "FLOW_HOME": ctx.file._makefile.dirname,
            "STDBUF_CMD": "",
        }

        ctx.actions.write(
            output = test,
            is_executable = True,
            content = """
#!/bin/sh
set -e
if [ ! -e external ]; then
    # Needed as of Bazel >= 8
    ln -sf $(realpath $(pwd)/..) external
fi
mkdir -p $(dirname {bin_dir})
ln -sfn $(pwd) {bin_dir}
{make} --file {makefile} {moreargs} {cmd}
""".format(
                cmd = ctx.attr.cmd,
                make = ctx.executable._make.short_path,
                makefile = ctx.file._makefile.path,
                bin_dir = ctx.bin_dir.path,
                moreargs = environment_string(
                    hack_away_prefix(
                        arguments = odb_arguments(ctx) | sdc_arguments(ctx) | data_arguments(ctx) | script_arg | tool_env,
                        prefix = config.root.path,
                    ) |
                    {"DESIGN_CONFIG": config.short_path} |
                    ({"WORK_HOME": work_home} if work_home else {}),
                ),
            ),
        )

    return [
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        DefaultInfo(
            executable = test,
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    [config, test] + script_inputs + extra_files,
                    transitive = [
                        test_inputs(ctx),
                        data_inputs(ctx),
                        source_inputs(ctx),
                        flow_inputs(ctx),
                        yosys_inputs(ctx),
                        ctx.attr.src[OrfsDepInfo].files,
                    ],
                ),
            ).merge(ctx.attr.src[DefaultInfo].default_runfiles).merge(ctx.attr.src[OrfsDepInfo].runfiles),
        ),
    ]

_orfs_rule_test = rule(
    implementation = _test_impl,
    attrs = yosys_attrs() |
            openroad_attrs() |
            flow_attrs() |
            {
                "cmd": attr.string(
                    mandatory = False,
                    default = "metadata-check",
                ),
                "script": attr.label(
                    mandatory = False,
                    allow_single_file = ["tcl", "sh", "py"],
                ),
                "stages": attr.string_list(
                    mandatory = False,
                    default = [],
                ),
            },
    test = True,
)

def orfs_test(**kwargs):
    """Rule wrapper for orfs_test to populate data dependencies and CLI arguments from explicitly specified sources.

    Args:
        **kwargs: The keyword arguments to pass to the underlying _orfs_rule_test.
    """
    _orfs_rule_test(**_expand_sources(kwargs))

# --- Run-executable rule ---
#
# Like orfs_run, but builds a `bazelisk run` target instead of a build-time
# action. The emitted wrapper exposes the same env that orfs_run sets, plus a
# pass-through for CLI args: every `KEY=VALUE` positional received after
# `bazelisk run //path:target -- ...` is forwarded to make as a variable
# override, which becomes an environment variable when make invokes the Tcl
# script. Make's last-wins rule means CLI overrides beat the BUILD-time
# `arguments` dict.
#
# Use this when the script has a parameter the user wants to vary
# per-invocation (e.g. an endpoint glob for a timing-path drill-down) and
# wiring a separate orfs_run target per parameter value would be tedious.

def _run_executable_impl(ctx):
    config = ctx.attr.src[OrfsDepInfo].config

    # With `stages`, reproduce orfs_run's stage-scoped configuration: merge
    # the src's inherited argument jsons and any extra_arguments jsons,
    # filtered to the named stages, into a fresh DESIGN_CONFIG. A script
    # that re-runs later flow stages off an early ODB (an estimator walking
    # floorplan..grt off a synth stage) reads the same stage-scoped
    # variables it would under orfs_run — config identity between the
    # build-time rule and the executable. Without `stages` the behavior is
    # unchanged: the src stage's config is used as-is.
    extra_files = []
    if ctx.attr.stages:
        inherited_jsons = ctx.attr.src[OrfsInfo].arguments.to_list() if OrfsInfo in ctx.attr.src else []
        config, extra_files = merge_and_filter_arguments(
            ctx,
            category = "results",
            name = ctx.attr.name,
            original_config = config,
            inherited_jsons = inherited_jsons,
            extra_jsons = ctx.files.extra_arguments,
            stages = ctx.attr.stages,
        )

        # The merged jsons name generated inputs by their execroot paths
        # (bazel-out/<cfg>/bin/...), which the runfiles tree the executable
        # runs from does not have — there a generated file sits at its
        # workspace-relative path, next to the sources. Strip the output
        # root so both kinds resolve at run time.
        runfiles_config = ctx.actions.declare_file(
            "{}_{}_runfiles_config.mk".format(ctx.attr.name, ctx.attr.variant),
        )
        ctx.actions.run_shell(
            inputs = [config],
            outputs = [runfiles_config],
            command = "sed 's|{}/||g' '{}' > '{}'".format(
                config.root.path,
                config.path,
                runfiles_config.path,
            ),
        )
        config = runfiles_config

    wrapper = ctx.actions.declare_file(
        "run_{}_{}_executable".format(ctx.attr.name, ctx.attr.variant),
    )

    # For external repo targets, WORK_HOME must include the external/<repo>/
    # prefix so Make finds results/reports at the correct runfiles path.
    work_home = work_home_relative(ctx) if ctx.label.workspace_name else None

    tool_env = {
        "OPENROAD_EXE": ctx.executable.openroad.short_path,
        "OPENSTA_EXE": ctx.executable.opensta.short_path,
        "YOSYS_EXE": ctx.executable.yosys.short_path,
        "KLAYOUT_CMD": ctx.executable._klayout.short_path if hasattr(ctx.executable, "_klayout") and ctx.executable._klayout else "",
        "PYTHON_EXE": ctx.executable._python.short_path,
        "ABC": ctx.executable._abc.short_path,
        "FLOW_HOME": ctx.file._makefile.dirname,
        "STDBUF_CMD": "",
        "RUN_SCRIPT": ctx.file.script.path,
    } | fork_arguments(ctx, short = True)

    moreargs = environment_string(
        hack_away_prefix(
            arguments = odb_arguments(ctx) | data_arguments(ctx) | tool_env,
            prefix = config.root.path,
        ) |
        {"DESIGN_CONFIG": config.short_path} |
        ({"WORK_HOME": work_home} if work_home else {}),
    )

    ctx.actions.write(
        output = wrapper,
        is_executable = True,
        content = """#!/bin/sh
set -e
if [ ! -e external ]; then
    # Needed as of Bazel >= 8. Concurrent invocations (e.g. an Optuna
    # study with n_jobs > 1) race to create the symlink; losing the race
    # is fine as long as the link exists afterwards.
    ln -sf $(realpath $(pwd)/..) external 2>/dev/null || [ -e external ]
fi
export ORFS_MAKE_EXE={make}
export ORFS_MAKEFILE={makefile}
export ORFS_CMD={cmd}
PYTHON="{python_exe}"
case "$PYTHON" in
  */*) ;;
  *) PYTHON="./$PYTHON" ;;
esac
SCRIPT="{py_script}"
case "$SCRIPT" in
  */*) ;;
  *) SCRIPT="./$SCRIPT" ;;
esac
exec "$PYTHON" "$SCRIPT" {moreargs} "$@"
""".format(
            make = ctx.executable._make.short_path,
            makefile = ctx.file._makefile.path,
            cmd = ctx.attr.cmd,
            moreargs = moreargs,
            python_exe = ctx.executable._python.short_path,
            py_script = ctx.file._run_executable_script.short_path,
        ),
    )

    # The executable drives make through run_executable.py, so it never
    # needed the make wrapper script the flow rules deploy. A reproducer
    # does: deploy.tpl runs `./make <cmd>` against config.mk. Mint one with
    # the same arguments the wrapper bakes in, de-prefixed for the deployed
    # tree the way orfs_run does.
    deploy_make = _create_make_script(
        ctx,
        "make_{}_{}_run_executable".format(ctx.attr.name, ctx.attr.variant),
        extra_substitutions = {
            '"$@"': environment_string(
                hack_away_prefix(
                    arguments = odb_arguments(ctx) |
                                data_arguments(ctx) |
                                run_arguments(ctx) |
                                fork_arguments(ctx),
                    prefix = config.root.path,
                ) |
                {"DESIGN_CONFIG": "config.mk"},
            ) + ' "$@"',
        },
    )

    reproducer_files = [
        config,
        deploy_make,
        ctx.file.script,
        ctx.file._fork_tcl,
        ctx.file._fork_lib,
    ] + extra_files

    return [
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        DefaultInfo(
            executable = wrapper,
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    [config, wrapper, ctx.file._run_executable_script, ctx.file.script, ctx.file._fork_tcl, ctx.file._fork_lib] + extra_files,
                    transitive = [
                        flow_inputs(ctx),
                        yosys_inputs(ctx),
                        data_inputs(ctx),
                        source_inputs(ctx),
                    ],
                ),
            ),
        ),
        OrfsDepInfo(
            make = deploy_make,
            config = config,
            renames = [],
            files = depset(reproducer_files),
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    reproducer_files,
                    transitive = [
                        flow_inputs(ctx),
                        data_inputs(ctx),
                        source_inputs(ctx),
                    ],
                ),
            ),
        ),
    ]

_orfs_rule_run_executable = rule(
    implementation = _run_executable_impl,
    attrs = yosys_attrs() |
            openroad_attrs() |
            fork_attrs() |
            {
                "cmd": attr.string(
                    mandatory = False,
                    default = "run",
                ),
                "script": attr.label(
                    mandatory = True,
                    allow_single_file = ["tcl"],
                ),
                "stages": attr.string_list(
                    mandatory = False,
                    default = [],
                    doc = "Stages whose scoped variables the executable's " +
                          "DESIGN_CONFIG carries, merged from the src's " +
                          "inherited argument jsons and extra_arguments " +
                          "exactly as orfs_run does. Empty keeps the src " +
                          "stage's config unchanged.",
                ),
                "_run_executable_script": attr.label(
                    default = "//:run_executable.py",
                    allow_single_file = True,
                ),
            },
    executable = True,
)

def orfs_run_executable(deps = False, **kwargs):
    """Rule wrapper for orfs_run_executable to populate data dependencies and CLI arguments from explicitly specified sources.

    This rule produces a standalone executable that invokes GNU Make with the
    target's configuration and tools. It is designed for tight-loop optimizers
    like Optuna, where the overhead of a full `bazel build` would be too slow.

    **Execution Constraints**:
    1. **What the framework writes**: for the default `cmd = "run"`, the ORFS
       Makefile's `run` target does `mkdir -p` on `RESULTS_DIR`, `LOG_DIR`,
       `REPORTS_DIR` and `OBJECTS_DIR`, and writes exactly one file:
       `$(LOG_DIR)/$(RUN_LOG_NAME_STEM).log` (default `run.log`) — the full
       tool output plus a final elapsed-time line, opened in overwrite mode
       on every invocation. Nothing else is written by the framework; no
       metrics JSON is produced (unlike the flow stages).
    2. **Pass LOG_DIR**: the executable sets its working directory (`pwd`) to
       the Bazel runfiles root, and `LOG_DIR` defaults to the log directory of
       the flow the `src` stage belongs to — where the stage logs are, and
       *inside the runfiles tree*, so the framework writes `run.log` into
       Bazel's output tree. Pass `LOG_DIR=<absolute path>` (it is created if
       missing) to keep runfiles pristine. Concurrent invocations of the same
       executable (e.g. an Optuna study with `n_jobs > 1`) MUST each get
       their own `LOG_DIR` (or `RUN_LOG_NAME_STEM`), or they overwrite each
       other's `run.log`.
    3. **Read-only ORFS outputs**: scripts must treat the staged flow outputs
       under `RESULTS_DIR`, `REPORTS_DIR` and `OBJECTS_DIR` as read-only.
    4. **Absolute paths for custom outputs**: what the script itself writes is
       the script author's responsibility; script-specific output destinations
       must be passed via custom variables as **absolute paths** to write back
       to the workspace.
    5. **Results folders**: a script that produces a folder of files (e.g. a
       fork/join tree walk writing one JSON per leaf — see docs/fork.md)
       takes the folder as such an absolute-path variable, supplied by the
       caller per invocation exactly like `LOG_DIR`; concurrent invocations
       must not share it. (The build-time sibling `orfs_run` declares the
       folder itself via its `out_dir` attribute instead.)

    The compiled binary accepts `KEY=VALUE` positional arguments which become
    Make variable overrides, and an optional `--cmd` flag to override the default
    Make target (`run`).

    Example:
        $ ./bazel-bin/pkg/my_tuner PLACE_DENSITY=0.45 \\
              LOG_DIR=/tmp/trial42 MY_OUT_FILE=/tmp/trial42/out.json

    Args:
        deps: Also emit the {name}_deps / {name}_deps_tar reproducer
            companions. Opt-in for the same reason as orfs_run's.
        **kwargs: The keyword arguments to pass to the underlying _orfs_rule_run_executable.
    """
    _orfs_rule_run_executable(**_expand_sources(kwargs))
    if deps:
        create_deps_tar(kwargs.get("name"), kwargs.get("visibility", None))

# --- Synthesis rule ---

CANON_OUTPUT = "1_1_yosys_canonicalize.rtlil"

# 1_synth.odb/.sdc are not listed here: they are produced by do-1_synth
# (synth_odb.tcl), not yosys, and are only declared when save_odb=True.
SYNTH_OUTPUTS = ["1_2_yosys.v", "1_2_yosys.sdc", "mem.json"]

# Outputs of the OpenROAD-SYN synthesis flow (SYNTH_USE_SYN=1). synth_syn.tcl
# always writes the ODB, the canonicalized SDC and a gate-level Verilog
# netlist (LEC input); none of the yosys-flow files exist in this mode.
SYN_OUTPUTS = ["1_synth.odb", "1_synth.sdc", "1_synth.v"]
SYNTH_REPORTS = ["synth_stat.txt", "synth_mocked_memories.txt"]

def _yosys_parallel_synth(ctx, config, canon_output, synth_outputs, synth_logs, synth_jsons, synth_reports, num_partitions, save_odb, all_arguments = {}, clock_period = None, sdc_overrides = [], synth_data_inputs = None, sdc_only_inputs = None):
    """Parallel synthesis: keep → kept-json → N partitions → merge.

    Yosys is not deterministic when using host threads, so SYNTH_NUM_PARTITIONS
    defaulting to NUM_CPUS means synthesis results vary across machines with
    different core counts. Users who need reproducible builds should set a fixed
    SYNTH_NUM_PARTITIONS value.

    clock_period / sdc_overrides / synth_data_inputs carry the caller's
    clock-period extraction (see _yosys_impl): the preamble-sourcing yosys
    actions (keep, partitions, top) read SDC_FILE_CLOCK_PERIOD instead of
    the raw SDC, whose only legitimate consumers here are the sdc-copy and
    do-1_synth actions.

    When SYNTH_KEEP_MODULES is provided, the keep-hierarchy discovery step
    (synth_keep.tcl + rtlil_kept_modules.py) is skipped entirely.  The module
    list is written directly to kept_modules.json and partitions read from
    the canonical RTLIL, each running full coarse+fine synthesis with all
    other modules blackboxed.

    The parallel Make targets (do-yosys-keep, do-yosys-partition, etc.) only
    exist in the patched ORFS source, not in the docker image Makefile used by
    _makefile_yosys.  We therefore invoke Make for yosys-dependencies setup,
    then run the actual steps (synth_keep.tcl, synth_partition.sh, etc.)
    directly as shell commands.
    """
    base_env = (
        verilog_arguments([]) |
        flow_environment(ctx) |
        yosys_environment(ctx) |
        config_environment(config)
    )
    yosys_and_flow_tools = depset(transitive = [yosys_inputs(ctx), flow_inputs(ctx)])
    parallel_makefile = ctx.file._parallel_synth_makefile
    if synth_data_inputs == None:
        synth_data_inputs = data_inputs(ctx)
    if sdc_only_inputs == None:
        sdc_only_inputs = data_inputs(ctx)
    clock_period_inputs = [clock_period] if clock_period else []

    kept_json = declare_artifact(ctx, "results", "kept_modules.json")
    skip_keep = all_arguments.get("SYNTH_KEEP_MODULES", "")

    if skip_keep:
        # SYNTH_KEEP_MODULES provided: skip keep-hierarchy discovery.
        # Write kept_modules.json directly from the variable.
        modules = [m for m in skip_keep.split(" ") if m]
        modules_json = ", ".join(['"{}"'.format(m) for m in modules])
        ctx.actions.write(
            output = kept_json,
            content = '{{"modules": [{}]}}'.format(modules_json),
        )
        checkpoint_output = canon_output
    else:
        # Action 2a: keep → 1_1_yosys_keep.rtlil
        # Uses wrapper Makefile that includes ORFS Makefile + adds do-yosys-keep
        checkpoint_output = declare_artifact(ctx, "results", "1_1_yosys_keep.rtlil")
        keep_logs = declare_artifacts(ctx, "logs", ["1_1_yosys_keep.log"])
        keep_commands = [_make_cmd(ctx)] + generation_commands(
            [checkpoint_output] + keep_logs,
        )
        ctx.actions.run_shell(
            arguments = [
                "--file",
                parallel_makefile.path,
                "yosys-dependencies",
                "do-yosys-keep",
                "SYNTH_KEEP_SCRIPT=" + ctx.file._synth_keep_script.path,
            ] + sdc_overrides,
            command = " && ".join(keep_commands),
            env = base_env,
            inputs = depset(
                [canon_output, config, parallel_makefile, ctx.file._synth_keep_script] +
                clock_period_inputs + ctx.files.extra_configs,
                transitive = [
                    synth_data_inputs,
                    pdk_inputs(ctx),
                    deps_inputs(ctx, gds = False),
                ],
            ),
            outputs = [checkpoint_output] + keep_logs,
            tools = yosys_and_flow_tools,
        )

        # Action 2b: kept-json → kept_modules.json. The top is excluded:
        # the top partition synthesizes it, so it is not a kept submodule.
        ctx.actions.run_shell(
            command = "{python} {script} --top {top} {rtlil} {json}".format(
                python = ctx.executable._python.path,
                script = ctx.file._rtlil_kept_modules.path,
                top = module_top(ctx),
                rtlil = checkpoint_output.path,
                json = kept_json.path,
            ),
            inputs = [checkpoint_output, ctx.file._rtlil_kept_modules],
            outputs = [kept_json],
            tools = [ctx.executable._python],
        )

    # Optional pre-synth validation of kept_macros against the canonical
    # RTLIL. Runs in seconds; on mismatch prints a paste-ready corrected
    # dict to stderr and fails the build before any partition synth.
    # Gated on kept_macros_enabled so disabled call sites pay nothing.
    validated_kept_macros_json = None
    if ctx.attr.kept_macros_enabled:
        validated_kept_macros_json = declare_artifact(
            ctx,
            "results",
            "validated_kept_macros.json",
        )
        user_dict_json = ctx.actions.declare_file(
            ctx.label.name + "_user_kept_macros.json",
        )
        ctx.actions.write(
            output = user_dict_json,
            content = json.encode(ctx.attr.kept_macros),
        )
        macro_names_json = ctx.actions.declare_file(
            ctx.label.name + "_macro_names.json",
        )

        # Use TopInfo.module_top (the Verilog module name) — that's what
        # the RTLIL hierarchy contains. label.name has stage suffixes
        # like _behavioral / _generate_abstract that don't match RTLIL.
        ctx.actions.write(
            output = macro_names_json,
            content = json.encode([dep[TopInfo].module_top for dep in ctx.attr.deps]),
        )
        ctx.actions.run_shell(
            command = "{py} {script} --rtlil {rtlil} --kept-modules {kj} --macros {mj} --user-kept-macros {uj} --top {top} --output {out}".format(
                py = ctx.executable._python.path,
                script = ctx.file._rtlil_kept_macros.path,
                rtlil = canon_output.path,
                kj = kept_json.path,
                mj = macro_names_json.path,
                uj = user_dict_json.path,
                top = module_top(ctx),
                out = validated_kept_macros_json.path,
            ),
            inputs = [
                canon_output,
                kept_json,
                macro_names_json,
                user_dict_json,
                ctx.file._rtlil_kept_macros,
            ],
            outputs = [validated_kept_macros_json],
            tools = [ctx.executable._python],
            progress_message = "Validating kept_macros against canonicalize RTLIL for %s" % module_top(ctx),
        )

    # Actions 3..N: partition (parallel)
    # Uses wrapper Makefile for yosys-dependencies + do-yosys-partition
    partition_env_extra = {"SYNTH_SKIP_KEEP": "1"} if skip_keep else {}

    # kept_macros validation is NOT gated onto the build graph here. The
    # validation output (validated_kept_macros.json) carries no data the
    # partition or per-module canonicalize actions read — gating on it only
    # serialized every partition behind the validation action, which itself
    # waits on the global canonicalize (and thus all macro PnR abstracts).
    # Instead validated_kept_macros_json is surfaced in OutputGroupInfo so a
    # build_test can run it off the critical path; a stale dict fails that
    # test rather than blocking synth.
    extra_partition_inputs = []

    # Compute the kept-module list once so the per-module canonicalize
    # actions and the partition loop below agree on names and ordering.
    kept_modules_list = keep_modules(all_arguments)

    # Actions 2c (one per kept module): re-canonicalize each kept module
    # into its own RTLIL slice. The slice has all other kept modules
    # blackboxed and the target renamed to its bare name, so it serves as
    # a self-contained checkpoint for the partition action that consumes
    # it. Byte-stable under upstream edits that don't touch the module's
    # body — restores the canonicalize-as-cache-barrier intent at the
    # partition layer (matching what `synth-no-verilog-in-depinfo.patch`
    # did for post-synth stages downstream of `1_synth.v`).
    #
    # Filename sanitisation must match synth_partition.sh's `sanitize()`
    # and parallel_synth.mk's log path.
    per_module_rtlil = {}
    per_module_name_file = {}
    for module in kept_modules_list:
        sanitized = module.replace("$", "_").replace(".", "_").replace("[", "_").replace("]", "_")
        per_module_out = declare_artifact(
            ctx,
            "results",
            "partition_{}_canonical.rtlil".format(sanitized),
        )
        per_module_name_out = declare_artifact(
            ctx,
            "results",
            "partition_{}_canonical.name".format(sanitized),
        )
        blackboxes = [m for m in kept_modules_list if m != module]
        per_module_commands = [_make_cmd(ctx)] + generation_commands(
            [per_module_out, per_module_name_out],
        )
        ctx.actions.run_shell(
            arguments = [
                "--file",
                parallel_makefile.path,
                "do-yosys-canonicalize-module",
                "SYNTH_CANONICALIZE_MODULE_SCRIPT=" + ctx.file._synth_canonicalize_module_script.path,
                # No yosys-dependencies goal and no synth_preamble.tcl here,
                # so the clock period is never read — only the raw SDC needs
                # to stay out (dangling-path hygiene; the input set below
                # already excludes it).
            ] + (["SDC_FILE="] if sdc_overrides else []),
            command = " && ".join(per_module_commands),
            env = base_env | partition_env_extra | {
                "SYNTH_CHECKPOINT": checkpoint_output.path,
                "MODULE_BLACKBOXES": " ".join(blackboxes),
                "MODULE_TARGET_NAME": module,
                "MODULE_RTLIL_OUT": per_module_out.path,
                "MODULE_NAME_OUT": per_module_name_out.path,
                # Byte-stable per-module RTLIL is the whole point of this
                # action — partition synth caches on its hash. Force
                # SYNTH_REPEATABLE_BUILD=1 here regardless of the user's
                # variables.yaml default (0): src/area/capacitance attrs
                # MUST be stripped for the slice to be stable across
                # upstream PnR runs that re-characterise SHARED_LOGIC
                # macro .libs.
                "SYNTH_REPEATABLE_BUILD": "1",
            },
            inputs = depset(
                [
                    checkpoint_output,
                    config,
                    parallel_makefile,
                    ctx.file._synth_canonicalize_module_script,
                ] + extra_partition_inputs + ctx.files.extra_configs,
                transitive = [
                    synth_data_inputs,
                    pdk_inputs(ctx),
                ],
            ),
            outputs = [per_module_out, per_module_name_out],
            tools = yosys_and_flow_tools,
            progress_message = "Re-canonicalize for partition cache: {}".format(module),
        )
        per_module_rtlil[module] = per_module_out
        per_module_name_file[module] = per_module_name_out

    # Base inputs common to every partition (no macros yet — those are
    # added per partition below). checkpoint_output is NOT included here:
    # non-top partitions consume per-module RTLIL slices instead. The top
    # partition adds it back explicitly below.
    base_partition_inputs = depset(
        [
            kept_json,
            config,
            parallel_makefile,
            ctx.file._synth_partition_script,
            ctx.file._synth_tcl,
        ] + clock_period_inputs + extra_partition_inputs +
        ctx.files.extra_configs,
        transitive = [
            synth_data_inputs,
            pdk_inputs(ctx),
        ],
    )

    # Full macro inputs — used by the top action, and as the fallback
    # for every partition when per-partition scoping is disabled.
    all_macro_files = deps_inputs(ctx, gds = False)

    # Per-macro lookup tables, keyed by Verilog module name
    # (TopInfo.module_top — what the RTLIL hierarchy contains). Used
    # below to build per-partition inputs and per-partition config.mk
    # from ctx.attr.kept_macros. Macros without LEF aren't
    # physically-realised; safe to skip.
    macro_files_by_name = {}
    macro_dep_by_name = {}
    for dep in ctx.attr.deps:
        info = dep[OrfsInfo]
        if not info.lef:
            continue

        # No .gds: partition synthesis never reads it (see deps_inputs).
        files = [info.lef, info.lib]
        if info.lib_pre_layout:
            files.append(info.lib_pre_layout)
        name = dep[TopInfo].module_top
        macro_files_by_name[name] = depset([f for f in files if f])
        macro_dep_by_name[name] = dep

    # Base arguments common to every partition config (data + required;
    # ADDITIONAL_* gets layered on per-partition).
    base_arguments = data_arguments(ctx) | required_arguments(ctx)

    # kept_modules_list is computed earlier (before Action 2c per-module
    # canonicalize) so we don't recompute it here.

    macro_info_dict = {}
    for name, dep in macro_dep_by_name.items():
        info = dep[OrfsInfo]
        macro_info_dict[name] = {
            "lib": info.lib.path if info.lib else "",
            "lib_pre_layout": info.lib_pre_layout.path if info.lib_pre_layout else "",
            "lef": info.lef.path if info.lef else "",
            "gds": info.gds.path if info.gds else "",
        }
    macros_json_file = ctx.actions.declare_file(ctx.label.name + "_macros_info.json")
    ctx.actions.write(
        output = macros_json_file,
        content = json.encode(macro_info_dict),
    )

    use_kept_macros_scoping = (
        ctx.attr.kept_macros_enabled and bool(ctx.attr.kept_macros)
    )

    partition_outputs = []

    filter_json = write_stage_filter(ctx, "results", "1_synth_partition", ["synth"])

    for i in range(num_partitions):
        # Build a human-readable progress message showing which modules
        # this partition will synthesize.
        my_modules = []
        if kept_modules_list:
            my_modules = [m for idx, m in enumerate(kept_modules_list) if idx % num_partitions == i]
            if my_modules:
                progress_msg = "Synthesizing partition {}/{}: {}".format(i, num_partitions, ", ".join(my_modules))
            else:
                progress_msg = "Synthesizing partition {}/{} (empty)".format(i, num_partitions)
        else:
            progress_msg = "Synthesizing partition {}/{}".format(i, num_partitions)

        # Scope this partition's macro inputs to just the macros listed
        # for the kept modules it synthesises. Also generate a partition-
        # specific config.mk whose ADDITIONAL_LIBS/LEFS/GDS list ONLY
        # those macros — otherwise `yosys-dependencies` would expect the
        # full macro set as Make prereqs and fail with "no rule to make
        # target" on the macros we've excluded from inputs.
        if getattr(ctx.file, "filter_script", None):
            filtered_macros_dir = ctx.actions.declare_directory(
                ctx.label.name + "_filtered_macros_" + str(i),
            )
            ctx.actions.run(
                executable = ctx.executable._python,
                arguments = [
                    ctx.file.filter_script.path,
                    "--rtlil",
                    canon_output.path,
                    "--kept-modules",
                    kept_json.path,
                    "--macros-json",
                    macros_json_file.path,
                    "--out-dir",
                    filtered_macros_dir.path,
                ],
                inputs = [ctx.file.filter_script, canon_output, kept_json, macros_json_file] + all_macro_files.to_list(),
                outputs = [filtered_macros_dir],
                mnemonic = "FilterPartitionMacros",
                progress_message = "Filtering macros for partition {}".format(i),
            )

            my_macro_files = depset([filtered_macros_dir])
            my_arguments = merge_arguments(
                base_arguments,
                {},
            )
            my_analysis_args = config_arguments(ctx, my_arguments)
            my_analysis_json = declare_artifact(ctx, "results", "1_synth_partition_{}.analysis.json".format(i))
            ctx.actions.write(
                output = my_analysis_json,
                content = json.encode(my_analysis_args),
            )

            my_config = declare_artifact(
                ctx,
                "results",
                "1_synth_partition_{}.mk".format(i),
            )
            my_jsons = [my_analysis_json] + ctx.files.extra_arguments

            my_args = [
                ctx.file._merge_arguments.path,
                my_config.path,
                "--filter",
                filter_json.path,
            ]
            for f in ctx.files.extra_configs + [filtered_macros_dir]:
                if f == filtered_macros_dir:
                    my_args.extend(["--include", filtered_macros_dir.path + "/filtered_config.mk"])
                else:
                    my_args.extend(["--include", f.path])
            my_args.extend([f.path for f in my_jsons])

            ctx.actions.run(
                executable = ctx.executable._python,
                arguments = my_args,
                inputs = my_jsons + [ctx.file._merge_arguments, filter_json, filtered_macros_dir] + ctx.files.extra_configs,
                outputs = [my_config],
            )
            extra_partition_config = [my_config]
            partition_env_override = {"DESIGN_CONFIG": my_config.path}
        elif use_kept_macros_scoping:
            macro_name_set = {}
            for m in my_modules:
                for macro_name in ctx.attr.kept_macros.get(m, []):
                    macro_name_set[macro_name] = True
            my_macro_files = depset(
                transitive = [
                    macro_files_by_name[n]
                    for n in macro_name_set
                    if n in macro_files_by_name
                ],
            )
            my_deps_infos = [
                macro_dep_by_name[n][OrfsInfo]
                for n in macro_name_set
                if n in macro_dep_by_name
            ]
            my_arguments = merge_arguments(
                base_arguments,
                orfs_additional_arguments(my_deps_infos, use_pre_layout = True),
            )
            my_analysis_args = config_arguments(ctx, my_arguments)
            my_analysis_json = declare_artifact(ctx, "results", "1_synth_partition_{}.analysis.json".format(i))
            ctx.actions.write(
                output = my_analysis_json,
                content = json.encode(my_analysis_args),
            )

            my_config = declare_artifact(
                ctx,
                "results",
                "1_synth_partition_{}.mk".format(i),
            )
            my_jsons = [my_analysis_json] + ctx.files.extra_arguments

            my_args = [
                ctx.file._merge_arguments.path,
                my_config.path,
                "--filter",
                filter_json.path,
            ]
            for f in ctx.files.extra_configs:
                my_args.extend(["--include", f.path])
            my_args.extend([f.path for f in my_jsons])

            ctx.actions.run(
                executable = ctx.executable._python,
                arguments = my_args,
                inputs = my_jsons + [ctx.file._merge_arguments, filter_json] + ctx.files.extra_configs,
                outputs = [my_config],
            )
            extra_partition_config = [my_config]
            partition_env_override = {"DESIGN_CONFIG": my_config.path}
        else:
            my_macro_files = all_macro_files
            extra_partition_config = []
            partition_env_override = {}

        # Add per-module RTLIL slices for this partition's modules, plus
        # their canonical-name sidecars (synth_partition.sh reads the
        # sidecar to pass DESIGN_NAME=<canonical> to synth.tcl). Each
        # slice + sidecar is byte-stable under upstream edits that don't
        # touch the module's body, so the partition action's input set
        # is stable too — restoring the canonicalize-as-cache-barrier
        # intent at the partition layer.
        #
        # With no pinned list there are no slices: the kept modules were
        # discovered by synth_keep.tcl inside a build action, too late to
        # declare an action per name. Every partition then reads the
        # global keep checkpoint, exactly as the top partition does, and
        # synth_partition.sh blackboxes the other kept modules itself.
        # That trades the per-module cache barrier for a working build;
        # pinning SYNTH_KEEP_MODULES buys the barrier back.
        my_per_module_files = []
        for m in my_modules:
            if m in per_module_rtlil:
                my_per_module_files.append(per_module_rtlil[m])
                my_per_module_files.append(per_module_name_file[m])
        if not kept_modules_list:
            my_per_module_files.append(checkpoint_output)
        partition_inputs = depset(
            [base_inp for base_inp in extra_partition_config] + my_per_module_files,
            transitive = [base_partition_inputs, my_macro_files],
        )

        part_output = declare_artifact(ctx, "results", "partition_{}.v".format(i))
        partition_outputs.append(part_output)
        part_commands = [_make_cmd(ctx)] + generation_commands([part_output])
        ctx.actions.run_shell(
            arguments = [
                "--file",
                parallel_makefile.path,
                "yosys-dependencies",
                "do-yosys-partition",
                "SYNTH_PARTITION_SCRIPT=" + ctx.file._synth_partition_script.path,
            ] + sdc_overrides,
            command = " && ".join(part_commands),
            env = base_env | partition_env_extra | partition_env_override | {
                "SYNTH_PARTITION_ID": str(i),
                "SYNTH_NUM_PARTITIONS": str(num_partitions),
                "SYNTH_TCL": ctx.file._synth_tcl.path,
            },
            inputs = partition_inputs,
            outputs = [part_output],
            tools = yosys_and_flow_tools,
            progress_message = progress_msg,
        )

    # Action 4: synthesize the top module with all kept modules blackboxed.
    # Top integration always sees the full macro set — it stitches every
    # partition together and is the join point of the synth phase, so
    # scoping its inputs doesn't help wall time. Top synth reads the
    # global checkpoint directly (not a per-module slice), so include
    # checkpoint_output explicitly here.
    top_partition_inputs = depset(
        [checkpoint_output],
        transitive = [base_partition_inputs, all_macro_files],
    )
    top_output = declare_artifact(ctx, "results", "partition_top.v")
    top_commands = [_make_cmd(ctx)] + generation_commands([top_output])
    ctx.actions.run_shell(
        arguments = [
            "--file",
            parallel_makefile.path,
            "yosys-dependencies",
            "do-yosys-partition",
            "SYNTH_PARTITION_SCRIPT=" + ctx.file._synth_partition_script.path,
        ] + sdc_overrides,
        command = " && ".join(top_commands),
        env = base_env | partition_env_extra | {
            "SYNTH_PARTITION_ID": "top",
            "SYNTH_NUM_PARTITIONS": str(num_partitions),
            "SYNTH_TCL": ctx.file._synth_tcl.path,
        },
        inputs = top_partition_inputs,
        outputs = [top_output],
        tools = yosys_and_flow_tools,
        progress_message = "Synthesizing top module %s" % module_top(ctx),
    )

    # Action 5: merge partition outputs + top module → 1_2_yosys.v
    all_parts = partition_outputs + [top_output]
    ctx.actions.run_shell(
        command = "cat {inputs} > {output}".format(
            inputs = " ".join([p.path for p in all_parts]),
            output = synth_outputs["1_2_yosys.v"].path,
        ),
        inputs = all_parts,
        outputs = [synth_outputs["1_2_yosys.v"]],
        progress_message = "Merging synthesized partitions for %s" % module_top(ctx),
    )

    # Action 5: SDC copy → 1_2_yosys.sdc
    # Uses wrapper Makefile so SDC_FILE is resolved from DESIGN_CONFIG.
    # A cp of the raw SDC: make parse (config + platform includes) plus
    # the SDC itself — no design data, no macro collateral.
    ctx.actions.run_shell(
        arguments = [
            "--file",
            parallel_makefile.path,
            "do-yosys-sdc-copy",
        ],
        command = "{make} $@".format(make = ctx.executable._make.path),
        env = base_env,
        inputs = depset(
            [config, parallel_makefile] + ctx.files.extra_configs,
            transitive = [
                sdc_only_inputs,
                pdk_inputs(ctx),
            ],
        ),
        outputs = [synth_outputs["1_2_yosys.sdc"]],
        tools = yosys_and_flow_tools,
        progress_message = "Generating SDC for %s" % module_top(ctx),
    )

    # Action 6: ODB generation → 1_synth.odb
    # do-1_synth is a .PHONY target that runs synth_odb.tcl to read the
    # merged Verilog and produce the ODB; it does not trigger yosys rebuilds.
    if save_odb:
        # No generation_commands for 1_synth.odb/.sdc: they are the
        # step's contract; a missing one must fail the action, not be
        # papered over with a touched empty file.
        odb_commands = [_make_cmd(ctx)] + [
            # flow.sh writes logs/1_synth.json during do-1_synth; guarantee a
            # parseable declared output either way (genMetrics json.load()s it).
            "[ -s {p} ] || echo '{{}}' > {p}".format(p = f.path)
            for f in synth_jsons
        ]
        ctx.actions.run_shell(
            arguments = [
                "--file",
                parallel_makefile.path,
                "do-1_synth",
            ],
            command = " && ".join(odb_commands),
            env = base_env,
            inputs = depset(
                [
                    synth_outputs["1_2_yosys.v"],
                    synth_outputs["1_2_yosys.sdc"],
                    config,
                    parallel_makefile,
                ] + ctx.files.extra_configs,
                transitive = [
                    data_inputs(ctx),
                    pdk_inputs(ctx),
                    deps_inputs(ctx, gds = False),
                ],
            ),
            outputs = [synth_outputs["1_synth.odb"], synth_outputs["1_synth.sdc"]] + synth_jsons,
            tools = yosys_and_flow_tools,
            progress_message = "Building synth ODB for %s" % module_top(ctx),
        )

    # Stub outputs that the serial path produces but parallel does not
    for name in ["mem.json"]:
        ctx.actions.write(output = synth_outputs[name], content = "")
    for f in synth_logs + synth_reports:
        ctx.actions.write(output = f, content = "")

    return validated_kept_macros_json

def _yosys_impl(ctx):
    all_arguments = merge_arguments(
        data_arguments(ctx) |
        required_arguments(ctx),
        orfs_additional_arguments(
            [dep[OrfsInfo] for dep in ctx.attr.deps],
            use_pre_layout = True,
        ),
    )

    analysis_args = config_arguments(ctx, all_arguments)
    analysis_json = declare_artifact(ctx, "results", "1_synth.analysis.json")
    ctx.actions.write(
        output = analysis_json,
        content = json.encode(analysis_args),
    )

    filter_json = write_stage_filter(ctx, "results", "1_synth", ["synth"])

    config = declare_artifact(ctx, "results", "1_synth.mk")
    all_jsons = [analysis_json] + ctx.files.extra_arguments

    args = [
        ctx.file._merge_arguments.path,
        config.path,
        "--filter",
        filter_json.path,
    ]
    for f in ctx.files.extra_configs:
        args.extend(["--include", f.path])
    args.extend([f.path for f in all_jsons])

    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = args,
        inputs = all_jsons + [ctx.file._merge_arguments, filter_json] + ctx.files.extra_configs,
        outputs = [config],
    )

    # Canonicalize only needs each macro's port interface to blackbox it, not
    # its PnR'd lef/lib/gds. The caller-named macros (canon_blackbox_macros)
    # are blackboxed by name at slang read time via `--blackboxed-module`,
    # appended to the design's SYNTH_SLANG_ARGS in a scoped canonicalize
    # config: the interface comes from the design's own Verilog, the module
    # keeps its bare name (so downstream OpenROAD's LEF-master lookup matches),
    # and the macro's abstract files drop out of the canonicalize action
    # entirely — so canonicalize no longer waits on their place-and-route.
    # Gated on kept_macros scoping so non-scoped bazel-orfs designs keep
    # today's behavior.
    #
    # Blackboxing AFTER elaboration (a yosys `blackbox` pass) was rejected:
    # slang mangles elaborated module names to <bare>$<instance-path>, which
    # then fails the ODB LEF-master lookup (ORD-2013). Blackboxing at read
    # keeps the bare name.
    canon_config = config
    canon_deps = deps_inputs(ctx, gds = False)
    if ctx.attr.kept_macros_enabled and ctx.attr.canon_blackbox_macros:
        # The caller names exactly the macros to blackbox at canonicalize
        # (canon_blackbox_macros — e.g. the SHARED_LOGIC macros). They are
        # blackboxed by name via slang --blackboxed-module, so canonicalize
        # reads no liberty for them and does not wait on their PnR. Every
        # other dep (memory macros etc.) stays liberty-blackboxed via its
        # cheap pre-layout lib — blackboxing those by name would instead
        # elaborate their bodies into every partition slice.
        blackbox = {m: True for m in ctx.attr.canon_blackbox_macros}
        hardened_names = [
            dep[TopInfo].module_top
            for dep in ctx.attr.deps
            if dep[TopInfo].module_top in blackbox
        ]
        soft_infos = [
            dep[OrfsInfo]
            for dep in ctx.attr.deps
            if dep[TopInfo].module_top not in blackbox
        ]
        if hardened_names:
            canon_arguments = merge_arguments(
                data_arguments(ctx) | required_arguments(ctx),
                orfs_additional_arguments(soft_infos, use_pre_layout = True),
            )

            # Append --blackboxed-module for each hardened macro to the
            # design's existing SYNTH_SLANG_ARGS rather than replacing it:
            # the design relies on flags there (e.g.
            # --disable-instance-caching=false, which dedups identical module
            # instances) — clobbering them bloats the canonicalize ~3x.
            blackbox_slang = " ".join([
                "--blackboxed-module " + n
                for n in hardened_names
            ])
            existing_slang = canon_arguments.get("SYNTH_SLANG_ARGS", "")
            canon_arguments = canon_arguments | {
                "SYNTH_SLANG_ARGS": (existing_slang + " " + blackbox_slang) if existing_slang else blackbox_slang,
            }

            canon_analysis_args = config_arguments(ctx, canon_arguments)
            canon_analysis_json = declare_artifact(ctx, "results", "1_1_yosys_canonicalize.analysis.json")
            ctx.actions.write(
                output = canon_analysis_json,
                content = json.encode(canon_analysis_args),
            )

            canon_config = declare_artifact(ctx, "results", "1_1_yosys_canonicalize.mk")
            canon_jsons = [canon_analysis_json] + ctx.files.extra_arguments

            canon_args = [
                ctx.file._merge_arguments.path,
                canon_config.path,
                "--filter",
                filter_json.path,
            ]
            for f in ctx.files.extra_configs:
                canon_args.extend(["--include", f.path])
            canon_args.extend([f.path for f in canon_jsons])

            ctx.actions.run(
                executable = ctx.executable._python,
                arguments = canon_args,
                inputs = canon_jsons + [ctx.file._merge_arguments, filter_json] + ctx.files.extra_configs,
                outputs = [canon_config],
            )

            # No .gds: canonicalize reads liberty to blackbox, never GDS.
            canon_deps = depset(
                [info.lef for info in soft_infos if info.lef] +
                [info.lib for info in soft_infos if info.lib] +
                [
                    info.lib_pre_layout
                    for info in soft_infos
                    if info.lib_pre_layout
                ],
            )

    # Engine selection: SYNTH_USE_SYN=1 in the merged arguments switches the
    # synthesis stage from the yosys flow to OpenROAD's built-in synthesizer
    # (the Makefile's synth_syn path). Analysis-time only: the value must
    # come through arguments/stage_arguments, not extra_arguments .json files.
    use_syn = all_arguments.get("SYNTH_USE_SYN") == "1"

    # Clock-period extraction. The yosys side never reads the raw SDC:
    # synth_preamble.tcl consumes only SDC_FILE_CLOCK_PERIOD (the abc -D
    # value), which ORFS's do-sdc-clock-period target derives from the SDC
    # in a make blink. Run that derivation as its own cheap action so a
    # period-preserving SDC edit re-runs only this step; the expensive
    # yosys actions get SDC_FILE_CLOCK_PERIOD=<artifact> and SDC_FILE=
    # (empty — variables.mk guards every SDC_FILE use with $(wildcard))
    # on the make command line and the raw SDC dropped from their inputs.
    # SDC_FILE_CLOCK_PERIOD is not in variables.yaml, so it must ride the
    # command line, not the config. The SYNTH_USE_SYN engine bypasses
    # yosys and reads SDC_FILE directly, so it keeps the raw SDC.
    sdc_file_raw = all_arguments.get("SDC_FILE")
    sdc_path = ctx.expand_location(sdc_file_raw, ctx.attr.data) if sdc_file_raw else None

    # The raw SDC as File(s) — for the cheap actions that read ONLY it
    # (clock-period extraction, sdc-copy). Handing them the full data set
    # would re-run them, harmlessly but noisily, on every data edit.
    # Falls back to the full data set when the SDC_FILE path cannot be
    # matched to a data file (a literal path spelled without $(location)).
    sdc_files = [f for f in data_inputs(ctx).to_list() if f.path == sdc_path]
    sdc_only_inputs = depset(sdc_files) if sdc_files else data_inputs(ctx)
    clock_period = None
    sdc_overrides = []
    synth_data_inputs = data_inputs(ctx)
    if sdc_path and not use_syn:
        clock_period = declare_artifact(ctx, "results", "clock_period.txt")
        ctx.actions.run_shell(
            arguments = [
                "--file",
                ctx.file._makefile_yosys.path,
                "do-sdc-clock-period",
                "SDC_FILE_CLOCK_PERIOD=" + clock_period.path,
            ],
            command = _make_cmd(ctx),
            env = verilog_arguments([]) |
                  yosys_environment(ctx) |
                  config_environment(config),
            # Make parse (config + platform includes) plus the SDC the
            # period is regexed out of — nothing else is opened.
            inputs = depset(
                [config] + ctx.files.extra_configs,
                transitive = [
                    sdc_only_inputs,
                    pdk_inputs(ctx),
                ],
            ),
            outputs = [clock_period],
            tools = yosys_inputs(ctx),
            progress_message = "Extracting clock period from SDC for %s" % module_top(ctx),
        )
        sdc_overrides = [
            "SDC_FILE_CLOCK_PERIOD=" + clock_period.path,
            "SDC_FILE=",
        ]
        synth_data_inputs = data_inputs_excluding(ctx, sdc_path)

    canon_logs = declare_artifacts(ctx, "logs", ["1_1_yosys_canonicalize.log"])

    canon_output = declare_artifact(ctx, "results", CANON_OUTPUT)

    if use_syn:
        # OpenROAD-SYN has no yosys canonicalization; stub its outputs
        # (lint-mode precedent) so the provider/deploy tail below is
        # identical in both engine modes. genMetrics.py treats the empty
        # RTLIL like a missing file when hashing.
        for f in canon_logs + [canon_output]:
            ctx.actions.write(output = f, content = "")
    else:
        # SYNTH_NETLIST_FILES will not create an .rtlil file or reports, so we need
        # an empty placeholder in that case.
        commands = [_make_cmd(ctx)] + generation_commands(
            canon_logs + [canon_output],
        )

        ctx.actions.run_shell(
            arguments = [
                "--file",
                ctx.file._makefile_yosys.path,
                "yosys-dependencies",
                "do-yosys-canonicalize",
            ] + sdc_overrides,
            command = EXPAND_VERILOG_DIRS + " && ".join(commands),
            env = verilog_arguments(ctx.files.verilog_files) |
                  yosys_environment(ctx) |
                  config_environment(canon_config),
            inputs = depset(
                [canon_config] + ([clock_period] if clock_period else []) +
                ctx.files.verilog_files + ctx.files.extra_configs,
                transitive = [
                    synth_data_inputs,
                    pdk_inputs(ctx),
                    canon_deps,
                ],
            ),
            outputs = [canon_output] + canon_logs,
            tools = yosys_inputs(ctx),
            progress_message = "Canonicalizing RTL for %s" % module_top(ctx),
        )

    num_partitions = int(all_arguments.get("SYNTH_NUM_PARTITIONS", "0"))
    if num_partitions == 0 and all_arguments.get("SYNTH_KEEP_MODULES"):
        # SYNTH_KEEP_MODULES implies parallel synthesis; default to 1 partition
        # when NUM_CPUS-based auto-detection hasn't run (direct orfs_synth call).
        kept_count = len(keep_modules(all_arguments))
        num_partitions = max(1, kept_count)
    if use_syn:
        # Parallel/hierarchical synthesis is a yosys-flow concept; the
        # Makefile's SYNTH_USE_SYN path ignores SYNTH_KEEP_MODULES and
        # SYNTH_NUM_PARTITIONS (e.g. asap7/swerv_wrapper carries both
        # with SYNTH_USE_SYN=1), so never take the partitioned branch.
        num_partitions = 0

    save_odb = ctx.attr.save_odb
    if use_syn and not save_odb:
        fail("SYNTH_USE_SYN=1 always writes 1_synth.odb; save_odb=False is " +
             "not supported in " + str(ctx.label))

    # logs/1_synth.json: metrics that flow.sh's `openroad -metrics` writes
    # during do-1_synth. Declared so generate_metadata (which merges
    # logs/1_*.json via genMetrics.py) sees the synth__* metrics.
    if use_syn:
        synth_logs = declare_artifacts(ctx, "logs", ["1_synth.log"])
        synth_jsons = declare_artifacts(ctx, "logs", ["1_synth.json"])
        synth_outputs = {o: declare_artifact(ctx, "results", o) for o in SYN_OUTPUTS}
    else:
        synth_logs = declare_artifacts(ctx, "logs", ["1_2_yosys.log", "1_2_yosys_metrics.log"] + (["1_synth.log"] if save_odb else []))
        synth_jsons = declare_artifacts(ctx, "logs", ["1_synth.json"] if save_odb else [])
        synth_outputs = {}
        for output in SYNTH_OUTPUTS + (["1_synth.odb", "1_synth.sdc"] if save_odb else []):
            synth_outputs[output] = declare_artifact(ctx, "results", output)

    synth_reports = declare_artifacts(ctx, "reports", SYNTH_REPORTS)

    variables = declare_artifact(ctx, "results", "1_synth.vars")

    # Populated only by the parallel-synth path when kept_macros validation
    # is enabled; surfaced via the kept_macros_validation output group.
    validated_kept_macros_json = None

    # Ensure declared metrics .json outputs exist and are parseable even if
    # make did not write them; genMetrics.py json.load()s every 1_*.json, so
    # the fallback must be "{}" rather than a touched empty file.
    json_fallback = [
        "[ -s {p} ] || echo '{{}}' > {p}".format(p = f.path)
        for f in synth_jsons
    ]

    if ctx.attr.lint:
        # Lint mode: only canonicalization runs; stub remaining synth outputs.
        for f in synth_outputs.values() + synth_logs + synth_reports + [variables]:
            ctx.actions.write(output = f, content = "")
        for f in synth_jsons:
            ctx.actions.write(output = f, content = "{}")
    elif use_syn:
        # OpenROAD-SYN synthesis: one openroad invocation (synth_syn.tcl via
        # do-1_synth) consumes the staged Verilog sources directly, so
        # VERILOG_FILES is set from ctx.files.verilog_files exactly like the
        # yosys canonicalize action does. Uses the full flow makefile
        # filegroup (synth_syn.tcl sources load.tcl etc.), no yosys tools.
        commands = [_make_cmd(ctx)] + generation_commands(
            synth_logs + synth_reports,
        ) + json_fallback
        ctx.actions.run_shell(
            arguments = [
                "--file",
                ctx.file._makefile.path,
                "do-1_synth",
            ],
            command = EXPAND_VERILOG_DIRS + " && ".join(commands),
            env = verilog_arguments(ctx.files.verilog_files) |
                  flow_environment(ctx) |
                  config_environment(config),
            inputs = depset(
                [config] + ctx.files.verilog_files + ctx.files.extra_configs,
                transitive = [
                    data_inputs(ctx),
                    pdk_inputs(ctx),
                    deps_inputs(ctx, gds = False),
                ],
            ),
            outputs = synth_outputs.values() + synth_logs + synth_jsons + synth_reports,
            tools = flow_inputs(ctx),
            progress_message = "OpenROAD-SYN synthesis for %s" % module_top(ctx),
        )
    elif num_partitions > 0:
        validated_kept_macros_json = _yosys_parallel_synth(ctx, config, canon_output, synth_outputs, synth_logs, synth_jsons, synth_reports, num_partitions, save_odb, all_arguments, clock_period, sdc_overrides, synth_data_inputs, sdc_only_inputs)
    else:
        # Serial path, split into three actions mirroring the parallel
        # path so the raw SDC feeds only the cheap sdc-copy step:
        #   1. sdc-copy: raw SDC -> 1_2_yosys.sdc (empty placeholder for
        #      SYNTH_NETLIST_FILES designs with no SDC).
        #   2. do-yosys: the expensive synthesis; reads the canonicalized
        #      RTLIL and clock_period.txt, never the raw SDC.
        #   3. do-1_synth (save_odb only): 1_synth.odb/.sdc from
        #      1_2_yosys.v/.sdc.
        # SYNTH_NETLIST_FILES will not create an .rtlil file, logs,
        # reports or mem.json, so touch empty placeholders for those.
        # Primary artifacts (1_2_yosys.v/.sdc, 1_synth.odb/.sdc) are
        # deliberately excluded: a missing one must fail the action,
        # not be papered over with a touched empty file.
        serial_env = (
            verilog_arguments([]) |
            flow_environment(ctx) |
            yosys_environment(ctx) |
            config_environment(config)
        )
        serial_tools = depset(transitive = [yosys_inputs(ctx), flow_inputs(ctx)])
        if sdc_path:
            ctx.actions.run_shell(
                command = "cp {sdc} {out}".format(
                    sdc = sdc_path,
                    out = synth_outputs["1_2_yosys.sdc"].path,
                ),
                # A cp of the raw SDC reads exactly one file.
                inputs = sdc_only_inputs,
                outputs = [synth_outputs["1_2_yosys.sdc"]],
                progress_message = "Generating SDC for %s" % module_top(ctx),
            )
        else:
            ctx.actions.write(output = synth_outputs["1_2_yosys.sdc"], content = "")

        yosys_logs = [f for f in synth_logs if f.basename != "1_synth.log"]
        odb_logs = [f for f in synth_logs if f.basename == "1_synth.log"]
        yosys_commands = [_make_cmd(ctx)] + generation_commands(
            yosys_logs + synth_reports + [synth_outputs["mem.json"]],
        )
        ctx.actions.run_shell(
            arguments = [
                "--file",
                ctx.file._makefile_yosys.path,
                "yosys-dependencies",
                "do-yosys",
            ] + sdc_overrides,
            command = " && ".join(yosys_commands),
            env = serial_env,
            inputs = depset(
                [canon_output, config] +
                ([clock_period] if clock_period else []) +
                ctx.files.extra_configs,
                transitive = [
                    synth_data_inputs,
                    pdk_inputs(ctx),
                    deps_inputs(ctx, gds = False),
                ],
            ),
            outputs = [synth_outputs["1_2_yosys.v"], synth_outputs["mem.json"]] +
                      yosys_logs + synth_reports,
            tools = serial_tools,
        )

        if save_odb:
            odb_commands = [_make_cmd(ctx)] + generation_commands(odb_logs) + json_fallback
            ctx.actions.run_shell(
                arguments = [
                    "--file",
                    ctx.file._makefile_yosys.path,
                    "do-1_synth",
                ],
                command = " && ".join(odb_commands),
                env = serial_env,
                inputs = depset(
                    [
                        synth_outputs["1_2_yosys.v"],
                        synth_outputs["1_2_yosys.sdc"],
                        config,
                    ] + ctx.files.extra_configs,
                    transitive = [
                        data_inputs(ctx),
                        pdk_inputs(ctx),
                        deps_inputs(ctx, gds = False),
                    ],
                ),
                outputs = [synth_outputs["1_synth.odb"], synth_outputs["1_synth.sdc"]] +
                          odb_logs + synth_jsons,
                tools = serial_tools,
                progress_message = "Building synth ODB for %s" % module_top(ctx),
            )

    if not ctx.attr.lint:
        ctx.actions.run_shell(
            arguments = [
                "--file",
                ctx.file._makefile_yosys.path,
                "print-LIB_FILES",
                # A make-parse-only action: LIB_FILES never involves the
                # SDC, so don't let raw-SDC edits re-run it (the input set
                # below excludes the SDC accordingly).
                "SDC_FILE=",
            ],
            command = """
            {make} $@ > {out}
            """.format(make = ctx.executable._make.path, out = variables.path),
            env = verilog_arguments([]) |
                  flow_environment(ctx) |
                  yosys_environment(ctx) |
                  config_environment(config),
            # A pure make-variable expansion: parses the config and the
            # platform includes, opens no design file — neither the
            # canonicalized RTLIL nor the data/macro collateral.
            inputs = depset(
                [config] + ctx.files.extra_configs,
                transitive = [
                    pdk_inputs(ctx),
                ],
            ),
            outputs = [variables],
            tools = depset(transitive = [flow_inputs(ctx)]),
        )

    # 1_2_yosys.sdc is a verbatim copy of the raw SDC feeding do-1_synth —
    # an intermediate, not a deliverable (nothing in the repo consumes it,
    # and a deployed re-run regenerates it via ORFS's own file rule).
    # Keeping it in DefaultInfo.files would land it in every downstream
    # stage's action inputs (ctx.files.src → source_inputs) and re-run
    # floorplan+ on every raw-SDC edit; the downstream contract is the
    # canonicalized 1_synth.sdc.
    #
    # 1_synth.vars likewise leaves DefaultInfo.files: no stage reads it,
    # so it has no business in downstream action inputs — but it MUST
    # stay in the runfiles and the deploy set: odb-debug-style tooling
    # recovers LIB_FILES by globbing *.vars in a synth target's runfiles
    # and fails silently without it.
    outputs = [canon_output] + [
        f
        for name, f in synth_outputs.items()
        if name != "1_2_yosys.sdc"
    ]

    # Write synth's data_arguments to a JSON so downstream stages
    # inherit synth-time variables (SDC_FILE, VERILOG_FILES, SYNTH_*)
    # via OrfsInfo.arguments propagation. Without this, `bazel run :_final
    # -- SYNTH_NETLIST_FILES=...` (used by //:make-yosys-netlist to feed
    # make's netlist into the bazel flow) fails inside the resulting
    # re-synth: synth_preamble.tcl reads $::env(SDC_FILE) but _final's
    # args.mk only contains openroad-stage data_arguments.
    synth_args_json = declare_artifact(ctx, "results", "1_synth.args.json")
    synth_all_args = merge_arguments(
        data_arguments(ctx) |
        required_arguments(ctx),
        orfs_additional_arguments(
            [dep[OrfsInfo] for dep in ctx.attr.deps],
            use_pre_layout = True,
        ),
    ) | verilog_arguments(ctx.files.verilog_files)
    ctx.actions.write(
        output = synth_args_json,
        content = json.encode(synth_all_args),
    )

    config_short = declare_artifact(ctx, "results", "1_synth.short.mk")
    short_all_args = merge_arguments(
        data_arguments(ctx) |
        required_arguments(ctx),
        orfs_additional_arguments(
            [dep[OrfsInfo] for dep in ctx.attr.deps],
            use_pre_layout = True,
        ),
    ) | verilog_arguments(ctx.files.verilog_files)

    short_analysis_args = config_arguments(ctx, hack_away_prefix(short_all_args, config_short.root.path))
    short_analysis_json = declare_artifact(ctx, "results", "1_synth.short.analysis.json")
    ctx.actions.write(
        output = short_analysis_json,
        content = json.encode(short_analysis_args),
    )

    short_args = [
        ctx.file._merge_arguments.path,
        config_short.path,
        "--filter",
        filter_json.path,
    ]
    for f in ctx.files.extra_configs:
        short_args.extend(["--include", f.short_path])
    short_args.append(short_analysis_json.path)
    short_args.extend([f.path for f in ctx.files.extra_arguments])

    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = short_args,
        inputs = [short_analysis_json] + ctx.files.extra_arguments + [ctx.file._merge_arguments, filter_json] + ctx.files.extra_configs,
        outputs = [config_short],
    )

    make = _create_make_script(
        ctx,
        "make_{}_1_synth".format(ctx.attr.name),
        yosys_substitutions(ctx),
    )

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    _expand_deploy_template(
        ctx,
        exe,
        config = config_short,
        make = make,
        genfiles = [config_short, variables] + outputs + canon_logs + synth_logs + synth_jsons,
    )

    # Collect all files needed for deployment (tools, PDK, stage inputs).
    # Uses flow_inputs (CLI openroad), not flow_runfiles: the tarball and
    # the OrfsDepInfo.runfiles consumed by downstream rules (orfs_step,
    # orfs_deploy_srcs) are headless paths. openroad_qt is only added to
    # DefaultInfo.runfiles below so `bazelisk run :synth gui_synth` works.
    deploy_files = depset(
        [config_short, make] +
        ctx.files.verilog_files +
        ctx.files.extra_configs,
        transitive = [
            flow_inputs(ctx),
            yosys_inputs(ctx),
            data_inputs(ctx),
            pdk_inputs(ctx),
            deps_inputs(ctx),
        ],
    )

    # Portable tarball for on-demand deployment.
    deps_tar = _package_stage(
        ctx,
        config = config_short,
        make = make,
        runfiles_depset = deploy_files,
    )

    # Legacy deploy script (used by orfs_step for bazel run).
    deps_exe = declare_artifact(ctx, "results", ctx.attr.name + "_deps_deploy.sh")
    _expand_deploy_template(
        ctx,
        deps_exe,
        config = config_short,
        make = make,
        genfiles = [config_short] + ctx.files.verilog_files + ctx.files.extra_configs,
        name = ctx.attr.name + "_deps",
    )

    _runfiles_files = [config_short, make, variables] + outputs + canon_logs + synth_logs + synth_jsons + ctx.files.extra_configs + ctx.files.data
    _runfiles_common = depset(
        transitive = [
            deps_inputs(ctx),
            pdk_inputs(ctx),
        ],
    )
    return [
        DefaultInfo(
            executable = exe,
            files = depset(outputs),
            # default_runfiles includes openroad_qt so `bazelisk run
            # :synth gui_synth` finds the Qt-linked binary in the
            # deployed temp folder. data_runfiles deliberately omits
            # openroad_qt so downstream rules that consume this stage
            # via `data =` (e.g. orfs_generate_metadata) do not drag
            # the Qt binary into their build action graph.
            default_runfiles = ctx.runfiles(
                _runfiles_files,
                transitive_files = depset(
                    transitive = [flow_runfiles(ctx), _runfiles_common],
                ),
            ),
            data_runfiles = ctx.runfiles(
                _runfiles_files,
                transitive_files = depset(
                    transitive = [flow_inputs(ctx), _runfiles_common],
                ),
            ),
        ),
        OutputGroupInfo(
            logs = depset(canon_logs + synth_logs),
            reports = depset([]),
            deps = depset([deps_tar]),
            kept_macros_validation = depset(
                [validated_kept_macros_json] if validated_kept_macros_json else [],
            ),
            # 1_2_yosys.sdc and 1_synth.vars left DefaultInfo.files (see
            # the outputs comment above) but stay inspectable on demand:
            # bazelisk build --output_groups=<basename> <synth target>.
            **{
                f.basename: depset([f])
                for f in [config, variables] + outputs + (
                    [synth_outputs["1_2_yosys.sdc"]] if "1_2_yosys.sdc" in synth_outputs else []
                )
            }
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            renames = [],
            # Include the stage data (sources= files) like the PnR stage
            # rule does: orfs_arguments/orfs_run consumers stage
            # OrfsDepInfo.files, and the synth config can reference
            # sources= paths (e.g. LAYER_PARASITICS_FILE) that load.tcl
            # sources at load_design time.
            #
            # EXCEPT the raw SDC: downstream's contract is the previous
            # stage's written .odb/.sdc (for floorplan, the canonicalized
            # 1_synth.sdc via OrfsInfo.sdc — write_sdc resolves every
            # dependency the raw SDC_FILE may source), and nothing after
            # synth reads SDC_FILE (open.tcl's fallback never fires once
            # an N_*.sdc exists). Keeping it here would feed it into
            # floorplan's inputs via source_inputs() and re-run floorplan
            # on every raw-SDC edit, period-preserving or not.
            files = depset(
                [config_short] +
                [f for f in ctx.files.data if f.path != sdc_path] +
                ctx.files.extra_configs,
            ),
            runfiles = ctx.runfiles(transitive_files = deploy_files),
        ),
        OrfsInfo(
            stage = "1_synth",
            config = config,
            variant = ctx.attr.variant,
            odb = synth_outputs.get("1_synth.odb"),
            sdc = synth_outputs.get("1_synth.sdc"),
            gds = None,
            lef = None,
            lib = None,
            lib_pre_layout = None,
            additional_gds = depset(
                [dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds],
            ),
            additional_lefs = depset(
                [dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef],
            ),
            additional_libs = depset(
                [dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib],
            ),
            additional_libs_pre_layout = depset(
                [
                    (dep[OrfsInfo].lib_pre_layout or dep[OrfsInfo].lib)
                    for dep in ctx.attr.deps
                    if (dep[OrfsInfo].lib_pre_layout or dep[OrfsInfo].lib)
                ],
            ),
            arguments = depset([synth_args_json]),
        ),
        ctx.attr.pdk[PdkInfo],
        TopInfo(
            module_top = ctx.attr.module_top,
        ),
        LoggingInfo(
            log_dir = artifact_dir(ctx, "logs"),
            logs = depset(canon_logs + synth_logs),
            reports = depset(synth_reports),
            drcs = depset([]),
            jsons = depset(synth_jsons),
        ),
    ]

orfs_synth_rule = rule(
    implementation = _yosys_impl,
    attrs = yosys_attrs() |
            synth_attrs() |
            {
                "_stage": attr.string(
                    default = "synth",
                ),
                "save_odb": attr.bool(
                    default = True,
                    doc = "Whether to save the ODB file from synthesis. Useful to disable if " +
                          "only Verilog output is needed or possible when doing hierarchical " +
                          "synthesis as some files could be blackboxed.",
                ),
                "_parallel_synth_makefile": attr.label(
                    allow_single_file = True,
                    default = Label("//:parallel_synth.mk"),
                ),
                "_synth_keep_script": attr.label(
                    allow_single_file = True,
                    default = Label("//:synth_keep.tcl"),
                ),
                "_synth_partition_script": attr.label(
                    allow_single_file = True,
                    default = Label("//:synth_partition.sh"),
                ),
                "filter_script": attr.label(
                    allow_single_file = True,
                ),
                "_synth_canonicalize_module_script": attr.label(
                    allow_single_file = True,
                    default = Label("//:synth_canonicalize_module.tcl"),
                ),
                "_rtlil_kept_modules": attr.label(
                    allow_single_file = True,
                    default = Label("//:rtlil_kept_modules.py"),
                ),
                "_rtlil_kept_macros": attr.label(
                    allow_single_file = True,
                    default = Label("//:rtlil_kept_macros.py"),
                ),
                "_synth_tcl": attr.label(
                    allow_single_file = True,
                    default = Label("@orfs//flow:scripts/synth.tcl"),
                ),
            },
    provides = [
        DefaultInfo,
        OutputGroupInfo,
        OrfsDepInfo,
        OrfsInfo,
        PdkInfo,
        TopInfo,
        LoggingInfo,
    ],
    executable = True,
)

# --- Make-based stage implementation ---

_PRE_LAYOUT_STAGES = ("2_floorplan", "3_place")

def _make_impl(
        ctx,
        stage,
        steps,
        forwarded_names = [],
        result_names = [],
        object_names = [],
        log_names = [],
        report_names = [],
        extra_arguments = {},
        json_names = [],
        drc_names = [],
        substep_names = [],
        lib_pre_layout = None,
        rename_data = False):
    """
    Implementation function for the OpenROAD-flow-scripts stages.

    Args:
      ctx: The context object.
      stage: The stage name.
      steps: Makefile targets to run.
      forwarded_names: The names of files to be forwarded from `src`.
      result_names: The names of the result files.
      object_names: The names of the object files.
      log_names: The names of the log files.
      report_names: The names of the report files.
      extra_arguments: Extra arguments to add to the configuration.
      json_names: The names of the JSON files.
      drc_names: The names of the DRC files.
      substep_names: Substep names whose intermediate .odb files should be
          captured as additional action outputs in per-substep output groups.
      rename_data: Also apply cross-variant input renaming to data and
          logging inputs, not just `src` results. Needed when a stage of
          a sub-variant (e.g. the fast synthesis QoR pre-check's
          "<variant>_synth") consumes logs/jsons staged under the parent
          variant's tree — make and genMetrics.py resolve those paths
          from this stage's FLOW_VARIANT.
      lib_pre_layout: Optional pre-layout .lib File to expose on this
          stage's OrfsInfo. Used by orfs_abstract to surface the post-place
          .lib alongside the canonical (post-final) one.

    Returns:
        A list of providers. The returned PdkInfo and TopInfo providers are taken from the first
        target of a ctx.attr.srcs list.
    """
    use_pre_layout = stage in _PRE_LAYOUT_STAGES
    all_arguments = merge_arguments(
        extra_arguments |
        data_arguments(ctx) |
        required_arguments(ctx),
        orfs_additional_arguments(
            [ctx.attr.src[OrfsInfo]],
            use_pre_layout = use_pre_layout,
        ),
    )

    # Write this stage's analysis arguments to .json for downstream stages, then
    # merge inherited .json files and this stage's .json into the final .mk.
    # Precedence (later wins in merge_arguments.py): inherited < stage < extra.
    analysis_args = config_arguments(ctx, all_arguments)
    analysis_json = declare_artifact(ctx, "results", stage + ".analysis.json")
    ctx.actions.write(
        output = analysis_json,
        content = json.encode(analysis_args),
    )
    inherited_jsons = ctx.attr.src[OrfsInfo].arguments.to_list()
    extra_arg_files = ctx.files.extra_arguments
    all_jsons = inherited_jsons + [analysis_json] + extra_arg_files

    # Which canonical stages own this action's variables. `stages` is set by
    # the squashed multi-stage rule; every other rule carries a single
    # `_stage`. Both are declared, never sniffed out of the ORFS stage name
    # (`stage` here is an ORFS name like "2_floorplan", not a stage key). Name
    # sniffing used to be the fallback, and a name it failed to resolve fell
    # through to an empty allow-list — every known variable silently dropped
    # from the stage's config. An unresolvable stage is an error instead.
    if hasattr(ctx.attr, "stages") and ctx.attr.stages:
        filter_stages = ctx.attr.stages
    elif hasattr(ctx.attr, "_stage") and ctx.attr._stage in ALL_STAGE_TO_VARIABLES:
        filter_stages = [ctx.attr._stage]
    else:
        fail(
            "Cannot resolve the canonical stage(s) for '{stage}'. ".format(stage = stage) +
            "Set the rule's `stages` attribute (or its `_stage` default) to " +
            "one of: {known}.".format(known = ", ".join(ALL_STAGES)),
        )

    filter_json = write_stage_filter(ctx, "results", stage, filter_stages)

    config = declare_artifact(ctx, "results", stage + ".mk")
    args = [
        ctx.file._merge_arguments.path,
        config.path,
        "--filter",
        filter_json.path,
    ]
    for f in ctx.files.extra_configs:
        args.extend(["--include", f.path])
    args.extend([f.path for f in all_jsons])

    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = args,
        inputs = all_jsons + [ctx.file._merge_arguments, filter_json] + ctx.files.extra_configs,
        outputs = [config],
    )

    results = declare_artifacts(ctx, "results", result_names)
    objects = declare_artifacts(ctx, "objects", object_names)
    logs = declare_artifacts(ctx, "logs", log_names)
    jsons = declare_artifacts(ctx, "logs", json_names)
    reports = declare_artifacts(ctx, "reports", report_names)
    drcs = declare_artifacts(ctx, "reports", drc_names)
    substep_odbs = declare_artifacts(
        ctx,
        "results",
        [s + ".odb" for s in substep_names],
    )

    forwards = [f for f in ctx.files.src if f.basename in forwarded_names]

    info = {}
    for file in forwards + results:
        info[file.extension] = file

    all_outputs = results + objects + logs + reports + jsons + drcs + substep_odbs
    if ctx.attr.lint and stage in ("generate_metadata", "update_rules"):
        # Lint mode: metadata/update parse real stage outputs that are stubs
        # in lint mode, so stub their outputs instead of running Make.
        json_set = {f: True for f in jsons + reports}
        for f in all_outputs:
            ctx.actions.write(output = f, content = "{}" if f in json_set else "")
    else:
        rename_candidates = ctx.files.src
        if rename_data:
            rename_candidates = depset(
                ctx.files.src,
                transitive = [data_inputs(ctx), source_inputs(ctx)],
            ).to_list()
        commands = (
            generation_commands(reports + logs + jsons + drcs + substep_odbs) +
            input_commands(renames(ctx, rename_candidates)) +
            [_make_cmd(ctx)]
        )

        # Stage only the macro .lib variant this stage's args.mk references
        # (mirrors the orfs_additional_arguments(use_pre_layout) selection
        # above). Squashed multi-stage actions span both timing domains,
        # so they keep both variants.
        lib_selection = use_pre_layout
        if getattr(ctx.attr, "stages", None) and len(ctx.attr.stages) > 1:
            lib_selection = None

        # Macro .gds is read only by the GDS-emitting make steps (the
        # klayout wrap under do-gds / do-final); a squashed action ending
        # at final carries stage == "6_final" and keeps it.
        include_gds = stage in ("6_final", "6_gds")

        # The src chain's metrics .json / report files are read only by
        # genMetrics.py — the metadata stages declare them; the PnR make
        # steps never open an upstream stage's .json or .rpt, and while
        # the jsons are supposed to be byte-stable, OpenROAD is not
        # trusted on that: consumers state the dependency, nobody gets
        # fed it for convenience.
        include_logging = stage in ("generate_metadata", "update_rules")
        ctx.actions.run_shell(
            arguments = ["--file", ctx.file._makefile.path] + steps,
            command = " && ".join(commands),
            env = flow_environment(ctx) | config_environment(config),
            inputs = depset(
                [config] + ctx.files.extra_configs + all_jsons,
                transitive = [
                    data_inputs(ctx),
                    source_inputs(
                        ctx,
                        use_pre_layout = lib_selection,
                        gds = include_gds,
                        logging = include_logging,
                    ),
                    rename_inputs(ctx),
                ],
            ),
            outputs = all_outputs,
            tools = flow_inputs(ctx),
        )

    config_short = declare_artifact(ctx, "results", stage + ".short.mk")
    short_analysis_args = config_arguments(ctx, hack_away_prefix(all_arguments, config_short.root.path))
    short_analysis_json = declare_artifact(ctx, "results", stage + ".short.analysis.json")
    ctx.actions.write(
        output = short_analysis_json,
        content = json.encode(short_analysis_args),
    )

    short_args = [
        ctx.file._merge_arguments.path,
        config_short.path,
        "--filter",
        filter_json.path,
    ]
    for f in ctx.files.extra_configs:
        short_args.extend(["--include", f.short_path])
    short_args.extend([f.path for f in inherited_jsons])
    short_args.append(short_analysis_json.path)
    short_args.extend([f.path for f in extra_arg_files])

    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = short_args,
        inputs = inherited_jsons + [short_analysis_json] + extra_arg_files + [ctx.file._merge_arguments, filter_json] + ctx.files.extra_configs,
        outputs = [config_short],
    )

    make = _create_make_script(
        ctx,
        "make_{}_{}_{}".format(ctx.attr.name, ctx.attr.variant, stage),
    )

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    _expand_deploy_template(
        ctx,
        exe,
        config = config_short,
        make = make,
        genfiles = [config_short] + results + logs + reports + drcs + jsons,
    )

    # Collect all files needed for deployment.
    # Uses flow_inputs (CLI openroad), not flow_runfiles: the tarball and
    # the OrfsDepInfo.runfiles consumed by downstream rules (orfs_step,
    # orfs_deploy_srcs) are headless paths. openroad_qt is only added to
    # DefaultInfo.runfiles below so `bazelisk run :stage gui_<stage>` works.
    stage_renames = renames(ctx, ctx.files.src, short = True)
    deploy_files = depset(
        [config_short, make] + ctx.files.src + ctx.files.extra_configs + all_jsons,
        transitive = [
            flow_inputs(ctx),
            data_inputs(ctx),
            source_inputs(ctx),
            rename_inputs(ctx),
        ],
    )

    # Portable tarball for on-demand deployment.
    deps_tar = _package_stage(
        ctx,
        config = config_short,
        make = make,
        runfiles_depset = deploy_files,
        renames = stage_renames,
    )

    # Legacy deploy script (used by orfs_step for bazel run).
    deps_exe = declare_artifact(ctx, "results", ctx.attr.name + "_deps_deploy.sh")
    _expand_deploy_template(
        ctx,
        deps_exe,
        config = config_short,
        make = make,
        genfiles = [config_short] + ctx.files.src + ctx.files.data + ctx.files.extra_configs,
        name = ctx.attr.name + "_deps",
        renames = stage_renames,
    )

    _runfiles_files = (
        [config_short, make] +
        forwards +
        results +
        logs +
        reports +
        ctx.files.extra_configs +
        drcs +
        jsons +
        ctx.files.data
    )
    _runfiles_common = depset(
        transitive = [
            ctx.attr.src[PdkInfo].files,
            ctx.attr.src[PdkInfo].libs,
            ctx.attr.src[OrfsInfo].additional_gds,
            ctx.attr.src[OrfsInfo].additional_lefs,
            ctx.attr.src[OrfsInfo].additional_libs,
            ctx.attr.src[OrfsInfo].additional_libs_pre_layout,
        ],
    )
    return [
        DefaultInfo(
            executable = exe,
            files = depset(forwards + results + reports),
            # default_runfiles includes openroad_qt so `bazelisk run
            # :stage gui_<stage>` finds the Qt-linked binary in the
            # deployed temp folder. data_runfiles deliberately omits
            # openroad_qt so downstream rules that consume this stage
            # via `data =` (e.g. orfs_generate_metadata pulling synth
            # and floorplan outputs) do not drag the Qt binary into
            # their build action graph.
            default_runfiles = ctx.runfiles(
                _runfiles_files,
                transitive_files = depset(
                    transitive = [flow_runfiles(ctx), _runfiles_common],
                ),
            ),
            data_runfiles = ctx.runfiles(
                _runfiles_files,
                transitive_files = depset(
                    transitive = [flow_inputs(ctx), _runfiles_common],
                ),
            ),
        ),
        OutputGroupInfo(
            logs = depset(logs),
            reports = depset(reports),
            jsons = depset(jsons),
            drcs = depset(drcs),
            deps = depset([deps_tar]),
            **dict(
                {
                    f.basename: depset([f])
                    for f in [config] + results + objects + logs + reports + jsons + drcs
                },
                **{
                    "substep_" + substep_names[i]: depset([f])
                    for i, f in enumerate(substep_odbs)
                }
            )
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            renames = stage_renames,
            # This stage's OWN data (sources= files) and configs — what the
            # next stage's source_inputs() legitimately needs beyond the
            # results/reports it already takes from DefaultInfo via
            # ctx.files.src. Deliberately NOT ctx.files.src: that is the
            # PREVIOUS stage's whole DefaultInfo, and re-feeding it here
            # handed stage N-1's results (1_synth netlist/RTLIL/…) to
            # stage N+1's action inputs, one hop past every reader — a
            # N-1 output change stage N absorbed still re-ran N+1. The
            # forwarded subset (forwards) already travels via
            # DefaultInfo.files. The deploy set (OrfsDepInfo.runfiles =
            # deploy_files) keeps ctx.files.src — a deployed re-run of
            # this stage's make reads the previous stage's results.
            files = depset(
                [config_short] +
                ctx.files.data +
                ctx.files.extra_configs,
            ),
            runfiles = ctx.runfiles(transitive_files = deploy_files),
        ),
        OrfsInfo(
            stage = stage,
            config = config,
            variant = ctx.attr.variant,
            odb = info.get("odb"),
            sdc = info.get("sdc"),
            gds = info.get("gds"),
            lef = info.get("lef"),
            lib = info.get("lib"),
            lib_pre_layout = lib_pre_layout,
            additional_gds = ctx.attr.src[OrfsInfo].additional_gds,
            additional_lefs = ctx.attr.src[OrfsInfo].additional_lefs,
            additional_libs = ctx.attr.src[OrfsInfo].additional_libs,
            additional_libs_pre_layout = ctx.attr.src[OrfsInfo].additional_libs_pre_layout,
            arguments = depset(
                [analysis_json],
                transitive = [ctx.attr.src[OrfsInfo].arguments] +
                             ([depset(extra_arg_files)] if extra_arg_files else []),
            ),
        ),
        LoggingInfo(
            log_dir = artifact_dir(ctx, "logs"),
            logs = depset(logs, transitive = [ctx.attr.src[LoggingInfo].logs]),
            reports = depset(reports, transitive = [ctx.attr.src[LoggingInfo].reports]),
            drcs = depset(drcs, transitive = [ctx.attr.src[LoggingInfo].drcs]),
            jsons = depset(jsons, transitive = [ctx.attr.src[LoggingInfo].jsons]),
        ),
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
    ]

# --- Substep deploy-and-run rule ---

def _step_impl(ctx):
    """Deploys stage artifacts and runs a specific substep make target."""
    exe = declare_artifact(ctx, "results", ctx.attr.name + ".sh")

    # All substep targets for a stage share the same deploy directory
    # so that substep N can read the ODB written by substep N-1.
    deploy_name = ctx.attr.deploy_name if ctx.attr.deploy_name else ctx.attr.name
    _expand_deploy_template(
        ctx,
        exe,
        config = ctx.attr.src[OrfsDepInfo].config,
        make = ctx.attr.src[OrfsDepInfo].make,
        genfiles = ctx.attr.src[OrfsDepInfo].files.to_list(),
        name = deploy_name,
        renames = ctx.attr.src[OrfsDepInfo].renames,
    )

    # Wrapper that symlinks runfiles so the deploy script can find them,
    # then invokes deploy with the baked-in make target.
    wrapper = ctx.actions.declare_file(ctx.attr.name + "_run.sh")
    ctx.actions.write(
        output = wrapper,
        is_executable = True,
        content = """\
#!/bin/bash
RUNFILES="${{RUNFILES_DIR:-$0.runfiles}}"
DEPLOY="$RUNFILES/_main/{deploy}"
# deploy.tpl expects $0.runfiles to exist
ln -sfn "$RUNFILES" "$DEPLOY.runfiles"
exec "$DEPLOY" do-{make_target} "$@"
""".format(
            deploy = exe.short_path,
            make_target = ctx.attr.stage_name,
        ),
    )
    return [
        DefaultInfo(
            executable = wrapper,
            files = ctx.attr.src[OrfsDepInfo].files,
            runfiles = ctx.runfiles(files = [exe]).merge(
                ctx.attr.src[OrfsDepInfo].runfiles,
            ),
        ),
    ]

orfs_step = rule(
    implementation = _step_impl,
    attrs = flow_attrs() | openroad_only_attrs() | yosys_only_attrs() | {
        "stage_name": attr.string(
            doc = "ORFS substep name, e.g. '3_4_place_resized'. " +
                  "Used to derive the make target (do-{stage_name}).",
            mandatory = True,
        ),
        "deploy_name": attr.string(
            doc = "Deploy folder name. All substeps for a stage share " +
                  "the same deploy_name so they read/write the same ODB files.",
        ),
    },
    executable = True,
)

# --- Squashed multi-stage rule ---

def _squashed_impl(ctx):
    """Runs multiple stages as a single Bazel action."""
    return _make_impl(
        ctx = ctx,
        stage = ctx.attr.stage_name,
        steps = ctx.attr.make_targets,
        log_names = ctx.attr.log_names,
        json_names = ctx.attr.json_names,
        report_names = ctx.attr.report_names,
        result_names = ctx.attr.result_names,
        drc_names = ctx.attr.drc_names,
        substep_names = ctx.attr.substep_names,
    )

orfs_squashed = rule(
    implementation = _squashed_impl,
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "stage_name": attr.string(mandatory = True),
                "stages": attr.string_list(default = []),
                "make_targets": attr.string_list(mandatory = True),
                "log_names": attr.string_list(default = []),
                "json_names": attr.string_list(default = []),
                "report_names": attr.string_list(default = []),
                "result_names": attr.string_list(default = []),
                "drc_names": attr.string_list(default = []),
                "substep_names": attr.string_list(default = []),
            },
    provides = flow_provides(),
    executable = True,
)

# --- Stage rule declarations ---

orfs_floorplan_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "2_floorplan",
        steps = ["do-floorplan"],
        forwarded_names = [CANON_OUTPUT],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["floorplan"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["floorplan"]],
        report_names = [
            "2_floorplan_final.rpt",
        ],
        result_names = [
            "2_floorplan.odb",
            "2_floorplan.sdc",
        ],
        substep_names = STAGE_SUBSTEPS["floorplan"] if ctx.attr.substeps else [],
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "floorplan",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

orfs_place_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "3_place",
        steps = ["do-place"],
        forwarded_names = [CANON_OUTPUT],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["place"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["place"]],
        report_names = [],
        result_names = [
            "3_place.odb",
            "3_place.sdc",
        ],
        substep_names = STAGE_SUBSTEPS["place"] if ctx.attr.substeps else [],
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "place",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

orfs_cts_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "4_cts",
        steps = ["do-cts"],
        forwarded_names = [CANON_OUTPUT],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["cts"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["cts"]],
        report_names = [
            "4_cts_final.rpt",
        ],
        result_names = [
            "4_cts.odb",
            "4_cts.sdc",
        ],
        substep_names = STAGE_SUBSTEPS["cts"] if ctx.attr.substeps else [],
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "cts",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

orfs_grt_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "5_1_grt",
        steps = [
            "do-5_1_grt",
        ],
        forwarded_names = [
            "5_1_grt.sdc",
        ],
        log_names = [
            "5_1_grt.log",
        ],
        json_names = [
            "5_1_grt.json",
        ],
        report_names = [
            "5_global_route.rpt",
        ],
        drc_names = [
            "congestion.rpt",
        ],
        result_names = [
            "5_1_grt.odb",
            "5_1_grt.sdc",
        ],
        substep_names = STAGE_SUBSTEPS["grt"] if ctx.attr.substeps else [],
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "grt",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

orfs_route_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "5_2_route",
        steps = [
            "do-5_2_route",
            "do-5_3_fillcell",
            "do-5_route",
            "do-5_route.sdc",
        ],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["route"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["route"]],
        drc_names = [
            "5_route_drc.rpt",
        ],
        result_names = [
            "5_route.odb",
            "5_route.sdc",
        ],
        substep_names = STAGE_SUBSTEPS["route"] if ctx.attr.substeps else [],
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "route",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

orfs_final_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "6_final",
        steps = ["do-final"],
        object_names = [],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["final"]],
        json_names = [
            "6_report.json",
            "6_1_fill.json",
        ],
        report_names = [
            "6_finish.rpt",
            "VDD.rpt",
            "VSS.rpt",
        ],
        result_names = [
            "6_final.def",
            "6_final.odb",
            "6_final.sdc",
            "6_final.spef",
            "6_final.v",
        ],
        substep_names = STAGE_SUBSTEPS["final"] if ctx.attr.substeps else [],
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "final",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

orfs_gds_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "6_gds",
        steps = ["do-gds"],
        object_names = [
            "klayout.lyt",
        ],
        log_names = [
            "6_gds.log",
        ],
        json_names = [],
        report_names = [],
        result_names = [
            "6_final.gds",
        ],
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "final",
                ),
                "klayout": attr.label(
                    doc = "KLayout binary. Override to use a custom or mock klayout.",
                    executable = True,
                    allow_files = True,
                    cfg = "exec",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

orfs_generate_metadata_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "generate_metadata",
        steps = ["metadata-generate"],
        object_names = [],
        log_names = [
            "metadata-generate.log",
        ],
        json_names = [],
        report_names = [
            "metadata.json",
        ],
        result_names = [],
        # The fast synthesis QoR pre-check runs this rule under a
        # "<variant>_synth" sub-variant whose logs/jsons inputs are
        # staged under the parent variant's tree.
        rename_data = True,
    ),
    attrs = openroad_attrs() | renamed_inputs_attr() | {
        "_stage": attr.string(default = "generate_metadata"),
    },
    provides = flow_provides(),
    executable = True,
)

orfs_update_rules = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "update_rules",
        steps = ["do-update_rules"],
        object_names = [],
        log_names = [],
        json_names = [],
        report_names = ["rules.json"],
        result_names = [],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr() | {
        "_stage": attr.string(default = "update_rules"),
    },
    provides = flow_provides(),
    executable = True,
)

orfs_abstract_rule = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "7_abstract",
        steps = ["do-generate_abstract"],
        result_names = [
            "{}.lef".format(ctx.attr.src[TopInfo].module_top),
            "{}_typ.lib".format(ctx.attr.src[TopInfo].module_top),
        ],
        log_names = [
            "generate_abstract.log",
        ],
        extra_arguments = {
            "ABSTRACT_SOURCE": extensionless_basename(ctx.attr.src[OrfsInfo].odb),
        },
        lib_pre_layout = (
            ctx.attr.pre_layout_abstract[OrfsInfo].lib if ctx.attr.pre_layout_abstract else None
        ),
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "generate_abstract",
                ),
                "pre_layout_abstract": attr.label(
                    providers = [OrfsInfo],
                    doc = "Optional sibling abstract target emitted at the " +
                          "post-`place` stage. Its .lib is exposed as this " +
                          "target's OrfsInfo.lib_pre_layout so that parent " +
                          "flows can consume ideal-clock timing for " +
                          "synth/floorplan/place and the canonical " +
                          "propagated-clock lib from CTS onward.",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

# --- Stage implementation structs ---

FINAL_STAGE_IMPL = struct(stage = "final", impl = orfs_final_rule)

GENERATE_METADATA_STAGE_IMPL = struct(
    stage = "generate_metadata",
    impl = orfs_generate_metadata_rule,
)
UPDATE_RULES_IMPL = struct(stage = "update_rules", impl = orfs_update_rules)

TEST_STAGE_IMPL = struct(stage = "test", impl = orfs_test)

STAGE_IMPLS = [
    struct(stage = "synth", impl = orfs_synth_rule),
    struct(stage = "floorplan", impl = orfs_floorplan_rule),
    struct(stage = "place", impl = orfs_place_rule),
    struct(stage = "cts", impl = orfs_cts_rule),
    struct(stage = "grt", impl = orfs_grt_rule),
    struct(stage = "route", impl = orfs_route_rule),
    FINAL_STAGE_IMPL,
]

ABSTRACT_IMPL = struct(stage = "generate_abstract", impl = orfs_abstract_rule)
