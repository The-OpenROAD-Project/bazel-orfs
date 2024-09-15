"""Rules for the building the OpenROAD-flow-scripts stages"""

OrfsInfo = provider(
    "The outputs of a OpenROAD-flow-scripts stage.",
    fields = [
        "stage",
        "odb",
        "gds",
        "lef",
        "lib",
        "additional_gds",
        "additional_lefs",
        "additional_libs",
    ],
)
PdkInfo = provider(
    "A process design kit.",
    fields = [
        "name",
        "files",
    ],
)
TopInfo = provider(
    "The name of the netlist top module.",
    fields = ["module_top"],
)

OrfsDepInfo = provider(
    "The name of the netlist top module.",
    fields = [
        "make",
        "config",
        "files",
        "runfiles",
    ],
)

LoggingInfo = provider(
    "Logs and reports for current and previous stages",
    fields = [
        "logs",
        "reports",
    ],
)

def _pdk_impl(ctx):
    return [
        DefaultInfo(
            files = depset(ctx.files.srcs),
        ),
        PdkInfo(
            name = ctx.attr.name,
            files = depset(ctx.files.srcs),
        ),
    ]

orfs_pdk = rule(
    implementation = _pdk_impl,
    attrs = {
        "srcs": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
    },
)

def odb_environment(ctx):
    if ctx.attr.src[OrfsInfo].odb:
        return {"ODB_FILE": ctx.attr.src[OrfsInfo].odb.path}
    return {}

def _default_env(ctx, config):
    return {
        "HOME": _work_home(ctx),
        "WORK_HOME": _work_home(ctx),
        "DESIGN_CONFIG": config.path,
        "FLOW_HOME": ctx.file._makefile.dirname,
    }

def _run_env(ctx, config):
    return _default_env(ctx, config) | {
        "OPENROAD_EXE": ctx.executable._openroad.path,
        "YOSYS_EXE": "",
        "TCL_LIBRARY": commonpath(ctx.files._tcl),
    }

def _run_impl(ctx):
    all_arguments = _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo])
    config = _declare_artifact(ctx, "results", "open.mk")
    ctx.actions.write(
        output = config,
        content = _config_content(all_arguments),
    )

    outs = []
    for k in dir(ctx.outputs):
        outs.extend(getattr(ctx.outputs, k))

    transitive_inputs = [
        ctx.attr.src[OrfsInfo].additional_gds,
        ctx.attr.src[OrfsInfo].additional_lefs,
        ctx.attr.src[OrfsInfo].additional_libs,
        ctx.attr.src[PdkInfo].files,
        ctx.attr.src[DefaultInfo].default_runfiles.files,
        ctx.attr.src[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._openroad[DefaultInfo].default_runfiles.files,
        ctx.attr._openroad[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._make[DefaultInfo].default_runfiles.files,
        ctx.attr._make[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._makefile[DefaultInfo].default_runfiles.files,
        ctx.attr._makefile[DefaultInfo].default_runfiles.symlinks,
    ]

    for datum in ctx.attr.data:
        transitive_inputs.append(datum.default_runfiles.files)
        transitive_inputs.append(datum.default_runfiles.symlinks)

    _, _, stage_name = ctx.attr.src[OrfsInfo].stage.partition("_")
    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile.path,
            "open_{}".format(stage_name),
        ],
        command = ctx.executable._make.path + " $@",
        env = odb_environment(ctx) | _run_env(ctx, config) | {
            "RUBYLIB": ":".join([commonpath(ctx.files._ruby), commonpath(ctx.files._ruby_dynamic)]),
            "DLN_LIBRARY_PATH": commonpath(ctx.files._ruby_dynamic),
            "GUI_ARGS": "-exit",
            "GUI_SOURCE": ctx.file.script.path,
        },
        inputs = depset(
            ctx.files.src +
            ctx.files.data +
            ctx.files._ruby +
            ctx.files._ruby_dynamic +
            ctx.files._tcl +
            [config, ctx.file.script, ctx.executable._openroad, ctx.executable._make, ctx.file._makefile],
            transitive = transitive_inputs,
        ),
        outputs = outs,
    )
    return [
        DefaultInfo(
            files = depset(outs),
        ),
        OutputGroupInfo(
            **{f.basename: depset([f]) for f in outs}
        ),
    ]

orfs_run = rule(
    implementation = _run_impl,
    attrs = {
        "data": attr.label_list(
            doc = "List of additional data.",
            allow_files = True,
            default = [],
        ),
        "src": attr.label(
            mandatory = True,
            providers = [OrfsInfo],
        ),
        "script": attr.label(
            mandatory = True,
            allow_single_file = ["tcl"],
        ),
        "outs": attr.output_list(
            mandatory = True,
            allow_empty = False,
        ),
        "variant": attr.string(
            doc = "Variant of the used flow.",
            default = "base",
        ),
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile"),
        ),
        "_make": attr.label(
            doc = "make binary",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:make"),
        ),
        "_openroad": attr.label(
            doc = "OpenROAD binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:openroad"),
        ),
        "_ruby": attr.label(
            doc = "Ruby library.",
            allow_files = True,
            default = Label("@docker_orfs//:ruby3.0.0"),
        ),
        "_ruby_dynamic": attr.label(
            doc = "Ruby dynamic library.",
            allow_files = True,
            default = Label("@docker_orfs//:ruby_dynamic3.0.0"),
        ),
        "_tcl": attr.label(
            doc = "Tcl library.",
            allow_files = True,
            default = Label("@docker_orfs//:tcl8.6"),
        ),
    },
)

