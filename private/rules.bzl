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
    "merge_arguments",
    "odb_arguments",
    "orfs_additional_arguments",
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
    if getattr(ctx.attr, "lint", False):
        return ctx.executable._make.path + " --silent $@"
    return ctx.executable._make.path + " $@"

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
    return [DefaultInfo(
        files = depset([dep.make, dep.config]),
        runfiles = dep.runfiles,
    )]

orfs_deploy_srcs = rule(
    implementation = _deploy_srcs_impl,
    attrs = {
        "src": attr.label(
            mandatory = True,
            providers = [OrfsDepInfo],
        ),
    },
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
        env = config_overrides(
            ctx,
            flow_environment(ctx) |
            yosys_environment(ctx) |
            config_environment(src_info.config) |
            odb_arguments(ctx) |
            data_arguments(ctx) |
            run_arguments(ctx) |
            {"OUTPUT": computed_json.path},
        ),
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
            },
)

# --- Test rule ---

def _test_impl(ctx):
    config = ctx.attr.src[OrfsDepInfo].config

    test = ctx.actions.declare_file(
        "make_{}_{}_test".format(ctx.attr.name, ctx.attr.variant),
    )

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
        if ctx.label.workspace_name:
            parts = ["external", ctx.label.workspace_name]
            if ctx.label.package:
                parts.append(ctx.label.package)
            work_home = "/".join(parts)
        else:
            work_home = None
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

