"""Rules for the building the OpenROAD-flow-scripts stages"""

load(
    "@config//:global_config.bzl",
    "CONFIG_MAKEFILE",
    "CONFIG_MAKEFILE_YOSYS",
    "CONFIG_OPENROAD",
    "CONFIG_PDK",
    "CONFIG_YOSYS",
    "CONFIG_YOSYS_ABC",
)
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
        "config",
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
        "drcs",
        "jsons",
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
            config = ctx.attr.config,
        ),
    ]

orfs_pdk = rule(
    implementation = _pdk_impl,
    attrs = {
        "srcs": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "config": attr.label(
            allow_single_file = ["config.mk"],
        ),
    },
)

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

def _odb_arguments(ctx, short = False):
    if ctx.attr.src[OrfsInfo].odb:
        odb = ctx.attr.src[OrfsInfo].odb
        return {"ODB_FILE": odb.short_path if short else odb.path}
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
        "OPENSTA_EXE": ctx.executable._opensta.path,
        "PYTHON_EXE": ctx.executable._python.path,
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

def _runfiles(attrs):
    return depset(
        _map(
            lambda tool: tool[DefaultInfo].files_to_run.executable,
            attrs,
        ),
        transitive = flatten(_map(
            lambda tool: [
                tool[DefaultInfo].default_runfiles.files,
                tool[DefaultInfo].default_runfiles.symlinks,
            ],
            attrs,
        )),
    )

def flow_inputs(ctx):
    return depset(
        ctx.files._ruby +
        ctx.files._ruby_dynamic +
        ctx.files._tcl +
        ctx.files._opengl +
        ctx.files._qt_plugins,
        transitive = [_runfiles([
            ctx.attr._klayout,
            ctx.attr._make,
            ctx.attr._openroad,
            ctx.attr._opensta,
            ctx.attr._python,
            ctx.attr._makefile,
        ] + ctx.attr.tools)],
    )

def yosys_inputs(ctx):
    return depset(
        ctx.files._tcl,
        transitive = [_runfiles([
            ctx.attr._abc,
            ctx.attr._yosys,
            ctx.attr._make,
            ctx.attr._makefile_yosys,
        ])],
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
            ctx.attr.src[LoggingInfo].jsons,
            ctx.attr.src[LoggingInfo].logs,
            ctx.attr.src[LoggingInfo].reports,
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
        "${KLAYOUT_PATH}": ctx.executable._klayout.path,
        "${LIBGL_DRIVERS_PATH}": commonpath(ctx.files._opengl),
        "${MAKEFILE_PATH}": ctx.file._makefile.path,
        "${MAKE_PATH}": ctx.executable._make.path,
        # OpenROAD uses //:openroad, //:opensta here and puts the binary in the pwd
        "${OPENROAD_PATH}": "./" + ctx.executable._openroad.short_path,
        "${OPENSTA_PATH}": "./" + ctx.executable._opensta.short_path,
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
        "tools": attr.label_list(
            doc = "List of tool binaries.",
            allow_files = True,
            cfg = "exec",
            default = [],
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
            default = CONFIG_MAKEFILE,
        ),
        "_python": attr.label(
            doc = "Python wrapper.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@bazel-orfs//pythonwrapper:python3"),
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
            default = CONFIG_OPENROAD,
        ),
        "_opensta": attr.label(
            doc = "OpenSTA binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:sta"),
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
    } | orfs_attrs()