def _run_openroad_impl(ctx, mock_area = False):
    all_arguments = _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo])
    config = _declare_artifact(ctx, "results", "run_or.mk")
    ctx.actions.write(
        output = config,
        content = _config_content(all_arguments),
    )

    if mock_area:
        obj_dir = _artifact_dir(ctx, "objects")
        outs = [ctx.actions.declare_file(obj_dir + "/scaled_area.env")]
    else:
        outs = ctx.outputs

    transitive_inputs = [
        ctx.attr.src[OrfsInfo].additional_gds,
        ctx.attr.src[OrfsInfo].additional_lefs,
        ctx.attr.src[OrfsInfo].additional_libs,
        ctx.attr.src[PdkInfo].files,
        ctx.attr.src[DefaultInfo].default_runfiles.files,
        ctx.attr.src[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._openroad[DefaultInfo].default_runfiles.files,
        ctx.attr._openroad[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._makefile[DefaultInfo].default_runfiles.files,
        ctx.attr._makefile[DefaultInfo].default_runfiles.symlinks,
    ]

    for datum in ctx.attr.data:
        transitive_inputs.append(datum.default_runfiles.files)
        transitive_inputs.append(datum.default_runfiles.symlinks)

    ctx.actions.run_shell(
        arguments = [
            "-no_splash",
            "-exit",
            ctx.file.script.path,
        ],
        command = ctx.executable._openroad.path + " $@",
        env = all_arguments | odb_environment(ctx) | _run_env(ctx, config) | {
            "RESULTS_DIR": ctx.genfiles_dir.path + "/" + _artifact_dir(ctx, "results"),
            "OUTPUTS": ":".join([out.path for out in outs]),
        } | ctx.attr.extra_envs,
        inputs = depset(
            ctx.files.src +
            ctx.files.data +
            ctx.files._tcl +
            [config, ctx.file.script, ctx.executable._openroad, ctx.file._makefile],
            transitive = transitive_inputs,
        ),
        outputs = outs,
    )
    return [
        DefaultInfo(
            files = depset(outs),
        ),
        OutputGroupInfo(
            **{f.basename: depset([f]) for f in outs}
        ),
    ]

def run_openroad_attrs():
    return {
        "data": attr.label_list(
            doc = "List of additional data.",
            allow_files = True,
            default = [],
        ),
        "src": attr.label(
            mandatory = True,
            providers = [OrfsInfo, PdkInfo],
        ),
        "variant": attr.string(
            doc = "Variant of the used flow.",
            default = "base",
        ),
        "extra_envs": attr.string_dict(
            doc = "Dictionary with additional environmental variables.",
            default = {},
        ),
        "_openroad": attr.label(
            doc = "OpenROAD binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:openroad"),
        ),
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile"),
        ),
        "_tcl": attr.label(
            doc = "Tcl library.",
            allow_files = True,
            default = Label("@docker_orfs//:tcl8.6"),
        ),
    }

orfs_run_openroad = rule(
    implementation = lambda ctx: _run_openroad_impl(ctx, False),
    attrs = run_openroad_attrs() | {
        "script": attr.label(
            mandatory = True,
            allow_single_file = ["tcl"],
        ),
        "outs": attr.output_list(
            mandatory = True,
            allow_empty = False,
        ),
    },
)

orfs_run_mock_area = rule(
    implementation = lambda ctx: _run_openroad_impl(ctx, True),
    attrs = run_openroad_attrs() | {
        "script": attr.label(
            default = "@bazel-orfs//:mock_area.tcl",
            allow_single_file = ["tcl"],
        ),
    },
)

def commonprefix(*args):
    """
    Return the longest path prefix.

    Return the longest path prefix (taken character-by-character)
    that is a prefix of all paths in `*args`. If `*args` is empty,
    return the empty string ('').

    Args:
      *args: Sequence of strings.
    Returns:
      Longest common prefix of each string in `*args`.
    """
    prefix = ""
    for t in zip(*args):
        for x in t:
            if x != t[0]:
                return prefix
        prefix += t[0]

    return prefix

def commonpath(files):
    """
    Return the longest common sub-path of each file in the sequence `files`.

    Args:
      files: Sequence of files.

    Returns:
      Longest common sub-path of each file in the sequence `files`.
    """
    prefix = commonprefix(*[f.path.elems() for f in files])
    path, _, _ = prefix.rpartition("/")
    return path

def flow_substitutions(ctx):
    return {
        "${MAKE_PATH}": ctx.executable._make.path,
        "${MAKEFILE_PATH}": ctx.file._makefile.path,
        "${FLOW_HOME}": ctx.file._makefile.dirname,
        "${TCL_LIBRARY}": commonpath(ctx.files._tcl),
    }

def openroad_substitutions(ctx):
    return {
        "${YOSYS_PATH}": "",
        "${OPENROAD_PATH}": ctx.executable._openroad.path,
        "${KLAYOUT_PATH}": ctx.executable._klayout.path,
        "${STDBUF_PATH}": "",
        "${RUBY_PATH}": commonpath(ctx.files._ruby),
        "${DLN_LIBRARY_PATH}": commonpath(ctx.files._ruby_dynamic),
        "${LIBGL_DRIVERS_PATH}": commonpath(ctx.files._opengl),
        "${QT_PLUGIN_PATH}": commonpath(ctx.files._qt_plugins),
        "${GIO_MODULE_DIR}": commonpath(ctx.files._gio_modules),
    }

