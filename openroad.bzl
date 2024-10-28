"""Rules for the building the OpenROAD-flow-scripts stages"""

load("@orfs_variable_metadata//:json.bzl", "orfs_variable_metadata")

def _map(function, iterable):
    return [function(x) for x in iterable]

def _union(*lists):
    merged_dict = {}
    for list1 in lists:
        dict1 = {key: True for key in list1}
        merged_dict.update(dict1)

    return list(merged_dict.keys())

OrfsInfo = provider(
    "The outputs of a OpenROAD-flow-scripts stage.",
    fields = [
        "stage",
        "config",
        "variant",
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
        "renames",
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

def _macro_impl(ctx):
    info = {}
    for field in ["odb", "gds", "lef", "lib"]:
        if not getattr(ctx.attr, field):
            continue
        for file in getattr(ctx.attr, field).files.to_list():
            info[file.extension] = file

    return [
        DefaultInfo(
            files = depset(ctx.files.odb + ctx.files.gds + ctx.files.lef + ctx.files.lib),
        ),
        OutputGroupInfo(
            **{f.basename: depset([f]) for f in ctx.files.odb + ctx.files.gds + ctx.files.lef + ctx.files.lib}
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
    } | {
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

def odb_environment(ctx):
    if ctx.attr.src[OrfsInfo].odb:
        return {"ODB_FILE": ctx.attr.src[OrfsInfo].odb.path}
    return {}

def orfs_environment(ctx):
    return {
        "HOME": _work_home(ctx),
        "STDBUF_CMD": "",
        "TCL_LIBRARY": commonpath(ctx.files._tcl),
        "WORK_HOME": _work_home(ctx),
    }

def flow_environment(ctx):
    return {
        "DLN_LIBRARY_PATH": commonpath(ctx.files._ruby_dynamic),
        "FLOW_HOME": ctx.file._makefile.dirname,
        "KLAYOUT_CMD": ctx.executable._klayout.path,
        "OPENROAD_EXE": ctx.executable._openroad.path,
        "QT_PLUGIN_PATH": commonpath(ctx.files._qt_plugins),
        "QT_QPA_PLATFORM_PLUGIN_PATH": commonpath(ctx.files._qt_plugins),
        "RUBYLIB": ":".join([commonpath(ctx.files._ruby), commonpath(ctx.files._ruby_dynamic)]),
    } | orfs_environment(ctx)

def yosys_environment(ctx):
    return {
        "ABC": ctx.executable._abc.path,
        "YOSYS_EXE": ctx.executable._yosys.path,
        "FLOW_HOME": ctx.file._makefile_yosys.dirname,
    } | orfs_environment(ctx)

def config_environment(config):
    return {"DESIGN_CONFIG": config.path}

def flow_inputs(ctx):
    return depset(
        [
            ctx.executable._klayout,
            ctx.executable._make,
            ctx.executable._openroad,
            ctx.file._makefile,
        ] +
        ctx.files._ruby +
        ctx.files._ruby_dynamic +
        ctx.files._tcl +
        ctx.files._opengl +
        ctx.files._qt_plugins +
        ctx.files._gio_modules,
        transitive = [
            ctx.attr._openroad[DefaultInfo].default_runfiles.files,
            ctx.attr._openroad[DefaultInfo].default_runfiles.symlinks,
            ctx.attr._klayout[DefaultInfo].default_runfiles.files,
            ctx.attr._klayout[DefaultInfo].default_runfiles.symlinks,
            ctx.attr._makefile[DefaultInfo].default_runfiles.files,
            ctx.attr._makefile[DefaultInfo].default_runfiles.symlinks,
            ctx.attr._make[DefaultInfo].default_runfiles.files,
            ctx.attr._make[DefaultInfo].default_runfiles.symlinks,
        ],
    )

def yosys_inputs(ctx):
    return depset(
        [
            ctx.executable._abc,
            ctx.executable._yosys,
            ctx.executable._make,
            ctx.file._makefile_yosys,
        ] +
        ctx.files._tcl,
        transitive = [
            ctx.attr._abc[DefaultInfo].default_runfiles.files,
            ctx.attr._abc[DefaultInfo].default_runfiles.symlinks,
            ctx.attr._yosys[DefaultInfo].default_runfiles.files,
            ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
            ctx.attr._makefile_yosys[DefaultInfo].default_runfiles.files,
            ctx.attr._makefile_yosys[DefaultInfo].default_runfiles.symlinks,
            ctx.attr._make[DefaultInfo].default_runfiles.files,
            ctx.attr._make[DefaultInfo].default_runfiles.symlinks,
        ],
    )

def data_inputs(ctx):
    return depset(
        ctx.files.data,
        transitive = [datum.default_runfiles.files for datum in ctx.attr.data] +
                     [datum.default_runfiles.symlinks for datum in ctx.attr.data],
    )

def source_inputs(ctx):
    return depset(
        ctx.files.src,
        transitive = [
            ctx.attr.src[OrfsInfo].additional_gds,
            ctx.attr.src[OrfsInfo].additional_lefs,
            ctx.attr.src[OrfsInfo].additional_libs,
            ctx.attr.src[PdkInfo].files,
        ],
    )

def rename_inputs(ctx):
    return depset(transitive = [
        target.files
        for target in ctx.attr.renamed_inputs.values()
    ])

def pdk_inputs(ctx):
    return depset(transitive = [ctx.attr.pdk[PdkInfo].files])

def deps_inputs(ctx):
    return depset(
        [dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds] +
        [dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef] +
        [dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib],
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
        "${DLN_LIBRARY_PATH}": commonpath(ctx.files._ruby_dynamic),
        "${FLOW_HOME}": ctx.file._makefile.dirname,
        "${GIO_MODULE_DIR}": commonpath(ctx.files._gio_modules),
        "${KLAYOUT_PATH}": ctx.executable._klayout.path,
        "${LIBGL_DRIVERS_PATH}": commonpath(ctx.files._opengl),
        "${MAKEFILE_PATH}": ctx.file._makefile.path,
        "${MAKE_PATH}": ctx.executable._make.path,
        "${OPENROAD_PATH}": ctx.executable._openroad.path,
        "${QT_PLUGIN_PATH}": commonpath(ctx.files._qt_plugins),
        "${RUBY_PATH}": commonpath(ctx.files._ruby),
        "${STDBUF_PATH}": "",
        "${TCL_LIBRARY}": commonpath(ctx.files._tcl),
    }

def yosys_substitutions(ctx):
    return {
        "${ABC}": ctx.executable._abc.path,
        "${YOSYS_PATH}": ctx.executable._yosys.path,
    }

def _deps_impl(ctx):
    exe = _declare_artifact(ctx, "results", ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = {
            "${GENFILES}": " ".join(sorted([f.short_path for f in ctx.attr.src[OrfsDepInfo].files.to_list()])),
            "${RENAMES}": " ".join(["{}:{}".format(rename.src, rename.dst) for rename in ctx.attr.src[OrfsDepInfo].renames]),
            "${CONFIG}": ctx.attr.src[OrfsDepInfo].config.short_path,
            "${MAKE}": ctx.attr.src[OrfsDepInfo].make.short_path,
        },
    )
    return [
        ctx.attr.src[OrfsInfo],
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        DefaultInfo(
            executable = exe,
            files = ctx.attr.src[OrfsDepInfo].files,
            runfiles = ctx.attr.src[OrfsDepInfo].runfiles,
        ),
    ]

def flow_provides():
    return [DefaultInfo, OutputGroupInfo, OrfsDepInfo, OrfsInfo, LoggingInfo, PdkInfo, TopInfo]

def orfs_attrs():
    return {
        "arguments": attr.string_dict(
            doc = "Dictionary of additional flow arguments.",
            default = {},
        ),
        "extra_configs": attr.label_list(
            doc = "List of additional flow configuration files.",
            allow_files = True,
            default = [],
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
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile"),
        ),
    }

def flow_attrs():
    return {
        "_deploy_template": attr.label(
            default = ":deploy.tpl",
            allow_single_file = True,
        ),
        "_make_template": attr.label(
            default = ":make.tpl",
            allow_single_file = True,
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
    } | orfs_attrs()

def yosys_only_attrs():
    return {
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
        "_makefile_yosys": attr.label(
            doc = "Top level makefile yosys.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile_yosys"),
        ),
    }

def renamed_inputs_attr():
    return {
        "renamed_inputs": attr.string_keyed_label_dict(
            default = {},
        ),
    }

def synth_attrs():
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
    }

def openroad_only_attrs():
    return {
        "src": attr.label(
            providers = [DefaultInfo],
        ),
    }

def yosys_attrs():
    # flow_attrs() is not used by synthesis, but by bazel run foo_synth to
    # open synthesis results in OpenROAD
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

    arguments = {}
    if gds.to_list():
        arguments["ADDITIONAL_GDS"] = " ".join(sorted([file.short_path if short else file.path for file in gds.to_list()]))
    if lefs.to_list():
        arguments["ADDITIONAL_LEFS"] = " ".join(sorted([file.short_path if short else file.path for file in lefs.to_list()]))
    if libs.to_list():
        arguments["ADDITIONAL_LIBS"] = " ".join(sorted([file.short_path if short else file.path for file in libs.to_list()]))
    return arguments

def _verilog_arguments(files, short = False):
    return {"VERILOG_FILES": " ".join(sorted([file.short_path if short else file.path for file in files]))}

def _config_content(arguments, paths):
    return ("".join(sorted(["export {}?={}\n".format(*pair) for pair in arguments.items()]) +
                    ["include {}\n".format(path) for path in paths]))

def _hack_away_prefix(arguments, prefix):
    return {k: v.removeprefix(prefix + "/") for k, v in arguments.items()}

def _data_arguments(ctx):
    return {k: ctx.expand_location(v, ctx.attr.data) for k, v in ctx.attr.arguments.items()}

def _generation_commands(optional_files):
    if optional_files:
        return [
            "mkdir -p " + " ".join(sorted([result.dirname for result in optional_files])),
            "touch " + " ".join(sorted([result.path for result in optional_files])),
        ]
    return []

def _input_commands(renames):
    cmds = []
    for rename in renames:
        cmds.extend(_mv_cmds(rename.src, rename.dst))
    return cmds

def _mv_cmds(src, dst):
    dir, _, _ = dst.rpartition("/")
    return [
        "mkdir -p {}".format(dir),
        "mv {} {}".format(src, dst),
    ]

def _remap(s, a, b):
    if s.endswith(a):
        return s.replace("/" + a, "/" + b)
    return s.replace("/" + a + "/", "/" + b + "/")

def _renames(ctx, inputs, short = False):
    """Move inputs to the expected input locations"""
    renames = []
    for file in inputs:
        if ctx.attr.src[OrfsInfo].variant != ctx.attr.variant:
            renames.append(struct(
                src = file.short_path if short else file.path,
                dst = _remap(file.short_path if short else file.path, ctx.attr.src[OrfsInfo].variant, ctx.attr.variant),
            ))

    # renamed_inputs win over variant renaming
    for file in inputs:
        if file.basename in ctx.attr.renamed_inputs:
            for src in ctx.attr.renamed_inputs[file.basename].files.to_list():
                renames.append(struct(
                    src = src.short_path if short else src.path,
                    dst = _remap(file.short_path if short else file.path, ctx.attr.src[OrfsInfo].variant, ctx.attr.variant),
                ))
    return renames

def _work_home(ctx):
    if ctx.label.package:
        return "/".join([ctx.genfiles_dir.path, ctx.label.package])
    return ctx.genfiles_dir.path

def _artifact_name(ctx, category, name = None):
    return "/".join([
        category,
        _platform(ctx),
        _module_top(ctx),
        ctx.attr.variant,
        name,
    ])

def _declare_artifact(ctx, category, name):
    return ctx.actions.declare_file(_artifact_name(ctx, category, name))

def _run_impl(ctx):
    config = ctx.attr.src[OrfsInfo].config
    outs = []
    for k in dir(ctx.outputs):
        outs.extend(getattr(ctx.outputs, k))

    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile.path,
            "run",
        ],
        command = ctx.executable._make.path + " $@",
        env = _data_arguments(ctx) |
              odb_environment(ctx) |
              flow_environment(ctx) |
              config_environment(config) |
              {"RUN_SCRIPT": ctx.file.script.path},
        inputs = depset(
            [config, ctx.file.script],
            transitive = [
                data_inputs(ctx),
                flow_inputs(ctx),
                source_inputs(ctx),
            ],
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
    attrs = openroad_attrs() | {
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

CANON_OUTPUT = "1_synth.rtlil"
SYNTH_OUTPUTS = ["1_synth.v", "1_synth.sdc", "mem.json"]

def _yosys_impl(ctx):
    all_arguments = _data_arguments(ctx) | _required_arguments(ctx) | _orfs_arguments(*[dep[OrfsInfo] for dep in ctx.attr.deps])
    config = _declare_artifact(ctx, "results", "1_synth.mk")
    ctx.actions.write(
        output = config,
        content = _config_content(all_arguments, [file.path for file in ctx.files.extra_configs]),
    )

    canon_logs = []
    for log in ["1_1_yosys_canonicalize.log"]:
        canon_logs.append(_declare_artifact(ctx, "logs", log))

    canon_output = _declare_artifact(ctx, "results", CANON_OUTPUT)

    commands = _generation_commands(canon_logs) + [ctx.executable._make.path + " $@"]

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile_yosys.path, canon_output.path],
        command = " && ".join(commands),
        env = _verilog_arguments(ctx.files.verilog_files) |
              yosys_environment(ctx) |
              config_environment(config),
        inputs = depset(
            [config] +
            ctx.files.verilog_files +
            ctx.files.extra_configs,
            transitive = [
                yosys_inputs(ctx),
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = [canon_output] + canon_logs,
    )

    synth_logs = []
    for log in ["1_1_yosys.log", "1_1_yosys_metrics.log", "1_1_yosys_hier_report.log"]:
        synth_logs.append(_declare_artifact(ctx, "logs", log))

    synth_outputs = []
    for output in SYNTH_OUTPUTS:
        synth_outputs.append(_declare_artifact(ctx, "results", output))

    synth_outputs.append(_declare_artifact(ctx, "objects", "lib/merged.lib"))

    commands = _generation_commands(synth_logs) + [ctx.executable._make.path + " $@"]
    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile_yosys.path,
            "--old-file",
            canon_output.path,
            "yosys-dependencies",
            "do-yosys-keep-hierarchy",
            "do-yosys",
            "do-synth",
        ],
        command = " && ".join(commands),
        env = _verilog_arguments([]) |
              yosys_environment(ctx) |
              config_environment(config),
        inputs = depset(
            [canon_output, config] +
            ctx.files.extra_configs,
            transitive = [
                yosys_inputs(ctx),
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = synth_outputs + synth_logs,
    )

    # Dummy action to make sure that the flow environment is available to
    # bazel run foo_synth without causing resynthesis when upgrading
    # ORFS where yosys did not change, saves many hours of synthesis
    dummy_output = _declare_artifact(ctx, "results", "dummy.txt")
    ctx.actions.run_shell(
        command = "touch " + dummy_output.path,
        env = flow_environment(ctx),
        inputs = depset(
            transitive = [
                flow_inputs(ctx),
            ],
        ),
        outputs = [dummy_output],
    )

    outputs = [canon_output] + synth_outputs + [dummy_output]

    config_short = _declare_artifact(ctx, "results", "1_synth.short.mk")
    ctx.actions.write(
        output = config_short,
        content = _config_content(
            arguments = _hack_away_prefix(
                arguments = _data_arguments(ctx) | _required_arguments(ctx) | _orfs_arguments(short = True, *[dep[OrfsInfo] for dep in ctx.attr.deps]) | _verilog_arguments(ctx.files.verilog_files, short = True),
                prefix = config_short.root.path,
            ),
            paths = [file.short_path for file in ctx.files.extra_configs],
        ),
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
            "${GENFILES}": " ".join(sorted([f.short_path for f in [config_short] + outputs + canon_logs + synth_logs])),
            "${CONFIG}": config_short.short_path,
            "${MAKE}": make.short_path,
        },
    )

    return [
        DefaultInfo(
            executable = exe,
            files = depset(outputs),
            runfiles = ctx.runfiles(
                [config_short, make] + outputs + canon_logs + synth_logs +
                ctx.files.extra_configs,
                transitive_files = depset(transitive = [
                    flow_inputs(ctx),
                    deps_inputs(ctx),
                    pdk_inputs(ctx),
                ]),
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
            files = depset([config_short] + ctx.files.verilog_files + ctx.files.extra_configs),
            runfiles = ctx.runfiles(transitive_files = depset(
                [config_short, make] +
                ctx.files.verilog_files + ctx.files.extra_configs,
                transitive = [
                    flow_inputs(ctx),
                    yosys_inputs(ctx),
                    data_inputs(ctx),
                    pdk_inputs(ctx),
                    deps_inputs(ctx),
                ],
            )),
        ),
        OrfsInfo(
            stage = "1_synth",
            config = config,
            variant = ctx.attr.variant,
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
    attrs = yosys_attrs() | synth_attrs(),
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
        content = _config_content(
            arguments = all_arguments,
            paths = [file.path for file in ctx.files.extra_configs],
        ),
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

    commands = _generation_commands(reports + logs) + _input_commands(_renames(ctx, ctx.files.src)) + [ctx.executable._make.path + " $@"]

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile.path] + steps,
        command = " && ".join(commands),
        env = flow_environment(ctx) | config_environment(config),
        inputs = depset(
            [config] +
            ctx.files.extra_configs,
            transitive = [
                flow_inputs(ctx),
                data_inputs(ctx),
                source_inputs(ctx),
                rename_inputs(ctx),
            ],
        ),
        outputs = results + objects + logs + reports,
    )

    config_short = _declare_artifact(ctx, "results", stage + ".short.mk")
    ctx.actions.write(
        output = config_short,
        content = _config_content(
            arguments = _hack_away_prefix(
                arguments = extra_arguments | _data_arguments(ctx) | _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo], short = True),
                prefix = config_short.root.path,
            ),
            paths = [file.short_path for file in ctx.files.extra_configs],
        ),
    )

    make = ctx.actions.declare_file("make_{}_{}_{}".format(ctx.attr.name, ctx.attr.variant, stage))
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = flow_substitutions(ctx) | {'"$@"': 'WORK_HOME="./{}" DESIGN_CONFIG="config.mk" "$@"'.format(ctx.label.package)},
    )

    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._deploy_template,
        output = exe,
        substitutions = {
            "${GENFILES}": " ".join(sorted([f.short_path for f in [config_short] + results + logs + reports])),
            "${CONFIG}": config_short.short_path,
            "${MAKE}": make.short_path,
        },
    )

    return [
        DefaultInfo(
            executable = exe,
            files = depset(forwards + results + reports),
            runfiles = ctx.runfiles(
                [config_short, make] +
                forwards + results + logs + reports + ctx.files.extra_configs,
                transitive_files = depset(transitive = [
                    flow_inputs(ctx),
                    ctx.attr.src[PdkInfo].files,
                    ctx.attr.src[OrfsInfo].additional_gds,
                    ctx.attr.src[OrfsInfo].additional_lefs,
                    ctx.attr.src[OrfsInfo].additional_libs,
                ]),
            ),
        ),
        OutputGroupInfo(
            logs = depset(logs),
            reports = depset(reports),
            **{f.basename: depset([f]) for f in [config] + results + objects + logs + reports}
        ),
        OrfsDepInfo(
            make = make,
            config = config_short,
            renames = _renames(ctx, ctx.files.src, short = True),
            files = depset([config_short] + ctx.files.src + ctx.files.data + ctx.files.extra_configs),
            runfiles = ctx.runfiles(transitive_files = depset(
                [config_short, make] +
                ctx.files.src + ctx.files.extra_configs,
                transitive = [
                    flow_inputs(ctx),
                    data_inputs(ctx),
                    source_inputs(ctx),
                    rename_inputs(ctx),
                ],
            )),
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
        ),
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
    ]

