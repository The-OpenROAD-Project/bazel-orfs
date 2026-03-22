"""Rule implementations and declarations for OpenROAD-flow-scripts Bazel rules."""

load(
    "//private:attrs.bzl",
    "flow_attrs",
    "flow_provides",
    "openroad_attrs",
    "openroad_only_attrs",
    "renamed_inputs_attr",
    "synth_attrs",
    "yosys_attrs",
    "yosys_only_attrs",
)
load(
    "//private:environment.bzl",
    "EXPAND_VERILOG_DIRS",
    "config_content",
    "config_environment",
    "config_overrides",
    "data_arguments",
    "data_inputs",
    "declare_artifact",
    "declare_artifacts",
    "deps_inputs",
    "environment_string",
    "extensionless_basename",
    "flow_environment",
    "flow_inputs",
    "flow_substitutions",
    "generation_commands",
    "hack_away_prefix",
    "input_commands",
    "odb_arguments",
    "orfs_arguments",
    "pdk_inputs",
    "rename_inputs",
    "renames",
    "required_arguments",
    "run_arguments",
    "source_inputs",
    "test_inputs",
    "verilog_arguments",
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
    "STAGE_SUBSTEPS",
)

# --- Shared helpers ---

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
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = flow_substitutions(ctx) |
                        {'"$@"': 'DESIGN_CONFIG="config.mk" "$@"'} |
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
            gds = info.get("gds"),
            lef = info.get("lef"),
            lib = info.get("lib"),
            additional_gds = depset([]),
            additional_lefs = depset([]),
            additional_libs = depset([]),
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
    exe = declare_artifact(ctx, "results", ctx.attr.name + ".sh")
    _expand_deploy_template(
        ctx,
        exe,
        config = ctx.attr.src[OrfsDepInfo].config,
        make = ctx.attr.src[OrfsDepInfo].make,
        genfiles = ctx.attr.src[OrfsDepInfo].files.to_list(),
        name = ctx.attr.name,
        renames = ctx.attr.src[OrfsDepInfo].renames,
    )
    return [
        DefaultInfo(
            executable = exe,
            files = ctx.attr.src[OrfsDepInfo].files,
            runfiles = ctx.attr.src[OrfsDepInfo].runfiles,
        ),
        ctx.attr.src[OrfsInfo],
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        # Don't depend on the logs of the source; a circular dependency
        LoggingInfo(
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
    executable = True,
)

# --- Run rule ---

def _run_impl(ctx):
    config = ctx.attr.src[OrfsInfo].config
    outs = []
    for k in dir(ctx.outputs):
        outs.extend(getattr(ctx.outputs, k))

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
                "$@",
            ],
        ),
        env = config_overrides(
            ctx,
            flow_environment(ctx) |
            yosys_environment(ctx) |
            config_environment(config) |
            odb_arguments(ctx) |
            data_arguments(ctx) |
            run_arguments(ctx),
        ),
        inputs = depset(
            [config, ctx.file.script],
            transitive = [
                data_inputs(ctx),
                source_inputs(ctx),
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
                                                        data_arguments(ctx) |
                                                        run_arguments(ctx),
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
            config = ctx.attr.src[OrfsDepInfo].config,
            renames = [],
            files = depset([ctx.attr.src[OrfsDepInfo].config, ctx.file.script]),
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    [ctx.attr.src[OrfsDepInfo].config, make, ctx.file.script],
                    transitive = [
                        flow_inputs(ctx),
                        data_inputs(ctx),
                        source_inputs(ctx),
                    ],
                ),
            ),
        ),
    ]

orfs_run = rule(
    implementation = _run_impl,
    attrs = yosys_attrs() |
            openroad_attrs() |
            {
                "cmd": attr.string(
                    mandatory = False,
                    default = "run",
                ),
                "extra_args": attr.string(
                    mandatory = False,
                    default = "",
                ),
                "outs": attr.output_list(
                    mandatory = True,
                    allow_empty = False,
                ),
                "script": attr.label(
                    mandatory = True,
                    allow_single_file = ["tcl"],
                ),
            },
)

# --- Test rule ---