def yosys_substitutions(ctx):
    return {
        "${MAKE_PATH}": ctx.executable._make.path,
        "${YOSYS_PATH}": ctx.executable._yosys.path,
        "${OPENROAD_PATH}": "",
    }

default_substitutions = {
    "${EXTRA_ENVS}": "",
}

def _deps_impl(ctx):
    exe = _declare_artifact(ctx, "results", ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = default_substitutions | default_substitutions | {
            "${GENFILES}": " ".join([f.short_path for f in ctx.attr.src[OrfsDepInfo].files]),
            "${CONFIG}": ctx.attr.src[OrfsDepInfo].config.short_path,
            "${MAKE}": ctx.attr.src[OrfsDepInfo].make.short_path,
        } | openroad_substitutions(ctx),
    )
    return [
        DefaultInfo(
            executable = exe,
            files = depset(ctx.attr.src[OrfsDepInfo].files),
            runfiles = ctx.attr.src[OrfsDepInfo].runfiles,
        ),
    ]

def flow_attrs():
    return {
        "arguments": attr.string_dict(
            doc = "Dictionary of additional flow arguments.",
            default = {},
        ),
        "data": attr.label_list(
            doc = "List of additional flow data.",
            allow_files = True,
            default = [],
        ),
        "variant": attr.string(
            doc = "Variant of the used flow.",
            default = "base",
        ),
        "_deploy_template": attr.label(
            default = ":deploy.tpl",
            allow_single_file = True,
        ),
        "_make_template": attr.label(
            default = ":make.tpl",
            allow_single_file = True,
        ),
    }

def yosys_only_attrs():
    return {
        "verilog_files": attr.label_list(
            allow_files = [
                ".v",
                ".sv",
            ],
            allow_rules = [
            ],
            providers = [DefaultInfo],
        ),
        "deps": attr.label_list(
            default = [],
            providers = [OrfsInfo, TopInfo],
        ),
        "module_top": attr.string(mandatory = True),
        "pdk": attr.label(
            doc = "Process design kit.",
            default = Label("@docker_orfs//:asap7"),
            providers = [PdkInfo],
        ),
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile"),
        ),
        "_abc": attr.label(
            doc = "Abc binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:yosys-abc"),
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:yosys"),
        ),
        "_make": attr.label(
            doc = "make binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:make"),
        ),
        "_tcl": attr.label(
            doc = "Tcl library.",
            allow_files = True,
            default = Label("@docker_orfs//:tcl8.6"),
        ),
    }

def openroad_only_attrs():
    return {
        "src": attr.label(
            providers = [DefaultInfo],
        ),
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile"),
        ),
        "_make": attr.label(
            doc = "make binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:make"),
        ),
        "_openroad": attr.label(
            doc = "OpenROAD binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:openroad"),
        ),
        "_klayout": attr.label(
            doc = "Klayout binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:klayout"),
        ),
        "_ruby": attr.label(
            doc = "Ruby library.",
            allow_files = True,
            default = Label("@docker_orfs//:ruby3.0.0"),
        ),
        "_ruby_dynamic": attr.label(
            doc = "Ruby dynamic library.",
            allow_files = True,
            default = Label("@docker_orfs//:ruby_dynamic3.0.0"),
        ),
        "_tcl": attr.label(
            doc = "Tcl library.",
            allow_files = True,
            default = Label("@docker_orfs//:tcl8.6"),
        ),
        "_opengl": attr.label(
            doc = "OpenGL drivers.",
            allow_files = True,
            default = Label("@docker_orfs//:opengl"),
        ),
        "_qt_plugins": attr.label(
            doc = "Qt plugins.",
            allow_files = True,
            default = Label("@docker_orfs//:qt_plugins"),
        ),
        "_gio_modules": attr.label(
            doc = "GIO modules.",
            allow_files = True,
            default = Label("@docker_orfs//:gio_modules"),
        ),
    }

def yosys_attrs():
    return flow_attrs() | yosys_only_attrs()

def openroad_attrs():
    return flow_attrs() | openroad_only_attrs()

def _module_top(ctx):
    return ctx.attr.module_top if hasattr(ctx.attr, "module_top") else ctx.attr.src[TopInfo].module_top

def _platform(ctx):
    return ctx.attr.pdk[PdkInfo].name if hasattr(ctx.attr, "pdk") else ctx.attr.src[PdkInfo].name

def _required_arguments(ctx):
    return {
        "PLATFORM": _platform(ctx),
        "DESIGN_NAME": _module_top(ctx),
        "FLOW_VARIANT": ctx.attr.variant,
        "GENERATE_ARTIFACTS_ON_FAILURE": "1",
    }

def _orfs_arguments(*args, short = False):
    gds = depset([info.gds for info in args if info.gds], transitive = [info.additional_gds for info in args])
    lefs = depset([info.lef for info in args if info.lef], transitive = [info.additional_lefs for info in args])
    libs = depset([info.lib for info in args if info.lib], transitive = [info.additional_libs for info in args])

    args = {}
    if gds.to_list():
        args["ADDITIONAL_GDS"] = " ".join([file.short_path if short else file.path for file in gds.to_list()])
    if lefs.to_list():
        args["ADDITIONAL_LEFS"] = " ".join([file.short_path if short else file.path for file in lefs.to_list()])
    if libs.to_list():
        args["ADDITIONAL_LIBS"] = " ".join([file.short_path if short else file.path for file in libs.to_list()])
    return args