orfs_floorplan = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "2_floorplan",
        steps = ["do-floorplan"],
        log_names = [
            "2_1_floorplan.log",
            "2_2_floorplan_io.log",
            "2_3_floorplan_macro.log",
            "2_4_floorplan_tapcell.log",
            "2_5_floorplan_pdn.log",
            "2_1_floorplan.json",
            "2_2_floorplan_io.json",
            "2_3_floorplan_macro.json",
            "2_4_floorplan_tapcell.json",
            "2_5_floorplan_pdn.json",
        ],
        report_names = [
            "2_floorplan_final.rpt",
        ],
        result_names = [
            "2_floorplan.odb",
            "2_floorplan.sdc",
        ],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
    provides = flow_provides(),
    executable = True,
)

orfs_place = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "3_place",
        steps = ["do-place"],
        log_names = [
            "3_1_place_gp_skip_io.log",
            "3_2_place_iop.log",
            "3_3_place_gp.log",
            "3_4_place_resized.log",
            "3_5_place_dp.log",
            "3_1_place_gp_skip_io.json",
            "3_2_place_iop.json",
            "3_3_place_gp.json",
            "3_4_place_resized.json",
            "3_5_place_dp.json",
        ],
        report_names = [],
        result_names = [
            "3_place.odb",
            "3_place.sdc",
        ],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
    provides = flow_provides(),
    executable = True,
)

