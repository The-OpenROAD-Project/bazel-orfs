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
        env = odb_environment(ctx) | {
            "HOME": _work_home(ctx),
            "WORK_HOME": _work_home(ctx),
            "DESIGN_CONFIG": config.path,
            "FLOW_HOME": ctx.file._makefile.dirname,
            "OPENROAD_EXE": ctx.executable._openroad.path,
            "YOSYS_EXE": "",
            "TCL_LIBRARY": commonpath(ctx.files._tcl),
            "GUI_ARGS": "-exit",
            "GUI_SOURCE": ctx.file.script.path,
        },
        inputs = depset(
            ctx.files.src +
            ctx.files.data +
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
        "_tcl": attr.label(
            doc = "Tcl library.",
            allow_files = True,
            default = Label("@docker_orfs//:tcl8.6"),
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

def preloadwrap(command, library):
    """
    Return `command` wrapped in an `LD_PRELOAD` statement.

    Args:
      command: The command to be wrapped.
      library: The library to be preloaded.

    Returns:
      The wrapped command.
    """
    return "LD_PRELOAD=" + library + " " + command

def envwrap(command):
    """
    Return `command` argument wrapped in an `env -S` statement.

    Args:
      command: The command to be wrapped.

    Returns:
      The wrapped command.
    """
    return "env -S " + command

def pathatlevel(path, level):
    """
    Return `path` argument, `level` directories back.

    Args:
      path: Path to be prepended.
      level: The level of the parent directory to go to.

    Returns:
      The edited path.
    """
    return "/".join([".." for _ in range(level)] + [path])

def flow_substitutions(ctx):
    return {
        "${MAKE_PATH}": ctx.executable._make.path,
        "${MAKEFILE_PATH}": ctx.file._makefile.path,
        "${FLOW_HOME}": ctx.file._makefile.dirname,
    }

def openroad_substitutions(ctx):
    return {
        "${MAKE_PATH}": ctx.executable._make.path,
        "${YOSYS_PATH}": "",
        "${OPENROAD_PATH}": ctx.executable._openroad.path,
        "${KLAYOUT_PATH}": ctx.executable._klayout.path,
        "${TCL_LIBRARY}": commonpath(ctx.files._tcl),
        "${LIBGL_DRIVERS_PATH}": commonpath(ctx.files._opengl),
        "${QT_PLUGIN_PATH}": commonpath(ctx.files._qt_plugins),
        "${QT_QPA_PLATFORM_PLUGIN_PATH}": commonpath(ctx.files._qt_plugins),
        "${GIO_MODULE_DIR}": commonpath(ctx.files._gio_modules),
    }

def yosys_substitutions(ctx):
    return {
        "${MAKE_PATH}": ctx.executable._make.path,
        "${YOSYS_PATH}": ctx.executable._yosys.path,
        "${OPENROAD_PATH}": "",
    }

def _deps_impl(ctx):
    exe = _declare_artifact(ctx, "results", ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = {
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
        "_libstdbuf": attr.label(
            allow_single_file = ["libstdbuf.so"],
            default = Label("@docker_orfs//:libstdbuf.so"),
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
    return "/".join([category, _platform(ctx), _module_top(ctx), ctx.attr.variant])

def _declare_artifact(ctx, category, name):
    return ctx.actions.declare_file("/".join([_artifact_dir(ctx, category), name]))

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
        env = _verilog_arguments(ctx.files.verilog_files) | {
            "HOME": _work_home(ctx),
            "WORK_HOME": _work_home(ctx),
            "FLOW_HOME": ctx.file._makefile.dirname,
            "DESIGN_CONFIG": config.path,
            "ABC": ctx.executable._abc.path,
            "YOSYS_EXE": ctx.executable._yosys.path,
            "OPENROAD_EXE": "",
            "TCL_LIBRARY": commonpath(ctx.files._tcl),
        },
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
        env = _verilog_arguments([]) | {
            "HOME": _work_home(ctx),
            "WORK_HOME": _work_home(ctx),
            "FLOW_HOME": ctx.file._makefile.dirname,
            "DESIGN_CONFIG": config.path,
            "ABC": ctx.executable._abc.path,
            "YOSYS_EXE": ctx.executable._yosys.path,
            "OPENROAD_EXE": "",
        },
        inputs = depset(
            ctx.files.data +
            [
                canon_output,
                config,
                ctx.executable._abc,
                ctx.executable._yosys,
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
        substitutions = flow_substitutions(ctx) | yosys_substitutions(ctx) | {'"$@"': 'WORK_HOME="./{}" DESIGN_CONFIG="config.mk" "$@"'.format(ctx.label.package)},
    )

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = {
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
                synth_outputs + [canon_output, config_short, make, ctx.executable._yosys, ctx.file._makefile] +
                ctx.files.verilog_files + ctx.files.data + canon_logs + synth_logs,
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
                [config_short, make, ctx.executable._yosys, ctx.file._makefile] +
                ctx.files.verilog_files + ctx.files.data,
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
    odb = None
    gds = None
    lef = None
    lib = None
    for result in result_names:
        file = _declare_artifact(ctx, "results", result)
        if file.extension == "odb":
            odb = file
        elif file.extension == "gds":
            gds = file
        elif file.extension == "lef":
            lef = file
        elif file.extension == "lib":
            lib = file
        results.append(file)

    objects = []
    for object in object_names:
        objects.append(_declare_artifact(ctx, "objects", object))

    logs = []
    for log in log_names:
        logs.append(_declare_artifact(ctx, "logs", log))

    reports = []
    for report in report_names:
        reports.append(_declare_artifact(ctx, "reports", report))

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

    command = _add_optional_generation_to_command(ctx.executable._make.path + " $@", reports + logs)

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile.path] + steps,
        command = command,
        env = {
            "HOME": _work_home(ctx),
            "WORK_HOME": _work_home(ctx),
            "DESIGN_CONFIG": config.path,
            "FLOW_HOME": ctx.file._makefile.dirname,
            "OPENROAD_EXE": ctx.executable._openroad.path,
            "KLAYOUT_CMD": envwrap(preloadwrap(ctx.executable._klayout.path, ctx.file._libstdbuf.path)),
            "TCL_LIBRARY": commonpath(ctx.files._tcl),
            "QT_QPA_PLATFORM_PLUGIN_PATH": pathatlevel(commonpath(ctx.files._qt_plugins), 5),
            "QT_PLUGIN_PATH": commonpath(ctx.files._qt_plugins),
        },
        inputs = depset(
            ctx.files.src +
            ctx.files.data +
            ctx.files._tcl +
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

    make = ctx.actions.declare_file("make_{}".format(stage))
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = flow_substitutions(ctx) | openroad_substitutions(ctx) | {'"$@"': 'WORK_HOME="./{}" DESIGN_CONFIG="config.mk" "$@"'.format(ctx.label.package)},
    )

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = {
            "${GENFILES}": " ".join([f.short_path for f in [config_short] + results + logs + reports + ctx.files.data]),
            "${CONFIG}": config_short.short_path,
            "${MAKE}": make.short_path,
        },
    )

    return [
        DefaultInfo(
            executable = exe,
            files = depset(
                [f for f in ctx.files.src if f.basename in forwarded_names] + reports + results,
                transitive = [
                    ctx.attr.src[OrfsInfo].additional_gds,
                    ctx.attr.src[OrfsInfo].additional_lefs,
                    ctx.attr.src[OrfsInfo].additional_libs,
                ],
            ),
            runfiles = ctx.runfiles(
                [config_short, make, ctx.executable._openroad, ctx.executable._klayout, ctx.file._makefile] +
                results + ctx.files.data + ctx.files._tcl + ctx.files._opengl + ctx.files._qt_plugins + ctx.files._gio_modules + logs + reports,
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
                [config_short, make, ctx.executable._openroad, ctx.executable._klayout, ctx.file._makefile, ctx.executable._make] +
                ctx.files.src + ctx.files.data + ctx.files._tcl + ctx.files._opengl + ctx.files._qt_plugins + ctx.files._gio_modules,
                transitive = transitive_inputs,
            )),
        ),
        OrfsInfo(
            stage = stage,
            odb = odb,
            gds = gds,
            lef = lef,
            lib = lib,
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
        result_names = [
            "{}.lef".format(ctx.attr.src[TopInfo].module_top),
            "{}.lib".format(ctx.attr.src[TopInfo].module_top),
        ],
        extra_arguments =
            {"ABSTRACT_SOURCE": _extensionless_basename(ctx.attr.src[OrfsInfo].odb)},
    ),
    attrs = openroad_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsDepInfo, OrfsInfo, LoggingInfo, PdkInfo, TopInfo],
    executable = False,
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

def orfs_flow(
        name,
        verilog_files = [],
        macros = [],
        stage_sources = {},
        stage_args = {},
        abstract_stage = None,
        variant = None,
        visibility = ["//visibility:private"]):
    """
    Creates targets for running physical design flow with OpenROAD-flow-scripts.

    Args:
      name: name of the macro target
      verilog_files: list of verilog sources of the design
      macros: list of macros required to run physical design flow for this design
      stage_sources: dictionary keyed by ORFS stages with lists of stage-specific sources
      stage_args: dictionary keyed by ORFS stages with lists of stage-specific arguments
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      variant: name of the target variant, added right after the module name
      visibility: the visibility attribute on a target controls whether the target can be used in other packages
    """
    steps = []
    for step in STAGE_IMPLS:
        steps.append(step)
        if step.stage == abstract_stage:
            break
    if (abstract_stage != STAGE_IMPLS[0].stage):
        steps.append(ABSTRACT_IMPL)

    name_variant = name + "_" + variant if variant else name

    synth_step = steps[0]
    synth_step.impl(
        name = "{}_{}".format(name_variant, synth_step.stage),
        arguments = stage_args.get(synth_step.stage, {}),
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
            arguments = stage_args.get(step.stage, {}),
            data = stage_sources.get(step.stage, []),
            variant = variant,
            visibility = visibility,
        )
        orfs_deps(
            name = "{}_{}_deps".format(name_variant, step.stage),
            src = "{}_{}".format(name_variant, step.stage),
        )