def _verilog_arguments(files, short = False):
    return {"VERILOG_FILES": " ".join([file.short_path if short else file.path for file in files])}

def _block_arguments(ctx):
    return {"MACROS": " ".join([dep[TopInfo].module_top for dep in ctx.attr.deps])} if ctx.attr.deps else {}

def _config_content(args):
    return "".join(["export {}={}\n".format(*pair) for pair in args.items()])

def _data_arguments(ctx):
    return {k: ctx.expand_location(v, ctx.attr.data) for k, v in ctx.attr.arguments.items()}

def _add_optional_generation_to_command(command, optional_files):
    if optional_files:
        return " && ".join([
            "mkdir -p " + " ".join([result.dirname for result in optional_files]),
            "touch " + " ".join([result.path for result in optional_files]),
            command,
        ])
    return command

def _work_home(ctx):
    if ctx.label.package:
        return "/".join([ctx.genfiles_dir.path, ctx.label.package])
    return ctx.genfiles_dir.path

def _artifact_dir(ctx, category):
    return "/".join([
        category,
        _platform(ctx),
        _module_top(ctx),
        ctx.attr.non_mocked_variant if hasattr(ctx.attr, "non_mocked_variant") and ctx.attr.non_mocked_variant else ctx.attr.variant,
    ])

def _declare_artifact(ctx, category, name):
    return ctx.actions.declare_file("/".join([_artifact_dir(ctx, category), name]))

def _yosys_env(ctx, config):
    return _default_env(ctx, config) | {
        "ABC": ctx.executable._abc.path,
        "YOSYS_EXE": ctx.executable._yosys.path,
        "OPENROAD_EXE": "",
        "TCL_LIBRARY": commonpath(ctx.files._tcl),
    }

def _yosys_impl(ctx):
    all_arguments = _data_arguments(ctx) | _required_arguments(ctx) | _orfs_arguments(*[dep[OrfsInfo] for dep in ctx.attr.deps]) | _block_arguments(ctx)
    config = _declare_artifact(ctx, "results", "1_synth.mk")
    ctx.actions.write(
        output = config,
        content = _config_content(all_arguments),
    )

    canon_logs = []
    for log in ["1_1_yosys_canonicalize.log"]:
        canon_logs.append(_declare_artifact(ctx, "logs", log))

    canon_output = _declare_artifact(ctx, "results", "1_synth.rtlil")

    command = _add_optional_generation_to_command(ctx.executable._make.path + " $@", canon_logs)

    transitive_inputs = [
        ctx.attr.pdk[PdkInfo].files,
        ctx.attr._abc[DefaultInfo].default_runfiles.files,
        ctx.attr._abc[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._yosys[DefaultInfo].default_runfiles.files,
        ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._makefile[DefaultInfo].default_runfiles.files,
        ctx.attr._makefile[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._make[DefaultInfo].default_runfiles.files,
        ctx.attr._make[DefaultInfo].default_runfiles.symlinks,
        depset([dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds]),
        depset([dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef]),
        depset([dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib]),
    ]

    for datum in ctx.attr.data:
        transitive_inputs.append(datum.default_runfiles.files)
        transitive_inputs.append(datum.default_runfiles.symlinks)

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile.path, canon_output.path],
        command = command,
        env = _verilog_arguments(ctx.files.verilog_files) | _yosys_env(ctx, config),
        inputs = depset(
            ctx.files.verilog_files +
            ctx.files.data +
            ctx.files._tcl +
            [
                config,
                ctx.executable._abc,
                ctx.executable._yosys,
                ctx.executable._make,
                ctx.file._makefile,
            ],
            transitive = transitive_inputs,
        ),
        outputs = [canon_output] + canon_logs,
    )

    synth_logs = []
    for log in ["1_1_yosys.log", "1_1_yosys_metrics.log", "1_1_yosys_hier_report.log"]:
        synth_logs.append(_declare_artifact(ctx, "logs", log))

    synth_outputs = []
    for output in ["1_synth.v", "1_synth.sdc", "mem.json"]:
        synth_outputs.append(_declare_artifact(ctx, "results", output))

    command = _add_optional_generation_to_command(ctx.executable._make.path + " $@", synth_logs)
    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile.path, "--old-file", canon_output.path, "yosys-dependencies"] +
                    [f.path for f in synth_outputs],
        command = command,
        env = _verilog_arguments([]) | _yosys_env(ctx, config),
        inputs = depset(
            ctx.files.data +
            ctx.files._tcl +
            [
                canon_output,
                config,
                ctx.executable._abc,
                ctx.executable._yosys,
                ctx.executable._make,
                ctx.file._makefile,
            ],
            transitive = transitive_inputs,
        ),
        outputs = synth_outputs + synth_logs,
    )

    config_short = _declare_artifact(ctx, "results", "1_synth.short.mk")
    ctx.actions.write(
        output = config_short,
        content = _config_content(_data_arguments(ctx) | _required_arguments(ctx) | _block_arguments(ctx) | _orfs_arguments(short = True, *[dep[OrfsInfo] for dep in ctx.attr.deps]) | _verilog_arguments(ctx.files.verilog_files, short = True)),
    )

    make = ctx.actions.declare_file("make_1_synth")
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = default_substitutions | flow_substitutions(ctx) | yosys_substitutions(ctx) | {'"$@"': 'WORK_HOME="./{}" DESIGN_CONFIG="config.mk" "$@"'.format(ctx.label.package)},
    )

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = default_substitutions | {
            "${GENFILES}": " ".join([f.short_path for f in synth_outputs + [config_short] + canon_logs + synth_logs]),
            "${CONFIG}": config_short.short_path,
            "${MAKE}": make.short_path,
        },
    )

    return [
        DefaultInfo(
            executable = exe,
            files = depset(
                synth_outputs + [canon_output] + [dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds] +
                [dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef] +
                [dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib],
            ),
            runfiles = ctx.runfiles(
                synth_outputs + canon_logs + synth_logs + [canon_output, config_short, make, ctx.executable._yosys, ctx.executable._make, ctx.file._makefile] +
                ctx.files.verilog_files + ctx.files.data + ctx.files._tcl,
                transitive_files = depset(transitive = transitive_inputs),
            ),
        ),
        OutputGroupInfo(
            deps = depset(
                [config] + ctx.files.verilog_files + ctx.files.data +
                [dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds] +
                [dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef] +
                [dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib],
            ),
            logs = depset(canon_logs + synth_logs),
            reports = depset([]),
            **{f.basename: depset([f]) for f in [canon_output, config] + synth_outputs}
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            files = [config_short] + ctx.files.verilog_files + ctx.files.data,
            runfiles = ctx.runfiles(transitive_files = depset(
                [config_short, make, ctx.executable._yosys, ctx.executable._make, ctx.file._makefile] +
                ctx.files.verilog_files + ctx.files.data + ctx.files._tcl,
                transitive = transitive_inputs,
            )),
        ),
        OrfsInfo(
            stage = "1_synth",
            odb = None,
            gds = None,
            lef = None,
            lib = None,
            additional_gds = depset([dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds]),
            additional_lefs = depset([dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef]),
            additional_libs = depset([dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib]),
        ),
        ctx.attr.pdk[PdkInfo],
        TopInfo(
            module_top = ctx.attr.module_top,
        ),
        LoggingInfo(
            logs = depset(canon_logs + synth_logs),
            reports = depset([]),
        ),
    ]