def yosys_only_attrs():
    return {
        "_abc": attr.label(
            doc = "Abc binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_YOSYS_ABC,
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_YOSYS,
        ),
        "_makefile_yosys": attr.label(
            doc = "Top level makefile yosys.",
            allow_single_file = ["Makefile"],
            default = CONFIG_MAKEFILE_YOSYS,
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
            default = CONFIG_PDK,
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

def _platform_config(ctx):
    return (ctx.attr.pdk[PdkInfo] if hasattr(ctx.attr, "pdk") else ctx.attr.src[PdkInfo]).config.files.to_list()[0]

def _required_arguments(ctx):
    return {
        "PLATFORM": _platform(ctx),
        "PLATFORM_DIR": _platform_config(ctx).dirname,
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
    return {
        k: " ".join([w.removeprefix(prefix + "/") for w in v.split(" ")])
        for k, v in arguments.items()
    }

def _data_arguments(ctx):
    return {k: ctx.expand_location(v, ctx.attr.data) for k, v in ctx.attr.arguments.items()}

def _run_arguments(ctx):
    return {"RUN_SCRIPT": ctx.file.script.path}

def _environment_string(env):
    return " ".join(['{}="{}"'.format(*pair) for pair in env.items()])

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
        ],
        command = " ".join([
            ctx.executable._make.path,
            ctx.expand_location(ctx.attr.cmd, ctx.attr.data),
            ctx.expand_location(ctx.attr.extra_args, ctx.attr.data),
            "$@",
        ]),
        env =
            flow_environment(ctx) |
            yosys_environment(ctx) |
            config_environment(config) |
            _odb_arguments(ctx) |
            _data_arguments(ctx) |
            _run_arguments(ctx),
        inputs = depset(
            [config, ctx.file.script],
            transitive = [
                data_inputs(ctx),
                source_inputs(ctx),
            ],
        ),
        outputs = outs,
        tools = depset(transitive = [
            flow_inputs(ctx),
            yosys_inputs(ctx),
        ]),
    )

    make = ctx.actions.declare_file("make_{}_{}_run".format(ctx.attr.name, ctx.attr.variant))
    ctx.actions.expand_template(
        template = ctx.file._make_template,
        output = make,
        substitutions = flow_substitutions(ctx) | {'"$@"': _environment_string(
            _hack_away_prefix(
                arguments = _odb_arguments(ctx) |
                            _data_arguments(ctx) |
                            _run_arguments(ctx),
                prefix = config.root.path,
            ) |
            {
                "WORK_HOME": ctx.label.package,
                "DESIGN_CONFIG": "config.mk",
            },
        ) + ' "$@"'},
    )

    return [
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
        DefaultInfo(
            files = depset(outs),
        ),
        OutputGroupInfo(
            **{f.basename: depset([f]) for f in outs}
        ),
        OrfsDepInfo(
            make = make,
            config = ctx.attr.src[OrfsDepInfo].config,
            renames = [],
            files = depset([ctx.attr.src[OrfsDepInfo].config, ctx.file.script]),
            runfiles = ctx.runfiles(transitive_files = depset(
                [ctx.attr.src[OrfsDepInfo].config, make, ctx.file.script],
                transitive = [
                    flow_inputs(ctx),
                    data_inputs(ctx),
                    source_inputs(ctx),
                ],
            )),
        ),
    ]

orfs_run = rule(
    implementation = _run_impl,
    attrs = yosys_attrs() | openroad_attrs() | {
        "script": attr.label(
            mandatory = True,
            allow_single_file = ["tcl"],
        ),
        "outs": attr.output_list(
            mandatory = True,
            allow_empty = False,
        ),
        "cmd": attr.string(
            mandatory = False,
            default = "run",
        ),
        "extra_args": attr.string(
            mandatory = False,
            default = "",
        ),
    },
)

def _test_impl(ctx):
    config = ctx.attr.src[OrfsDepInfo].config

    test = ctx.actions.declare_file("make_{}_{}_test".format(ctx.attr.name, ctx.attr.variant))
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
            moreargs = _environment_string(
                _hack_away_prefix(
                    arguments = _odb_arguments(ctx) |
                                _data_arguments(ctx),
                    prefix = config.root.path,
                ) |
                {
                    "WORK_HOME": "./" + ctx.label.package,
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
            runfiles = ctx.runfiles(transitive_files = depset(
                [config, test],
                transitive = [
                    flow_inputs(ctx),
                    data_inputs(ctx),
                    source_inputs(ctx),
                ],
            )),
        ),
    ]

orfs_test = rule(
    implementation = _test_impl,
    attrs = yosys_attrs() | openroad_attrs() | {
        "cmd": attr.string(
            mandatory = False,
            default = "metadata-check",
        ),
    },
    test = True,
)

CANON_OUTPUT = "1_synth.rtlil"
SYNTH_OUTPUTS = ["1_synth.v", "1_synth.sdc", "mem.json"]
SYNTH_REPORTS = ["synth_stat.txt"]

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

    # SYNTH_NETLIST_FILES will not create an .rtlil file or reports, so we need
    # an empty placeholder in that case.
    commands = [ctx.executable._make.path + " $@"] + _generation_commands(canon_logs + [canon_output])

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile_yosys.path, "yosys-dependencies", "do-yosys-canonicalize"],
        command = " && ".join(commands),
        env = _verilog_arguments(ctx.files.verilog_files) |
              yosys_environment(ctx) |
              config_environment(config),
        inputs = depset(
            [config] +
            ctx.files.verilog_files +
            ctx.files.extra_configs,
            transitive = [
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = [canon_output] + canon_logs,
        tools = yosys_inputs(ctx),
    )

    synth_logs = []
    for log in ["1_1_yosys.log", "1_1_yosys_metrics.log", "1_1_yosys_hier_report.log"]:
        synth_logs.append(_declare_artifact(ctx, "logs", log))

    synth_outputs = []
    for output in SYNTH_OUTPUTS:
        synth_outputs.append(_declare_artifact(ctx, "results", output))

    synth_reports = []
    for report in SYNTH_REPORTS:
        synth_reports.append(_declare_artifact(ctx, "reports", report))

    # SYNTH_NETLIST_FILES will not create an .rtlil file or reports, so we need
    # an empty placeholder in that case.
    commands = [ctx.executable._make.path + " $@"] + _generation_commands(synth_logs + synth_outputs + synth_reports)
    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile_yosys.path,
            "yosys-dependencies",
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
                data_inputs(ctx),
                pdk_inputs(ctx),
                deps_inputs(ctx),
            ],
        ),
        outputs = synth_outputs + synth_logs + synth_reports,
        tools = yosys_inputs(ctx),
    )

    outputs = [canon_output] + synth_outputs

    config_short = _declare_artifact(ctx, "results", "1_synth.short.mk")
    ctx.actions.write(
        output = config_short,
        content = _config_content(
            arguments = _hack_away_prefix(
                arguments = _data_arguments(ctx) |
                            _required_arguments(ctx) |
                            _orfs_arguments(*[dep[OrfsInfo] for dep in ctx.attr.deps]) |
                            _verilog_arguments(ctx.files.verilog_files),
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
            reports = depset(synth_reports),
            drcs = depset([]),
            jsons = depset([]),
        ),
    ]

orfs_synth = rule(
    implementation = _yosys_impl,
    attrs = yosys_attrs() | synth_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsDepInfo, OrfsInfo, PdkInfo, TopInfo, LoggingInfo],
    executable = True,
)

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

    jsons = []
    for json in json_names:
        jsons.append(_declare_artifact(ctx, "logs", json))

    reports = []
    for report in report_names:
        reports.append(_declare_artifact(ctx, "reports", report))

    drcs = []
    for drc in drc_names:
        drcs.append(_declare_artifact(ctx, "reports", drc))

    forwards = [f for f in ctx.files.src if f.basename in forwarded_names]

    info = {}
    for file in forwards + results:
        info[file.extension] = file

    commands = _generation_commands(reports + logs + jsons + drcs) + _input_commands(_renames(ctx, ctx.files.src)) + [ctx.executable._make.path + " $@"]

    ctx.actions.run_shell(
        arguments = ["--file", ctx.file._makefile.path] + steps,
        command = " && ".join(commands),
        env = flow_environment(ctx) | config_environment(config),
        inputs = depset(
            [config] +
            ctx.files.extra_configs,
            transitive = [
                data_inputs(ctx),
                source_inputs(ctx),
                rename_inputs(ctx),
            ],
        ),
        outputs = results + objects + logs + reports + jsons + drcs,
        tools = flow_inputs(ctx),
    )

    config_short = _declare_artifact(ctx, "results", stage + ".short.mk")
    ctx.actions.write(
        output = config_short,
        content = _config_content(
            arguments = _hack_away_prefix(
                arguments = extra_arguments | _data_arguments(ctx) | _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo]),
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
            "${GENFILES}": " ".join(sorted([f.short_path for f in [config_short] + results + logs + reports + drcs + jsons])),
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
                forwards + results + logs + reports + ctx.files.extra_configs +
                drcs + jsons +
                # Some of these files might be read by open.tcl
                ctx.files.data,
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
            jsons = depset(jsons),
            drcs = depset(drcs),
            **{f.basename: depset([f]) for f in [config] + results + objects + logs + reports + jsons + drcs}
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
            drcs = depset(drcs, transitive = [ctx.attr.src[LoggingInfo].drcs]),
            jsons = depset(jsons, transitive = [ctx.attr.src[LoggingInfo].jsons]),
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
            "2_2_floorplan_macro.log",
            "2_3_floorplan_tapcell.log",
            "2_4_floorplan_pdn.log",
        ],
        json_names = [
            "2_1_floorplan.json",
            "2_2_floorplan_macro.json",
            "2_3_floorplan_tapcell.json",
            "2_4_floorplan_pdn.json",
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
        ],
        json_names = [
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
        ],
        json_names = [
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
        json_names = [
            "5_2_route.json",
            "5_3_fillcell.json",
        ],
        drc_names = [
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
        ],
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
            "6_final.gds",
            "6_final.odb",
            "6_final.sdc",
            "6_final.spef",
            "6_final.v",
        ],
    ),
    attrs = openroad_attrs() | renamed_inputs_attr(),
    provides = flow_provides(),
    executable = True,
)