def _yosys_parallel_synth(ctx, config, canon_output, synth_outputs, synth_logs, synth_reports, num_partitions, save_odb, all_arguments = {}):
    """Parallel synthesis: keep → kept-json → N partitions → merge.

    Yosys is not deterministic when using host threads, so SYNTH_NUM_PARTITIONS
    defaulting to NUM_CPUS means synthesis results vary across machines with
    different core counts. Users who need reproducible builds should set a fixed
    SYNTH_NUM_PARTITIONS value.

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
            ],
            command = " && ".join(keep_commands),
            env = config_overrides(ctx, base_env),
            inputs = depset(
                [canon_output, config, parallel_makefile, ctx.file._synth_keep_script] +
                ctx.files.extra_configs,
                transitive = [
                    data_inputs(ctx),
                    pdk_inputs(ctx),
                    deps_inputs(ctx),
                ],
            ),
            outputs = [checkpoint_output] + keep_logs,
            tools = yosys_and_flow_tools,
        )

        # Action 2b: kept-json → kept_modules.json
        ctx.actions.run_shell(
            command = "{python} {script} {rtlil} {json}".format(
                python = ctx.executable._python.path,
                script = ctx.file._rtlil_kept_modules.path,
                rtlil = checkpoint_output.path,
                json = kept_json.path,
            ),
            inputs = [checkpoint_output, ctx.file._rtlil_kept_modules],
            outputs = [kept_json],
            tools = [ctx.executable._python],
        )

    # Actions 3..N: partition (parallel)
    # Uses wrapper Makefile for yosys-dependencies + do-yosys-partition
    partition_env_extra = {"SYNTH_SKIP_KEEP": "1"} if skip_keep else {}
    partition_inputs = depset(
        [
            checkpoint_output,
            kept_json,
            config,
            parallel_makefile,
            ctx.file._synth_partition_script,
            ctx.file._synth_tcl,
        ] +
        ctx.files.extra_configs,
        transitive = [
            data_inputs(ctx),
            pdk_inputs(ctx),
            deps_inputs(ctx),
        ],
    )

    # Compute module-to-partition mapping for progress messages
    kept_modules_list = [m for m in all_arguments.get("SYNTH_KEEP_MODULES", "").split(" ") if m]

    partition_outputs = []
    for i in range(num_partitions):
        # Build a human-readable progress message showing which modules
        # this partition will synthesize.
        if kept_modules_list:
            my_modules = [m for idx, m in enumerate(kept_modules_list) if idx % num_partitions == i]
            if my_modules:
                progress_msg = "Synthesizing partition {}/{}: {}".format(i, num_partitions, ", ".join(my_modules))
            else:
                progress_msg = "Synthesizing partition {}/{} (empty)".format(i, num_partitions)
        else:
            progress_msg = "Synthesizing partition {}/{}".format(i, num_partitions)

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
            ],
            command = " && ".join(part_commands),
            env = config_overrides(ctx, base_env | partition_env_extra | {
                "SYNTH_PARTITION_ID": str(i),
                "SYNTH_NUM_PARTITIONS": str(num_partitions),
                "SYNTH_TCL": ctx.file._synth_tcl.path,
            }),
            inputs = partition_inputs,
            outputs = [part_output],
            tools = yosys_and_flow_tools,
            progress_message = progress_msg,
        )

    # Action 4: synthesize the top module with all kept modules blackboxed
    top_output = declare_artifact(ctx, "results", "partition_top.v")
    top_commands = [_make_cmd(ctx)] + generation_commands([top_output])
    ctx.actions.run_shell(
        arguments = [
            "--file",
            parallel_makefile.path,
            "yosys-dependencies",
            "do-yosys-partition",
            "SYNTH_PARTITION_SCRIPT=" + ctx.file._synth_partition_script.path,
        ],
        command = " && ".join(top_commands),
        env = config_overrides(ctx, base_env | partition_env_extra | {
            "SYNTH_PARTITION_ID": "top",
            "SYNTH_NUM_PARTITIONS": str(num_partitions),
            "SYNTH_TCL": ctx.file._synth_tcl.path,
        }),
        inputs = partition_inputs,
        outputs = [top_output],
        tools = yosys_and_flow_tools,
        progress_message = "Synthesizing top module",
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
    )

    # Action 5: SDC copy → 1_2_yosys.sdc
    # Uses wrapper Makefile so SDC_FILE is resolved from DESIGN_CONFIG
    ctx.actions.run_shell(
        arguments = [
            "--file",
            parallel_makefile.path,
            "do-yosys-sdc-copy",
        ],
        command = "{make} $@".format(make = ctx.executable._make.path),
        env = config_overrides(ctx, base_env),
        inputs = depset(
            [config, parallel_makefile] + ctx.files.extra_configs,
            transitive = [
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = [synth_outputs["1_2_yosys.sdc"]],
        tools = yosys_and_flow_tools,
    )

    # Action 6: ODB generation → 1_synth.odb
    # do-1_synth is a .PHONY target that runs synth_odb.tcl to read the
    # merged Verilog and produce the ODB; it does not trigger yosys rebuilds.
    if save_odb:
        odb_commands = [_make_cmd(ctx)] + generation_commands(
            [synth_outputs["1_synth.odb"]],
        )
        ctx.actions.run_shell(
            arguments = [
                "--file",
                parallel_makefile.path,
                "do-1_synth",
            ],
            command = " && ".join(odb_commands),
            env = config_overrides(ctx, base_env),
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
                    deps_inputs(ctx),
                ],
            ),
            outputs = [synth_outputs["1_synth.odb"], synth_outputs["1_synth.sdc"]],
            tools = yosys_and_flow_tools,
        )

    # Stub outputs that the serial path produces but parallel does not
    for name in ["mem.json"]:
        ctx.actions.write(output = synth_outputs[name], content = "")
    for f in synth_logs + synth_reports:
        ctx.actions.write(output = f, content = "")

def _yosys_impl(ctx):
    all_arguments = merge_arguments(
        data_arguments(ctx) |
        required_arguments(ctx),
        orfs_additional_arguments(
            [dep[OrfsInfo] for dep in ctx.attr.deps],
            use_pre_layout = True,
        ),
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
    commands = [_make_cmd(ctx)] + generation_commands(
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

    num_partitions = int(all_arguments.get("SYNTH_NUM_PARTITIONS", "0"))
    if num_partitions == 0 and all_arguments.get("SYNTH_KEEP_MODULES"):
        # SYNTH_KEEP_MODULES implies parallel synthesis; default to 1 partition
        # when NUM_CPUS-based auto-detection hasn't run (direct orfs_synth call).
        kept_count = len(all_arguments["SYNTH_KEEP_MODULES"].split(" "))
        num_partitions = max(1, kept_count)

    save_odb = ctx.attr.save_odb

    synth_logs = declare_artifacts(ctx, "logs", ["1_2_yosys.log", "1_2_yosys_metrics.log"] + (["1_synth.log"] if save_odb else []))

    synth_outputs = {}
    for output in SYNTH_OUTPUTS + (["1_synth.odb"] if save_odb else []):
        synth_outputs[output] = declare_artifact(ctx, "results", output)

    synth_reports = declare_artifacts(ctx, "reports", SYNTH_REPORTS)

    variables = declare_artifact(ctx, "results", "1_synth.vars")

    if ctx.attr.lint:
        # Lint mode: only canonicalization runs; stub remaining synth outputs.
        for f in synth_outputs.values() + synth_logs + synth_reports + [variables]:
            ctx.actions.write(output = f, content = "")
    elif num_partitions > 0:
        _yosys_parallel_synth(ctx, config, canon_output, synth_outputs, synth_logs, synth_reports, num_partitions, save_odb, all_arguments)
    else:
        # SYNTH_NETLIST_FILES will not create an .rtlil file or reports, so we need
        # an empty placeholder in that case.
        commands = [_make_cmd(ctx)] + generation_commands(
            synth_logs + synth_outputs.values() + synth_reports,
        )
        ctx.actions.run_shell(
            arguments = [
                "--file",
                ctx.file._makefile_yosys.path,
                "yosys-dependencies",
                "do-yosys",
            ] + (["do-1_synth"] if save_odb else []),
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

    if not ctx.attr.lint:
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
                arguments = merge_arguments(
                    data_arguments(ctx) |
                    required_arguments(ctx),
                    orfs_additional_arguments([dep[OrfsInfo] for dep in ctx.attr.deps]),
                ) | verilog_arguments(ctx.files.verilog_files),
                prefix = config_short.root.path,
            ),
            paths = [file.short_path for file in ctx.files.extra_configs],
        ),
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
        genfiles = [config_short] + outputs + canon_logs + synth_logs,
    )

    # Collect all files needed for deployment (tools, PDK, stage inputs).
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
            deps = depset([deps_tar]),
            **{f.basename: depset([f]) for f in [config] + outputs}
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            renames = [],
            files = depset(
                [config_short] + ctx.files.verilog_files + ctx.files.extra_configs,
            ),
            runfiles = ctx.runfiles(transitive_files = deploy_files),
        ),
        OrfsInfo(
            stage = "1_synth",
            config = config,
            variant = ctx.attr.variant,
            odb = synth_outputs.get("1_synth.odb"),
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
            arguments = depset([]),
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
                "_rtlil_kept_modules": attr.label(
                    allow_single_file = True,
                    default = Label("//:rtlil_kept_modules.py"),
                ),
                "_synth_tcl": attr.label(
                    allow_single_file = True,
                    default = Label("//:synth.tcl"),
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
        lib_pre_layout = None):
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

    # Write this stage's arguments to .json for downstream stages, then
    # merge inherited .json files and this stage's .json into a .mk that
    # the stage config includes via pre_paths. Precedence (later wins in
    # merge_arguments.py): inherited < stage < extra.
    stage_json = declare_artifact(ctx, "results", stage + ".args.json")
    ctx.actions.write(
        output = stage_json,
        content = json.encode(data_arguments(ctx)),
    )
    inherited_jsons = ctx.attr.src[OrfsInfo].arguments.to_list()
    extra_arg_files = ctx.files.extra_arguments
    all_jsons = inherited_jsons + [stage_json] + extra_arg_files
    args_mk = declare_artifact(ctx, "results", stage + ".args.mk")
    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = [ctx.file._merge_arguments.path, args_mk.path] +
                    [f.path for f in all_jsons],
        inputs = all_jsons + [ctx.file._merge_arguments],
        outputs = [args_mk],
    )

    config = declare_artifact(ctx, "results", stage + ".mk")
    ctx.actions.write(
        output = config,
        content = config_content(
            ctx,
            arguments = all_arguments,
            pre_paths = [args_mk.path],
            paths = [file.path for file in ctx.files.extra_configs],
        ),
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
        commands = (
            generation_commands(reports + logs + jsons + drcs + substep_odbs) +
            input_commands(renames(ctx, ctx.files.src)) +
            [_make_cmd(ctx)]
        )

        ctx.actions.run_shell(
            arguments = ["--file", ctx.file._makefile.path] + steps,
            command = " && ".join(commands),
            env = config_overrides(ctx, flow_environment(ctx) | config_environment(config)),
            inputs = depset(
                [config, args_mk] + ctx.files.extra_configs + all_jsons,
                transitive = [
                    data_inputs(ctx),
                    source_inputs(ctx),
                    rename_inputs(ctx),
                ],
            ),
            outputs = all_outputs,
            tools = flow_inputs(ctx),
        )

    config_short = declare_artifact(ctx, "results", stage + ".short.mk")
    ctx.actions.write(
        output = config_short,
        content = config_content(
            ctx,
            arguments = hack_away_prefix(
                arguments = merge_arguments(
                    extra_arguments |
                    data_arguments(ctx) |
                    required_arguments(ctx),
                    orfs_additional_arguments(
                        [ctx.attr.src[OrfsInfo]],
                        use_pre_layout = use_pre_layout,
                    ),
                ),
                prefix = config_short.root.path,
            ),
            pre_paths = [args_mk.short_path],
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

    # Collect all files needed for deployment.
    stage_renames = renames(ctx, ctx.files.src, short = True)
    deploy_files = depset(
        [config_short, make, args_mk] + ctx.files.src + ctx.files.extra_configs + all_jsons,
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

    return [
        DefaultInfo(
            executable = exe,
            files = depset(forwards + results + reports + [args_mk]),
            runfiles = ctx.runfiles(
                [config_short, make] +
                forwards +
                results +
                logs +
                reports +
                ctx.files.extra_configs +
                drcs +
                jsons +
                ctx.files.data,
                transitive_files = depset(
                    transitive = [
                        flow_inputs(ctx),
                        ctx.attr.src[PdkInfo].files,
                        ctx.attr.src[PdkInfo].libs,
                        ctx.attr.src[OrfsInfo].additional_gds,
                        ctx.attr.src[OrfsInfo].additional_lefs,
                        ctx.attr.src[OrfsInfo].additional_libs,
                        ctx.attr.src[OrfsInfo].additional_libs_pre_layout,
                    ],
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
            files = depset(
                [config_short] +
                ctx.files.src +
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
            gds = info.get("gds"),
            lef = info.get("lef"),
            lib = info.get("lib"),
            lib_pre_layout = lib_pre_layout,
            additional_gds = ctx.attr.src[OrfsInfo].additional_gds,
            additional_lefs = ctx.attr.src[OrfsInfo].additional_lefs,
            additional_libs = ctx.attr.src[OrfsInfo].additional_libs,
            additional_libs_pre_layout = ctx.attr.src[OrfsInfo].additional_libs_pre_layout,
            arguments = depset(
                [stage_json],
                transitive = [ctx.attr.src[OrfsInfo].arguments] +
                             ([depset(extra_arg_files)] if extra_arg_files else []),
            ),
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

orfs_floorplan = rule(
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

orfs_place = rule(
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

orfs_cts = rule(
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