orfs_synth = rule(
    implementation = _yosys_impl,
    attrs = yosys_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsDepInfo, OrfsInfo, PdkInfo, TopInfo, LoggingInfo],
    executable = True,
)

def _make_impl(ctx, stage, steps, forwarded_names = [], result_names = [], object_names = [], log_names = [], report_names = [], extra_arguments = {}):
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

    Returns:
        A list of providers. The returned PdkInfo and TopInfo providers are taken from the first
        target of a ctx.attr.srcs list.
    """
    all_arguments = extra_arguments | _data_arguments(ctx) | _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo])
    config = _declare_artifact(ctx, "results", stage + ".mk")
    ctx.actions.write(
        output = config,
        content = _config_content(all_arguments),
    )

    results = []
    for result in result_names:
        results.append(_declare_artifact(ctx, "results", result))

    objects = []
    for object in object_names:
        objects.append(_declare_artifact(ctx, "objects", object))

    logs = []
    for log in log_names:
        logs.append(_declare_artifact(ctx, "logs", log))

    reports = []
    for report in report_names:
        reports.append(_declare_artifact(ctx, "reports", report))

    forwards = [f for f in ctx.files.src if f.basename in forwarded_names]

    info = {}
    for file in forwards + results:
        info[file.extension] = file

    transitive_inputs = [
        ctx.attr.src[OrfsInfo].additional_gds,
        ctx.attr.src[OrfsInfo].additional_lefs,
        ctx.attr.src[OrfsInfo].additional_libs,
        ctx.attr.src[PdkInfo].files,
        ctx.attr._openroad[DefaultInfo].default_runfiles.files,
        ctx.attr._openroad[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._klayout[DefaultInfo].default_runfiles.files,
        ctx.attr._klayout[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._makefile[DefaultInfo].default_runfiles.files,
        ctx.attr._makefile[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._make[DefaultInfo].default_runfiles.files,
        ctx.attr._make[DefaultInfo].default_runfiles.symlinks,
    ]

    for datum in ctx.attr.data:
        transitive_inputs.append(datum.default_runfiles.files)
        transitive_inputs.append(datum.default_runfiles.symlinks)

    extra_envs_deps = []
    extra_envs_args = {}
    command = ctx.executable._make.path + " $@"
    if hasattr(ctx.file, "extra_envs") and ctx.file.extra_envs:
        command = "source {}; {}".format(ctx.file.extra_envs.path, command)
        extra_envs_deps = [ctx.file.extra_envs]
        extra_envs_args = {
            "${EXTRA_ENVS}": ctx.file.extra_envs.short_path,
        }
    command = _add_optional_generation_to_command(command, reports + logs)
    if hasattr(ctx.attr, "non_mocked_variant") and ctx.attr.non_mocked_variant:
        # Move mocked result to non-mocked variant
        for file in results + objects + logs + reports:
            command = command + " && mv {} {}".format(
                file.path.replace("/{}/".format(ctx.attr.non_mocked_variant), "/{}/".format(ctx.attr.variant)),
                file.path,
            )

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile.path] + steps,
        command = command,
        env = _run_env(ctx, config) | {
            "KLAYOUT_CMD": ctx.executable._klayout.path,
            "STDBUF_CMD": "",
            "RUBYLIB": ":".join([commonpath(ctx.files._ruby), commonpath(ctx.files._ruby_dynamic)]),
            "DLN_LIBRARY_PATH": commonpath(ctx.files._ruby_dynamic),
            "QT_QPA_PLATFORM_PLUGIN_PATH": commonpath(ctx.files._qt_plugins),
            "QT_PLUGIN_PATH": commonpath(ctx.files._qt_plugins),
        },
        inputs = depset(
            ctx.files.src +
            ctx.files.data +
            ctx.files._ruby +
            ctx.files._ruby_dynamic +
            ctx.files._tcl +
            extra_envs_deps +
            [config, ctx.executable._openroad, ctx.executable._klayout, ctx.file._makefile, ctx.executable._make],
            transitive = transitive_inputs,
        ),
        outputs = results + objects + logs + reports,
    )

    config_short = _declare_artifact(ctx, "results", stage + ".short.mk")
    ctx.actions.write(
        output = config_short,
        content = _config_content(extra_arguments | _data_arguments(ctx) | _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo], short = True)),
    )

    make = ctx.actions.declare_file("make_{}_{}".format(ctx.attr.variant, stage))
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = default_substitutions | flow_substitutions(ctx) | openroad_substitutions(ctx) | extra_envs_args | {'"$@"': 'WORK_HOME="./{}" DESIGN_CONFIG="config.mk" "$@"'.format(ctx.label.package)},
    )

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = default_substitutions | {
            "${GENFILES}": " ".join([f.short_path for f in [config_short] + results + logs + reports + ctx.files.data + extra_envs_deps]),
            "${CONFIG}": config_short.short_path,
            "${MAKE}": make.short_path,
        },
    )

    return [
        DefaultInfo(
            executable = exe,
            files = depset(
                forwards + reports + results,
                transitive = [
                    ctx.attr.src[OrfsInfo].additional_gds,
                    ctx.attr.src[OrfsInfo].additional_lefs,
                    ctx.attr.src[OrfsInfo].additional_libs,
                ],
            ),
            runfiles = ctx.runfiles(
                [config_short, make, ctx.executable._openroad, ctx.executable._klayout, ctx.executable._make, ctx.file._makefile] +
                forwards + results + logs + reports + ctx.files.data + extra_envs_deps + ctx.files._ruby + ctx.files._ruby_dynamic + ctx.files._tcl + ctx.files._opengl + ctx.files._qt_plugins + ctx.files._gio_modules,
                transitive_files = depset(transitive = transitive_inputs + [ctx.attr.src[LoggingInfo].logs, ctx.attr.src[LoggingInfo].reports]),
            ),
        ),
        OutputGroupInfo(
            deps = depset(
                [config_short] + ctx.files.src + ctx.files.data,
                transitive = [
                    ctx.attr.src[OrfsInfo].additional_gds,
                    ctx.attr.src[OrfsInfo].additional_lefs,
                    ctx.attr.src[OrfsInfo].additional_libs,
                ],
            ),
            logs = depset(logs),
            reports = depset(reports),
            **{f.basename: depset([f]) for f in [config] + results + objects + logs + reports}
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            files = [config_short] + ctx.files.src + ctx.files.data,
            runfiles = ctx.runfiles(transitive_files = depset(
                [config_short, make, ctx.executable._openroad, ctx.executable._klayout, ctx.executable._make, ctx.file._makefile, ctx.executable._make] +
                ctx.files.src + ctx.files.data + ctx.files._ruby + ctx.files._ruby_dynamic + ctx.files._tcl + ctx.files._opengl + ctx.files._qt_plugins + ctx.files._gio_modules,
                transitive = transitive_inputs,
            )),
        ),
        OrfsInfo(
            stage = stage,
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
        ),
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
    ]

def add_orfs_make_rule_(
        implementation,
        attrs = openroad_attrs(),
        provides = [DefaultInfo, OutputGroupInfo, OrfsDepInfo, OrfsInfo, LoggingInfo, PdkInfo, TopInfo],
        executable = True):
    return rule(
        implementation = implementation,
        attrs = attrs,
        provides = provides,
        executable = executable,
    )

orfs_floorplan = add_orfs_make_rule_(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "2_floorplan",
        steps = ["do-floorplan"],
        result_names = [
            "2_floorplan.odb",
            "2_floorplan.sdc",
        ],
        log_names = [
            "2_1_floorplan.log",
            "2_2_floorplan_io.log",
            "2_3_floorplan_tdms.log",
            "2_4_floorplan_macro.log",
            "2_5_floorplan_tapcell.log",
            "2_6_floorplan_pdn.log",
        ],
        report_names = [
            "2_floorplan_final.rpt",
        ],
    ),
    attrs = openroad_attrs() | {
        "extra_envs": attr.label(
            doc = "File with exported environmenta variables.",
            allow_single_file = True,
        ),
    },
)

orfs_place = add_orfs_make_rule_(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "3_place",
        steps = ["do-place"],
        result_names = [
            "3_place.odb",
            "3_place.sdc",
        ],
        log_names = [
            "3_1_place_gp_skip_io.log",
            "3_2_place_iop.log",
            "3_3_place_gp.log",
            "3_4_place_resized.log",
            "3_5_place_dp.log",
        ],
        report_names = [],
    ),
)

orfs_cts = add_orfs_make_rule_(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "4_cts",
        steps = ["do-cts"],
        result_names = [
            "4_cts.odb",
            "4_cts.sdc",
        ],
        log_names = [
            "4_1_cts.log",
        ],
        report_names = [
            "4_cts_final.rpt",
        ],
    ),
)

orfs_grt = add_orfs_make_rule_(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "5_1_grt",
        steps = [
            "do-5_1_grt",
        ],
        forwarded_names = [
            "4_cts.sdc",
        ],
        result_names = [
            "5_1_grt.odb",
        ],
        log_names = [
            "5_1_grt.log",
        ],
        report_names = [
            "5_global_route.rpt",
            "congestion.rpt",
        ],
    ),
    attrs = openroad_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsDepInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = True,
)

orfs_route = add_orfs_make_rule_(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "5_2_route",
        steps = [
            "do-5_2_fillcell",
            "do-5_3_route",
            "do-5_route",
            "do-5_route.sdc",
        ],
        result_names = [
            "5_route.odb",
            "5_route.sdc",
        ],
        log_names = [
            "5_2_fillcell.log",
            "5_3_route.log",
        ],
        report_names = [
            "5_route_drc.rpt",
        ],
    ),
)

orfs_final = add_orfs_make_rule_(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "6_final",
        steps = ["do-final"],
        result_names = [
            "6_final.gds",
            "6_final.odb",
            "6_final.sdc",
            "6_final.spef",
        ],
        object_names = [
            "klayout.lyt",
        ],
        log_names = [
            "6_1_merge.log",
            "6_report.log",
            "6_report.json",
        ],
        report_names = [
            "6_finish.rpt",
            "VDD.rpt",
            "VSS.rpt",
        ],
    ),
)

def _extensionless_basename(file):
    return file.basename.removesuffix("." + file.extension)

orfs_abstract = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "7_abstract",
        steps = ["do-generate_abstract"],
        forwarded_names = [
            "6_final.gds",
        ],
        result_names = [
            "{}.lef".format(ctx.attr.src[TopInfo].module_top),
            "{}.lib".format(ctx.attr.src[TopInfo].module_top),
        ],
        log_names = [
            "generate_abstract.log",
        ],
        extra_arguments =
            {"ABSTRACT_SOURCE": _extensionless_basename(ctx.attr.src[OrfsInfo].odb)},
    ),
    attrs = openroad_attrs() | {
        "non_mocked_variant": attr.string(
            default = "",
            doc = "FLOW_VARIANT of the non-mocked flow",
        ),
    },
    provides = [DefaultInfo, OutputGroupInfo, OrfsDepInfo, OrfsInfo, LoggingInfo, PdkInfo, TopInfo],
    executable = True,
)

orfs_deps = rule(
    implementation = _deps_impl,
    attrs = {
        "src": attr.label(
            providers = [OrfsDepInfo],
        ),
        "_deploy_template": attr.label(
            default = ":deploy.tpl",
            allow_single_file = True,
        ),
    } | openroad_attrs(),
    executable = True,
)

STAGE_IMPLS = [
    struct(stage = "synth", impl = orfs_synth),
    struct(stage = "floorplan", impl = orfs_floorplan),
    struct(stage = "place", impl = orfs_place),
    struct(stage = "cts", impl = orfs_cts),
    struct(stage = "grt", impl = orfs_grt),
    struct(stage = "route", impl = orfs_route),
    struct(stage = "final", impl = orfs_final),
]

ABSTRACT_IMPL = struct(stage = "generate_abstract", impl = orfs_abstract)

# A stage argument is used in one or more stages. This is metainformation
# about the ORFS code that there is no known nice way for ORFS to
# provide.
STAGE_ARGS_USES = {
    "PLACE_DENSITY": ["floorplan", "place"],
    "SDC_FILE": ["synth"],
    "IO_CONSTRAINTS": ["floorplan", "place"],
    "PLACE_PINS_ARGS": ["floorplan", "place"],
    "CORE_UTILIZATION": ["floorplan"],
    "CORE_AREA": ["floorplan"],
    "DIE_AREA": ["floorplan"],
    "CORE_ASPECT_RATIO": ["floorplan"],
    "REMOVE_ABC_BUFFERS": ["floorplan"],
    "PDN_TCL": ["floorplan"],
    "MACRO_PLACEMENT_TCL": ["floorplan"],
    "TNS_END_PERCENT": ["cts", "floorplan", "grt"],
    "SKIP_CTS_REPAIR_TIMING": ["cts"],
    "CORE_MARGIN": ["floorplan"],
    "SKIP_REPORT_METRICS": ["all"],
    "SYNTH_HIERARCHICAL": ["synth"],
    "RTLMP_FLOW": ["floorplan"],
    "MACRO_PLACE_HALO": ["floorplan"],
    "GND_NETS_VOLTAGES": ["final"],
    "PWR_NETS_VOLTAGES": ["final"],
    "GPL_ROUTABILITY_DRIVEN": ["place"],
    "GPL_TIMING_DRIVEN": ["place"],
    "SKIP_INCREMENTAL_REPAIR": ["grt"],
    "MIN_ROUTING_LAYER": ["place", "grt", "route", "final"],
    "MAX_ROUTING_LAYER": ["place", "grt", "route", "final"],
    "ROUTING_LAYER_ADJUSTMENT": ["place", "grt", "route", "final"],
    "FILL_CELLS": ["route"],
    "TAPCELL_TCL": ["floorplan"],
}

def get_stage_args(stage, stage_args, args):
    """Returns the arguments for a specific stage.

    Args:
        stage: The stage name.
        stage_args: the dictionary of stages with each stage having a dictionary of arguments
        args: a dictionary of arguments automatically assigned to a stage
    Returns:
      A dictionary of arguments for the stage.
    """
    return ({
                arg: value
                for arg, value in args.items()
                if stage in STAGE_ARGS_USES[arg] or "all" in STAGE_ARGS_USES[arg]
            } |
            stage_args.get(stage, {}))

def _deep_dict_copy(d):
    new_d = dict(d)
    for k, v in new_d.items():
        new_d[k] = dict(v)
    return new_d

def _mock_area_targets(
        name,
        mock_area,
        steps,
        verilog_files = [],
        macros = [],
        stage_sources = {},
        stage_args = {},
        args = {},
        variant = None,
        visibility = ["//visibility:private"]):
    steps.append(ABSTRACT_IMPL)

    # Make a copy of args
    stage_args = _deep_dict_copy(stage_args)
    args = dict(args)
    floorplan_args = stage_args.get("floorplan", {})
    for arg in ("DIE_AREA", "CORE_AREA", "CORE_UTILIZATION"):
        args.pop(arg, None)
        floorplan_args.pop(arg, None)
    stage_args["floorplan"] = floorplan_args
    stage_args.get("generate_abstract", {}).pop("ABSTRACT_SOURCE", None)

    # SYNTH_GUT=1 breaks floorplan for some targets, disabling for now
    # synth_args = stage_args.get("synth", {})
    # synth_args["SYNTH_GUT"] = "1"
    # stage_args["synth"] = synth_args

    name_variant = name + "_" + variant if variant else name
    mock_variant = variant + "_mock_area" if variant else "mock_area"

    synth_step = steps[0]
    synth_step.impl(
        name = "{}_{}_mock_area".format(name_variant, synth_step.stage),
        arguments = get_stage_args(synth_step.stage, stage_args, args),
        data = stage_sources.get(synth_step.stage, []),
        deps = macros,
        module_top = name,
        variant = mock_variant,
        verilog_files = verilog_files,
        visibility = visibility,
    )
    orfs_deps(
        name = "{}_{}_mock_area_deps".format(name_variant, synth_step.stage),
        src = "{}_{}_mock_area".format(name_variant, synth_step.stage),
    )

    orfs_run_mock_area(
        name = "{}_mock_area".format(name_variant),
        src = "{}_floorplan".format(name_variant),
        variant = variant,
        extra_envs = {"MOCK_AREA": str(mock_area)},
    )

    if not variant:
        variant = "base"
    extra_args = {"extra_envs": "{}_mock_area".format(name_variant)}
    last = len(steps) - 2
    for i, (step, prev) in enumerate(zip(steps[1:], steps)):
        suffix = "_mock_area"
        if i == last:
            suffix = ""
            extra_args = extra_args | {
                "non_mocked_variant": variant,
            }
        step.impl(
            name = "{}_{}{}".format(name_variant, step.stage, suffix),
            src = "{}_{}_mock_area".format(name_variant, prev.stage, suffix),
            arguments = get_stage_args(step.stage, stage_args, args),
            data = stage_sources.get(step.stage, []),
            variant = mock_variant,
            visibility = visibility,
            **extra_args
        )
        orfs_deps(
            name = "{}_{}{}_deps".format(name_variant, step.stage, suffix),
            src = "{}_{}{}".format(name_variant, step.stage, suffix),
        )
        extra_args = {}

def orfs_flow(
        name,
        verilog_files = [],
        macros = [],
        stage_sources = {},
        stage_args = {},
        args = {},
        abstract_stage = None,
        variant = None,
        mock_area = None,
        visibility = ["//visibility:private"]):
    """
    Creates targets for running physical design flow with OpenROAD-flow-scripts.

    Args:
      name: name of the macro target
      verilog_files: list of verilog sources of the design
      macros: list of macros required to run physical design flow for this design
      stage_sources: dictionary keyed by ORFS stages with lists of stage-specific sources
      stage_args: dictionary keyed by ORFS stages with lists of stage-specific arguments
      args: dictionary of additional arguments to the flow, automatically assigned to stages
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      variant: name of the target variant, added right after the module name
      mock_area: floating point number, scale the die width/height by this amount, default no scaling
      visibility: the visibility attribute on a target controls whether the target can be used in other packages
    """
    steps = []
    for step in STAGE_IMPLS:
        steps.append(step)
        if step.stage == abstract_stage:
            break
    if (abstract_stage != STAGE_IMPLS[0].stage) and not mock_area:
        steps.append(ABSTRACT_IMPL)

    name_variant = name + "_" + variant if variant else name

    synth_step = steps[0]
    synth_step.impl(
        name = "{}_{}".format(name_variant, synth_step.stage),
        arguments = get_stage_args(synth_step.stage, stage_args, args),
        data = stage_sources.get(synth_step.stage, []),
        deps = macros,
        module_top = name,
        variant = variant,
        verilog_files = verilog_files,
        visibility = visibility,
    )
    orfs_deps(
        name = "{}_{}_deps".format(name_variant, synth_step.stage),
        src = "{}_{}".format(name_variant, synth_step.stage),
    )

    for step, prev in zip(steps[1:], steps):
        step.impl(
            name = "{}_{}".format(name_variant, step.stage),
            src = "{}_{}".format(name_variant, prev.stage),
            arguments = get_stage_args(step.stage, stage_args, args),
            data = stage_sources.get(step.stage, []),
            variant = variant,
            visibility = visibility,
        )
        orfs_deps(
            name = "{}_{}_deps".format(name_variant, step.stage),
            src = "{}_{}".format(name_variant, step.stage),
        )

    if mock_area:
        if variant == "mock_area":
            fail("'mock_area' variant is used by mock_area targets, please choose different one")
        _mock_area_targets(
            name,
            mock_area,
            steps,
            verilog_files,
            macros,
            stage_sources,
            stage_args,
            args,
            variant,
            visibility,
        )