orfs_generate_metadata = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "generate_metadata",
        steps = ["metadata-generate"],
        object_names = [
        ],
        log_names = [
            "metadata-generate.log",
        ],
        json_names = [
        ],
        report_names = [
            "metadata.json",
        ],
        result_names = [
        ],
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
            "{}_typ.lib".format(ctx.attr.src[TopInfo].module_top),
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

FINAL_STAGE_IMPL = struct(stage = "final", impl = orfs_final)

GENERATE_METADATA_STAGE_IMPL = struct(stage = "generate_metadata", impl = orfs_generate_metadata)
UPDATE_RULES_IMPL = struct(stage = "update_rules", impl = orfs_update_rules)

TEST_STAGE_IMPL = struct(stage = "test", impl = orfs_test)

STAGE_IMPLS = [
    struct(stage = "synth", impl = orfs_synth),
    struct(stage = "floorplan", impl = orfs_floorplan),
    struct(stage = "place", impl = orfs_place),
    struct(stage = "cts", impl = orfs_cts),
    struct(stage = "grt", impl = orfs_grt),
    struct(stage = "route", impl = orfs_route),
    FINAL_STAGE_IMPL,
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

# Stages that do not appear in variables.yaml must be added manually here
ALL_STAGES = set(_union(*ORFS_VARIABLE_TO_STAGES.values()) +
                 ["generate_metadata", "test", "update_rules"])

ORFS_STAGE_TO_VARIABLES = {
    stage: [
        variable
        for variable, has_stages in ORFS_VARIABLE_TO_STAGES.items()
        if stage in has_stages
    ]
    for stage in ALL_STAGES
}

ALL_STAGE_TO_VARIABLES = {stage: ORFS_STAGE_TO_VARIABLES.get(stage, []) for stage in ALL_STAGES}

ALL_VARIABLE_TO_STAGES = {
    variable: [
        stage
        for stage in ALL_STAGES
        if variable in ALL_STAGE_TO_VARIABLES[stage]
    ]
    for variable in _union(*ALL_STAGE_TO_VARIABLES.values())
}

def get_stage_args(stage, stage_arguments, arguments, sources):
    """Returns the arguments for a specific stage.

    Args:
        stage: The stage name.
        stage_arguments: the dictionary of stages with each stage having a dictionary of arguments
        arguments: a dictionary of arguments automatically assigned to a stage
        sources: a dictionary of variables and source files
    Returns:
      A dictionary of arguments for the stage.
    """
    unsorted_dict = (
        {
            arg: " ".join(_map(lambda v: "$(locations {})".format(v), value))
            for arg, value in sources.items()
            if arg in ALL_STAGE_TO_VARIABLES[stage] or arg not in ALL_VARIABLE_TO_STAGES
        } | {
            arg: value
            for arg, value in arguments.items()
            if arg in ALL_STAGE_TO_VARIABLES[stage] or arg not in ALL_VARIABLE_TO_STAGES
        } | stage_arguments.get(stage, {})
    )
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
        stage_data = {},
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
      stage_arguments: dictionary keyed by ORFS stages with lists of stage-specific arguments
      renamed_inputs: dictionary keyed by ORFS stages to rename inputs
      arguments: dictionary of additional arguments to the flow, automatically assigned to stages
      extra_configs: dictionary keyed by ORFS stages with list of additional configuration files
      abstract_stage: string with physical design flow stage name which controls the name of the files generated in _generate_abstract stage
      variant: name of the target variant, added right after the module name
      mock_area: floating point number, scale the die width/height by this amount, default no scaling
      previous_stage: a dictionary with the input for a stage, default is previous stage. Useful when running experiments that share preceeding stages, like share synthesis for floorplan variants.
      pdk: name of the PDK to use, default is asap7
      stage_data: dictionary keyed by ORFS stages with lists of stage-specific data files
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
            runfiles = ctx.runfiles(transitive_files = depset(
                [],
                transitive = [
                    depset(ctx.files.rules_json),
                    depset(ctx.files.logs),
                ],
            )),
        ),
    ]