orfs_cts = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "4_cts",
        steps = ["do-cts"],
        log_names = [
            "4_1_cts.log",
            "4_1_cts.json",
        ],
        report_names = [
            "4_cts_final.rpt",
        ],
        result_names = [
            "4_cts.odb",
            "4_cts.sdc",
        ],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
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
            "5_1_grt.json",
            "5_2_route.json",
            "5_3_fillcell.json",
        ],
        report_names = [
            "5_global_route.rpt",
            "congestion.rpt",
        ],
        result_names = [
            "5_1_grt.odb",
            "5_1_grt.sdc",
        ],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
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
        log_names = [
            "5_2_route.log",
            "5_3_fillcell.log",
        ],
        report_names = [
            "5_route_drc.rpt",
        ],
        result_names = [
            "5_route.odb",
            "5_route.sdc",
        ],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
    provides = flow_provides(),
    executable = True,
)

orfs_final = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "6_final",
        steps = ["do-final"],
        object_names = [
            "klayout.lyt",
        ],
        log_names = [
            "6_1_merge.log",
            "6_report.log",
            "6_report.json",
            "6_1_fill.json",
        ],
        report_names = [
            "6_finish.rpt",
            "VDD.rpt",
            "VSS.rpt",
        ],
        result_names = [
            "6_final.gds",
            "6_final.odb",
            "6_final.sdc",
            "6_final.spef",
        ],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
    provides = flow_provides(),
    executable = True,
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
    attrs = openroad_attrs() | renamed_inputs_attr(),
    provides = flow_provides(),
    executable = True,
)