def _test_impl(ctx):
    config = ctx.attr.src[OrfsDepInfo].config

    test = ctx.actions.declare_file(
        "make_{}_{}_test".format(ctx.attr.name, ctx.attr.variant),
    )
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
{make} --file {makefile} {moreargs} metadata-check
""".format(
            make = ctx.executable._make.short_path,
            makefile = ctx.file._makefile.path,
            moreargs = environment_string(
                hack_away_prefix(
                    arguments = odb_arguments(ctx) | data_arguments(ctx),
                    prefix = config.root.path,
                ) |
                {
                    "DESIGN_CONFIG": config.short_path,
                },
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
                    [config, test],
                    transitive = [
                        test_inputs(ctx),
                        data_inputs(ctx),
                        source_inputs(ctx),
                    ],
                ),
            ),
        ),
    ]

orfs_test = rule(
    implementation = _test_impl,
    attrs = yosys_attrs() |
            openroad_attrs() |
            {
                "cmd": attr.string(
                    mandatory = False,
                    default = "metadata-check",
                ),
            },
    test = True,
)

# --- Synthesis rule ---

CANON_OUTPUT = "1_1_yosys_canonicalize.rtlil"
SYNTH_OUTPUTS = ["1_2_yosys.v", "1_2_yosys.sdc", "1_synth.sdc", "mem.json"]
SYNTH_REPORTS = ["synth_stat.txt", "synth_mocked_memories.txt"]

def _yosys_impl(ctx):
    all_arguments = (
        data_arguments(ctx) |
        required_arguments(ctx) |
        orfs_arguments(*[dep[OrfsInfo] for dep in ctx.attr.deps])
    )
    config = declare_artifact(ctx, "results", "1_synth.mk")
    ctx.actions.write(
        output = config,
        content = config_content(
            ctx,
            all_arguments,
            [file.path for file in ctx.files.extra_configs],
        ),
    )

    canon_logs = declare_artifacts(ctx, "logs", ["1_1_yosys_canonicalize.log"])

    canon_output = declare_artifact(ctx, "results", CANON_OUTPUT)

    # SYNTH_NETLIST_FILES will not create an .rtlil file or reports, so we need
    # an empty placeholder in that case.
    commands = [ctx.executable._make.path + " $@"] + generation_commands(
        canon_logs + [canon_output],
    )

    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile_yosys.path,
            "yosys-dependencies",
            "do-yosys-canonicalize",
        ],
        command = EXPAND_VERILOG_DIRS + " && ".join(commands),
        env = config_overrides(
            ctx,
            verilog_arguments(ctx.files.verilog_files) |
            yosys_environment(ctx) |
            config_environment(config),
        ),
        inputs = depset(
            [config] + ctx.files.verilog_files + ctx.files.extra_configs,
            transitive = [
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = [canon_output] + canon_logs,
        tools = yosys_inputs(ctx),
    )

    synth_logs = declare_artifacts(ctx, "logs", ["1_2_yosys.log", "1_2_yosys_metrics.log"])

    synth_outputs = {}
    for output in SYNTH_OUTPUTS + (["1_synth.odb"] if ctx.attr.save_odb else []):
        synth_outputs[output] = declare_artifact(ctx, "results", output)

    synth_reports = declare_artifacts(ctx, "reports", SYNTH_REPORTS)

    # SYNTH_NETLIST_FILES will not create an .rtlil file or reports, so we need
    # an empty placeholder in that case.
    commands = [ctx.executable._make.path + " $@"] + generation_commands(
        synth_logs + synth_outputs.values() + synth_reports,
    )
    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile_yosys.path,
            "yosys-dependencies",
            "do-yosys",
        ] + (["do-1_synth"] if ctx.attr.save_odb else []),
        command = " && ".join(commands),
        env = config_overrides(
            ctx,
            verilog_arguments([]) |
            flow_environment(ctx) |
            yosys_environment(ctx) |
            config_environment(config),
        ),
        inputs = depset(
            [canon_output, config] + ctx.files.extra_configs,
            transitive = [
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = synth_outputs.values() + synth_logs + synth_reports,
        tools = depset(transitive = [yosys_inputs(ctx), flow_inputs(ctx)]),
    )

    variables = declare_artifact(ctx, "results", "1_synth.vars")
    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile_yosys.path,
            "print-LIB_FILES",
        ],
        command = """
        {make} $@ > {out}
        """.format(make = ctx.executable._make.path, out = variables.path),
        env = config_overrides(
            ctx,
            verilog_arguments([]) |
            flow_environment(ctx) |
            yosys_environment(ctx) |
            config_environment(config),
        ),
        inputs = depset(
            [canon_output, config] + ctx.files.extra_configs,
            transitive = [
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = [variables],
        tools = depset(transitive = [flow_inputs(ctx)]),
    )

    outputs = [canon_output, variables] + synth_outputs.values()

    config_short = declare_artifact(ctx, "results", "1_synth.short.mk")
    ctx.actions.write(
        output = config_short,
        content = config_content(
            ctx,
            arguments = hack_away_prefix(
                arguments = data_arguments(ctx) |
                            required_arguments(ctx) |
                            orfs_arguments(*[dep[OrfsInfo] for dep in ctx.attr.deps]) |
                            verilog_arguments(ctx.files.verilog_files),
                prefix = config_short.root.path,
            ),
            paths = [file.short_path for file in ctx.files.extra_configs],
        ),
    )

    make = _create_make_script(ctx, "make_1_synth", yosys_substitutions(ctx))

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    _expand_deploy_template(
        ctx,
        exe,
        config = config_short,
        make = make,
        genfiles = [config_short] + outputs + canon_logs + synth_logs,
    )

    return [
        DefaultInfo(
            executable = exe,
            files = depset(outputs),
            runfiles = ctx.runfiles(
                [config_short, make] +
                outputs +
                canon_logs +
                synth_logs +
                ctx.files.extra_configs,
                transitive_files = depset(
                    transitive = [
                        flow_inputs(ctx),
                        deps_inputs(ctx),
                        pdk_inputs(ctx),
                    ],
                ),
            ),
        ),
        OutputGroupInfo(
            logs = depset(canon_logs + synth_logs),
            reports = depset([]),
            **{f.basename: depset([f]) for f in [config] + outputs}
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            renames = [],
            files = depset(
                [config_short] + ctx.files.verilog_files + ctx.files.extra_configs,
            ),
            runfiles = ctx.runfiles(
                transitive_files = depset(
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
                ),
            ),
        ),
        OrfsInfo(
            stage = "1_synth",
            config = config,
            variant = ctx.attr.variant,
            odb = synth_outputs["1_synth.odb"] if ctx.attr.save_odb else None,
            gds = None,
            lef = None,
            lib = None,
            additional_gds = depset(
                [dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds],
            ),
            additional_lefs = depset(
                [dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef],
            ),
            additional_libs = depset(
                [dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib],
            ),
        ),
        ctx.attr.pdk[PdkInfo],
        TopInfo(
            module_top = ctx.attr.module_top,
        ),
        LoggingInfo(
            logs = depset(canon_logs + synth_logs),
            reports = depset(synth_reports),
            drcs = depset([]),
            jsons = depset([]),
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
        drc_names = []):
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

    Returns:
        A list of providers. The returned PdkInfo and TopInfo providers are taken from the first
        target of a ctx.attr.srcs list.
    """
    all_arguments = (
        extra_arguments |
        data_arguments(ctx) |
        required_arguments(ctx) |
        orfs_arguments(ctx.attr.src[OrfsInfo])
    )
    config = declare_artifact(ctx, "results", stage + ".mk")
    ctx.actions.write(
        output = config,
        content = config_content(
            ctx,
            arguments = all_arguments,
            paths = [file.path for file in ctx.files.extra_configs],
        ),
    )

    results = declare_artifacts(ctx, "results", result_names)
    objects = declare_artifacts(ctx, "objects", object_names)
    logs = declare_artifacts(ctx, "logs", log_names)
    jsons = declare_artifacts(ctx, "logs", json_names)
    reports = declare_artifacts(ctx, "reports", report_names)
    drcs = declare_artifacts(ctx, "reports", drc_names)

    forwards = [f for f in ctx.files.src if f.basename in forwarded_names]

    info = {}
    for file in forwards + results:
        info[file.extension] = file

    commands = (
        generation_commands(reports + logs + jsons + drcs) +
        input_commands(renames(ctx, ctx.files.src)) +
        [ctx.executable._make.path + " $@"]
    )

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile.path] + steps,
        command = " && ".join(commands),
        env = config_overrides(ctx, flow_environment(ctx) | config_environment(config)),
        inputs = depset(
            [config] + ctx.files.extra_configs,
            transitive = [
                data_inputs(ctx),
                source_inputs(ctx),
                rename_inputs(ctx),
            ],
        ),
        outputs = results + objects + logs + reports + jsons + drcs,
        tools = flow_inputs(ctx),
    )

    config_short = declare_artifact(ctx, "results", stage + ".short.mk")
    ctx.actions.write(
        output = config_short,
        content = config_content(
            ctx,
            arguments = hack_away_prefix(
                arguments = extra_arguments |
                            data_arguments(ctx) |
                            required_arguments(ctx) |
                            orfs_arguments(ctx.attr.src[OrfsInfo]),
                prefix = config_short.root.path,
            ),
            paths = [file.short_path for file in ctx.files.extra_configs],
        ),
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

    return [
        DefaultInfo(
            executable = exe,
            files = depset(forwards + results + reports),
            runfiles = ctx.runfiles(
                [config_short, make] +
                forwards +
                results +
                logs +
                reports +
                ctx.files.extra_configs +
                drcs +
                jsons +
                # Some of these files might be read by open.tcl
                ctx.files.data,
                transitive_files = depset(
                    transitive = [
                        flow_inputs(ctx),
                        ctx.attr.src[PdkInfo].files,
                        ctx.attr.src[PdkInfo].libs,
                        ctx.attr.src[OrfsInfo].additional_gds,
                        ctx.attr.src[OrfsInfo].additional_lefs,
                        ctx.attr.src[OrfsInfo].additional_libs,
                    ],
                ),
            ),
        ),
        OutputGroupInfo(
            logs = depset(logs),
            reports = depset(reports),
            jsons = depset(jsons),
            drcs = depset(drcs),
            **{
                f.basename: depset([f])
                for f in [config] + results + objects + logs + reports + jsons + drcs
            }
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            renames = renames(ctx, ctx.files.src, short = True),
            files = depset(
                [config_short] +
                ctx.files.src +
                ctx.files.data +
                ctx.files.extra_configs,
            ),
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    [config_short, make] + ctx.files.src + ctx.files.extra_configs,
                    transitive = [
                        flow_inputs(ctx),
                        data_inputs(ctx),
                        source_inputs(ctx),
                        rename_inputs(ctx),
                    ],
                ),
            ),
        ),
        OrfsInfo(
            stage = stage,
            config = config,
            variant = ctx.attr.variant,
            odb = info.get("odb"),
            gds = info.get("gds"),
            lef = info.get("lef"),
            lib = info.get("lib"),
            additional_gds = ctx.attr.src[OrfsInfo].additional_gds,
            additional_lefs = ctx.attr.src[OrfsInfo].additional_lefs,
            additional_libs = ctx.attr.src[OrfsInfo].additional_libs,
        ),
        LoggingInfo(
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
    _expand_deploy_template(
        ctx,
        exe,
        config = ctx.attr.src[OrfsDepInfo].config,
        make = ctx.attr.src[OrfsDepInfo].make,
        genfiles = ctx.attr.src[OrfsDepInfo].files.to_list(),
        name = ctx.attr.name,
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
    )

orfs_squashed = rule(
    implementation = _squashed_impl,
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "stage_name": attr.string(mandatory = True),
                "make_targets": attr.string_list(mandatory = True),
                "log_names": attr.string_list(default = []),
                "json_names": attr.string_list(default = []),
                "report_names": attr.string_list(default = []),
                "result_names": attr.string_list(default = []),
                "drc_names": attr.string_list(default = []),
            },
    provides = flow_provides(),
    executable = True,
)