orfs_update = rule(
    implementation = _update_rules_impl,
    attrs = {
        "rules_json": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
        "logs": attr.label_list(
            allow_files = True,
            providers = [LoggingInfo],
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
        stage_data,
        **kwargs):
    steps = []
    LEGAL_ABSTRACT_STAGES = ["place", "cts", "grt", "route", "final"]
    if abstract_stage != None and abstract_stage not in LEGAL_ABSTRACT_STAGES:
        fail("Abstract stage {abstract_stage} must be one of: {legal}".format(abstract_stage = abstract_stage, legal = ", ".join(LEGAL_ABSTRACT_STAGES)))
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
        start_stage = _map(lambda x: x.stage, STAGE_IMPLS).index(previous_stage.keys()[0])

    step_names = []
    if start_stage < 1:
        synth_step = steps[0]
        step_name = _step_name(name, variant, synth_step.stage)
        step_names.append(step_name)
        synth_step.impl(
            name = step_name,
            arguments = get_stage_args(synth_step.stage, stage_arguments, arguments, sources),
            data = get_sources(synth_step.stage, stage_sources, sources) +
                   stage_data.get(synth_step.stage, []),
            deps = macros,
            extra_configs = extra_configs.get(synth_step.stage, []),
            module_top = top,
            variant = variant,
            verilog_files = verilog_files,
            pdk = pdk,
            **kwargs
        )
        orfs_deps(
            name = "{}_deps".format(_step_name(name, variant, synth_step.stage)),
            src = _step_name(name, variant, synth_step.stage),
            **_add_manual(kwargs)
        )

    if start_stage == 0:
        # implemented stage 0 above, so skip stage 0 below
        start_stage = 1

    def do_step(step, prev, add_deps = True, more_kwargs = {}, data = []):
        stage_variant = abstract_variant if step.stage == ABSTRACT_IMPL.stage and abstract_variant else variant
        step_name = _step_name(name, stage_variant, step.stage)
        src = previous_stage.get(step.stage, _step_name(name, variant, prev.stage))
        step.impl(
            name = step_name,
            src = src,
            arguments = get_stage_args(step.stage, stage_arguments, arguments, sources),
            data = get_sources(step.stage, stage_sources, sources) +
                   stage_data.get(step.stage, []) + data,
            extra_configs = extra_configs.get(step.stage, []),
            variant = variant,
            **(kwargs | _kwargs(
                step.stage,
                renamed_inputs = renamed_inputs,
            ) | more_kwargs)
        )
        if add_deps:
            orfs_deps(
                name = "{}_deps".format(step_name),
                src = step_name,
                **_add_manual(kwargs | more_kwargs)
            )
        return step_name

    for step, prev in zip(steps[start_stage:], steps[start_stage - 1:]):
        step_names.append(do_step(step, prev))

    if FINAL_STAGE_IMPL in steps:
        do_step(
            GENERATE_METADATA_STAGE_IMPL,
            FINAL_STAGE_IMPL,
            data = [
                # Need 2_floorplan.sdc
                _step_name(name, variant, "floorplan"),
            ],
        )

        test_args = get_stage_args(TEST_STAGE_IMPL.stage, stage_arguments, arguments, sources)
        if "RULES_JSON" in test_args:
            do_step(
                TEST_STAGE_IMPL,
                GENERATE_METADATA_STAGE_IMPL,
                add_deps = False,
                more_kwargs = kwargs,
            )
            rules_name = do_step(
                UPDATE_RULES_IMPL,
                GENERATE_METADATA_STAGE_IMPL,
                more_kwargs = kwargs,
            )
            orfs_update(
                name = _step_name(name, variant, "update"),
                rules_json = sources["RULES_JSON"][0],
                logs = [rules_name],
                **kwargs
            )