orfs_deps = rule(
    implementation = _deps_impl,
    attrs = flow_attrs() | openroad_only_attrs() | yosys_only_attrs(),
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

MOCK_STAGE_ARGUMENTS = {
    "synth": {"SYNTH_GUT": "1"},
}

# A stage argument is used in one or more stages. This is metainformation
# about the ORFS code that there is no known nice way for ORFS to
# provide.
BAZEL_VARIABLE_TO_STAGES = {
}

BAZEL_STAGE_TO_VARIABLES = {
}

def flatten(xs):
    """Flattens a nested list iteratively.

    Args:
        xs: A list that may contain other lists, maximum two levels
    Returns:
        A flattened list.
    """
    result = []
    for x in xs:
        if type(x) == "list":
            for y in x:
                if type(y) == "list":
                    fail("Nested lists are not supported")
                else:
                    result.append(y)
        else:
            result.append(x)
    return result

def set(iterable):
    """Creates a set-like collection from an iterable.

    Args:
        iterable: An iterable containing elements.
    Returns:
        A list with unique elements.
    """
    unique_dict = {}
    for item in iterable:
        unique_dict[item] = True
    return list(unique_dict.keys())

ORFS_VARIABLE_TO_STAGES = {
    k: v["stages"]
    for k, v in orfs_variable_metadata.items()
    if "stages" in v
}

ALL_STAGES = set(_union(*ORFS_VARIABLE_TO_STAGES.values()))

ORFS_STAGE_TO_VARIABLES = {
    stage: [
        variable
        for variable, has_stages in ORFS_VARIABLE_TO_STAGES.items()
        if stage in has_stages
    ]
    for stage in ALL_STAGES
}

STAGE_TO_VARIABLES = {
    stage: [
        variable
        for variable, stages in BAZEL_VARIABLE_TO_STAGES.items()
        if stage in stages
    ] + BAZEL_STAGE_TO_VARIABLES.get(stage, [])
    for stage in ALL_STAGES
}

VARIABLE_TO_STAGES = {
    variable: [
        stage
        for stage in ALL_STAGES
        if variable in STAGE_TO_VARIABLES[stage]
    ]
    for variable in _union(*STAGE_TO_VARIABLES.values())
}

[
    fail("Variable {} is defined the same in ORFS and Bazel {}".format(variable, stages))
    for variable, stages in VARIABLE_TO_STAGES.items()
    if variable in ORFS_VARIABLE_TO_STAGES and sorted(ORFS_VARIABLE_TO_STAGES[variable]) == sorted(stages)
]

ALL_STAGE_TO_VARIABLES = {stage: _union(STAGE_TO_VARIABLES.get(stage, []), ORFS_STAGE_TO_VARIABLES.get(stage, [])) for stage in ALL_STAGES}

ALL_VARIABLE_TO_STAGES = {
    variable: [
        stage
        for stage in ALL_STAGES
        if variable in ALL_STAGE_TO_VARIABLES[stage]
    ]
    for variable in _union(*ALL_STAGE_TO_VARIABLES.values())
}

def get_stage_args(stage, stage_arguments, arguments):
    """Returns the arguments for a specific stage.

    Args:
        stage: The stage name.
        stage_arguments: the dictionary of stages with each stage having a dictionary of arguments
        arguments: a dictionary of arguments automatically assigned to a stage
    Returns:
      A dictionary of arguments for the stage.
    """
    unsorted_dict = ({
                         arg: value
                         for arg, value in arguments.items()
                         if arg in ALL_STAGE_TO_VARIABLES[stage] or arg not in ALL_VARIABLE_TO_STAGES
                     } |
                     stage_arguments.get(stage, {}))
    return dict(sorted(unsorted_dict.items()))

def get_sources(stage, stage_sources, sources):
    """Returns the sources for a specific stage.

    Args:
        stage: The stage name.
        stage_sources: the dictionary of stages with each stage having a list of sources
        sources: a dictionary of variable names with a list of sources to a stage
    Returns:
      A list of sources for the stage.
    """
    return sorted(set(stage_sources.get(stage, []) +
                      flatten([
                          source_list
                          for variable, source_list in sources.items()
                          if variable in ALL_STAGE_TO_VARIABLES[stage] or variable not in ALL_VARIABLE_TO_STAGES
                      ])))

def _step_name(name, variant, stage):
    if variant:
        name += "_" + variant
    return name + "_" + stage

def _variant_name(variant, suffix):
    return "_".join([part for part in [variant, suffix] if part])

def _do_merge(a, b):
    return {k: a.get(k, {}) | b.get(k, {}) for k in (a | b).keys()}

def _merge(*args):
    x = {}
    for arg in args:
        x = _do_merge(x, arg)
    return x

def orfs_flow(
        name,
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
        visibility = ["//visibility:private"]):
    """
    Creates targets for running physical design flow with OpenROAD-flow-scripts.

    Args:
      name: name of the macro target
      verilog_files: list of verilog sources of the design
      macros: list of macros required to run physical design flow for this design
      sources: dictionary keyed by ORFS variables with lists of sources
      stage_sources: dictionary keyed by ORFS stages with lists of stage-specific sources
      stage_arguments: dictionary keyed by ORFS stages with lists of stage-specific arguments
      renamed_inputs: dictionary keyed by ORFS stages to rename inputs
      arguments: dictionary of additional arguments to the flow, automatically assigned to stages
      extra_configs: dictionary keyed by ORFS stages with list of additional configuration files
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      variant: name of the target variant, added right after the module name
      mock_area: floating point number, scale the die width/height by this amount, default no scaling
      visibility: the visibility attribute on a target controls whether the target can be used in other packages
      previous_stage: a dictionary with the input for a stage, default is previous stage. Useful when running experiments that share preceeding stages, like share synthesis for floorplan variants.
    """
    if variant == "base":
        variant = None
    abstract_variant = _variant_name(variant, "unmocked" if mock_area else None)
    _orfs_pass(
        name = name,
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
        visibility = visibility,
        previous_stage = previous_stage,
    )

    if not mock_area:
        return

    mock_variant = _variant_name(variant, "mocked")
    mock_area_name = _step_name(name, mock_variant, "generate_area")
    mock_configs = {
        "floorplan": [mock_area_name],
    }

    mock_stage_arguments = _merge(
        stage_arguments,
        MOCK_STAGE_ARGUMENTS,
    )

    _orfs_pass(
        name = name,
        verilog_files = verilog_files,
        macros = macros,
        sources = sources,
        stage_sources = stage_sources,
        stage_arguments = mock_stage_arguments,
        renamed_inputs = {},
        arguments = arguments,
        extra_configs = extra_configs | mock_configs,
        abstract_stage = "floorplan",
        variant = mock_variant,
        abstract_variant = None,
        visibility = visibility,
        previous_stage = {},
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
    )

    orfs_macro(
        name = _step_name(name, variant, ABSTRACT_IMPL.stage),
        lef = _step_name(name, mock_variant, ABSTRACT_IMPL.stage),
        lib = _step_name(name, abstract_variant, ABSTRACT_IMPL.stage),
        module_top = name,
    )

def _kwargs(stage, **kwargs):
    return {k: v[stage] for k, v in kwargs.items() if stage in v and v[stage]}

def _orfs_pass(
        name,
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
        visibility,
        previous_stage):
    steps = []
    for step in STAGE_IMPLS:
        steps.append(step)
        if step.stage == abstract_stage:
            break
    if abstract_stage != STAGE_IMPLS[0].stage:
        steps.append(ABSTRACT_IMPL)

    # Prune stages unused due to previous_stage
    if len(previous_stage) > 1:
        fail("Maximum previous stages is 1")
    start_stage = 0
    if len(previous_stage) > 0:
        start_stage = _map(lambda x: x.stage, STAGE_IMPLS).index(previous_stage.keys()[0])

    if start_stage < 1:
        synth_step = steps[0]
        synth_step.impl(
            name = _step_name(name, variant, synth_step.stage),
            arguments = get_stage_args(synth_step.stage, stage_arguments, arguments),
            data = get_sources(synth_step.stage, stage_sources, sources),
            deps = macros,
            extra_configs = extra_configs.get(synth_step.stage, []),
            module_top = name,
            variant = variant,
            verilog_files = verilog_files,
            visibility = visibility,
        )
        orfs_deps(
            name = "{}_deps".format(_step_name(name, variant, synth_step.stage)),
            src = _step_name(name, variant, synth_step.stage),
        )

    if start_stage == 0:
        # implemented stage 0 above, so skip stage 0 below
        start_stage = 1

    for step, prev in zip(steps[start_stage:], steps[start_stage - 1:]):
        stage_variant = abstract_variant if step.stage == ABSTRACT_IMPL.stage and abstract_variant else variant
        step_name = _step_name(name, stage_variant, step.stage)
        src = previous_stage.get(step.stage, _step_name(name, variant, prev.stage))
        step.impl(
            name = step_name,
            src = src,
            arguments = get_stage_args(step.stage, stage_arguments, arguments),
            data = get_sources(step.stage, stage_sources, sources),
            extra_configs = extra_configs.get(step.stage, []),
            variant = variant,
            visibility = visibility,
            **_kwargs(
                step.stage,
                renamed_inputs = renamed_inputs,
            )
        )
        orfs_deps(
            name = "{}_deps".format(step_name),
            src = step_name,
        )