# --- Stage rule declarations ---

orfs_floorplan = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "2_floorplan",
        steps = ["do-floorplan"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["floorplan"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["floorplan"]],
        report_names = [
            "2_floorplan_final.rpt",
        ],
        result_names = [
            "2_floorplan.odb",
            "2_floorplan.sdc",
        ],
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

orfs_place = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "3_place",
        steps = ["do-place"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["place"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["place"]],
        report_names = [],
        result_names = [
            "3_place.odb",
            "3_place.sdc",
        ],
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

orfs_cts = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "4_cts",
        steps = ["do-cts"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["cts"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["cts"]],
        report_names = [
            "4_cts_final.rpt",
        ],
        result_names = [
            "4_cts.odb",
            "4_cts.sdc",
        ],
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

orfs_grt = rule(
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

orfs_route = rule(
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

orfs_final = rule(
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
            "6_final.odb",
            "6_final.sdc",
            "6_final.spef",
            "6_final.v",
        ],
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

orfs_gds = rule(
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

orfs_generate_metadata = rule(
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
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
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
    attrs = openroad_attrs() | renamed_inputs_attr(),
    provides = flow_provides(),
    executable = True,
)

orfs_abstract = rule(
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
    ),
    attrs = openroad_attrs() |
            renamed_inputs_attr() |
            {
                "_stage": attr.string(
                    default = "generate_abstract",
                ),
            },
    provides = flow_provides(),
    executable = True,
)

# --- Stage implementation structs ---

FINAL_STAGE_IMPL = struct(stage = "final", impl = orfs_final)

GENERATE_METADATA_STAGE_IMPL = struct(
    stage = "generate_metadata",
    impl = orfs_generate_metadata,
)
UPDATE_RULES_IMPL = struct(stage = "update_rules", impl = orfs_update_rules)

TEST_STAGE_IMPL = struct(stage = "test", impl = orfs_test)

STAGE_IMPLS = [
    struct(stage = "synth", impl = orfs_synth_rule),
    struct(stage = "floorplan", impl = orfs_floorplan),
    struct(stage = "place", impl = orfs_place),
    struct(stage = "cts", impl = orfs_cts),
    struct(stage = "grt", impl = orfs_grt),
    struct(stage = "route", impl = orfs_route),
    FINAL_STAGE_IMPL,
]

ABSTRACT_IMPL = struct(stage = "generate_abstract", impl = orfs_abstract)
