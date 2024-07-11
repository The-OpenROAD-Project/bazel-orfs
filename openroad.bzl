"""Rules for the building the OpenROAD-flow-scripts stages"""

OrfsInfo = provider(
    "The outputs of a OpenROAD-flow-scripts stage.",
    fields = [
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

def _run_impl(ctx):
    all_arguments = _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo])
    config = _config(ctx, "open", all_arguments)

    outs = []
    for k in dir(ctx.outputs):
        outs.extend(getattr(ctx.outputs, k))

    transitive_inputs = [
        ctx.attr.src[OrfsInfo].additional_gds,
        ctx.attr.src[OrfsInfo].additional_lefs,
        ctx.attr.src[OrfsInfo].additional_libs,
        ctx.attr.src[PdkInfo].files,
        ctx.attr._openroad[DefaultInfo].default_runfiles.files,
        ctx.attr._openroad[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._makefile[DefaultInfo].default_runfiles.files,
        ctx.attr._makefile[DefaultInfo].default_runfiles.symlinks,
    ]

    ctx.actions.run_shell(
        arguments = [
            "--file",
            ctx.file._makefile.path,
            "open_{}".format(ctx.attr.src[OrfsInfo].odb.basename),
        ],
        command = "make $@ < {}".format(ctx.file.script.path),
        env = {
            "HOME": "/".join([ctx.genfiles_dir.path, ctx.label.package]),
            "WORK_HOME": "/".join([ctx.genfiles_dir.path, ctx.label.package]),
            "DESIGN_CONFIG": config.path,
            "FLOW_HOME": ctx.file._makefile.dirname,
            "OPENROAD_EXE": ctx.executable._openroad.path,
            "ODB_FILE": ctx.attr.src[OrfsInfo].odb.path,
            "TCL_LIBRARY": common_prefix(ctx.files._tcl),
        },
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
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile"),
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

def common_prefix(files):
    prefix = ""
    for t in zip(*tuple([f.path.elems() for f in files])):
        for x in t:
            if x != t[0]:
                return prefix
        prefix += t[0]

    return prefix

def _expand_template(ctx, output, cmd):
    ctx.actions.expand_template(
        template = ctx.file._template,
        output = output,
        substitutions = {
            "{WORK_HOME}": "/".join([ctx.genfiles_dir.path, ctx.label.package]),
            "{YOSYS_PATH}": ctx.executable._yosys.path,
            "{OPENROAD_PATH}": ctx.executable._openroad.path,
            "{KLAYOUT_PATH}": ctx.executable._klayout.path,
            "{MAKEFILE_PATH}": ctx.file._makefile.path,
            "{FLOW_HOME}": ctx.file._makefile.dirname,
            "{TCL_LIBRARY}": common_prefix(ctx.files._tcl),
            "{LIBGL_DRIVERS_PATH}": common_prefix(ctx.files._opengl),
            "{QT_PLUGIN_PATH}": common_prefix(ctx.files._qt_plugins),
            "{GIO_MODULE_DIR}": common_prefix(ctx.files._gio_modules),
            "{CMD}": cmd,
        },
    )

def _script_impl(ctx):
    out = ctx.actions.declare_file(ctx.attr.name)
    _expand_template(ctx, out, "$@")
    return [DefaultInfo(
        files = depset([out]),
        runfiles = ctx.runfiles([]),
    )]

orfs_make = rule(
    implementation = _script_impl,
    attrs = {
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = Label("@docker_orfs//:makefile"),
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:yosys"),
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
        "_template": attr.label(
            default = ":make.tpl",
            allow_single_file = True,
        ),
    },
)

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
    }

def _orfs_arguments(*args):
    gds = depset([info.gds for info in args if info.gds], transitive = [info.additional_gds for info in args])
    lefs = depset([info.lef for info in args if info.lef], transitive = [info.additional_lefs for info in args])
    libs = depset([info.lib for info in args if info.lib], transitive = [info.additional_libs for info in args])

    args = {}
    if gds.to_list():
        args["ADDITIONAL_GDS"] = " ".join([file.path for file in gds.to_list()])
    if lefs.to_list():
        args["ADDITIONAL_LEFS"] = " ".join([file.path for file in lefs.to_list()])
    if libs.to_list():
        args["ADDITIONAL_LIBS"] = " ".join([file.path for file in libs.to_list()])
    return args

def _verilog_arguments(ctx):
    return {"VERILOG_FILES": " ".join([file.path for file in ctx.files.verilog_files])} if hasattr(ctx.attr, "verilog_files") else {}

def _block_arguments(ctx):
    return {"MACROS": " ".join([dep[TopInfo].module_top for dep in ctx.attr.deps])} if ctx.attr.deps else {}

def _config(ctx, stage, all_arguments):
    config = ctx.actions.declare_file("results/{}/{}/base/{}.mk".format(_platform(ctx), _module_top(ctx), stage))
    ctx.actions.write(
        output = config,
        content = "".join(["export {}={}\n".format(*pair) for pair in all_arguments.items()]),
    )
    return config

def _synth_impl(ctx):
    all_arguments = {k: ctx.expand_location(v, ctx.attr.data) for k, v in ctx.attr.arguments.items()} | _required_arguments(ctx) | _orfs_arguments(*[dep[OrfsInfo] for dep in ctx.attr.deps]) | _verilog_arguments(ctx) | _block_arguments(ctx)
    config = _config(ctx, "1_synth", all_arguments)

    out = ctx.actions.declare_file("results/{}/{}/base/1_synth.v".format(_platform(ctx), _module_top(ctx)))
    sdc = ctx.actions.declare_file("results/{}/{}/base/1_synth.sdc".format(_platform(ctx), _module_top(ctx)))

    transitive_inputs = [
        ctx.attr.pdk[PdkInfo].files,
        ctx.attr._abc[DefaultInfo].default_runfiles.files,
        ctx.attr._abc[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._yosys[DefaultInfo].default_runfiles.files,
        ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
        ctx.attr._makefile[DefaultInfo].default_runfiles.files,
        ctx.attr._makefile[DefaultInfo].default_runfiles.symlinks,
        depset([dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds]),
        depset([dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef]),
        depset([dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib]),
    ]

    transitive_runfiles = []
    for datum in ctx.attr.data:
        transitive_runfiles.append(datum[DefaultInfo].default_runfiles.files)
        transitive_runfiles.append(datum[DefaultInfo].default_runfiles.symlinks)

    ctx.actions.run(
        arguments = ["--file", ctx.file._makefile.path, "synth"],
        executable = "make",
        env = {
            "HOME": "/".join([ctx.genfiles_dir.path, ctx.label.package]),
            "WORK_HOME": "/".join([ctx.genfiles_dir.path, ctx.label.package]),
            "FLOW_HOME": ctx.file._makefile.dirname,
            "DESIGN_CONFIG": config.path,
            "ABC": ctx.executable._abc.path,
            "YOSYS_CMD": ctx.executable._yosys.path,
        },
        inputs = depset(
            ctx.files.verilog_files +
            ctx.files.data +
            [
                config,
                ctx.executable._abc,
                ctx.executable._yosys,
                ctx.file._makefile,
            ],
            transitive = transitive_inputs,
        ),
        outputs = [out, sdc],
    )

    return [
        DefaultInfo(
            files = depset([config, out, sdc]),
            runfiles = ctx.runfiles(transitive_files = depset(transitive = transitive_runfiles)),
        ),
        OutputGroupInfo(
            logs = depset([]),
            reports = depset([]),
            **{f.basename: depset([f]) for f in [config, out, sdc]}
        ),
        OrfsInfo(
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
    ]

orfs_synth = rule(
    implementation = _synth_impl,
    attrs = yosys_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = False,
)

def _make_impl(ctx, stage, steps, result_names = [], object_names = [], log_names = [], report_names = [], extra_arguments = {}):
    all_arguments = {k: ctx.expand_location(v, ctx.attr.data) for k, v in ctx.attr.arguments.items()} | extra_arguments | _required_arguments(ctx) | _orfs_arguments(ctx.attr.src[OrfsInfo])
    config = _config(ctx, stage, all_arguments)

    results = []
    odb = None
    gds = None
    lef = None
    lib = None
    for result in result_names:
        file = ctx.actions.declare_file("results/{}/{}/base/{}".format(_platform(ctx), _module_top(ctx), result))
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
        objects.append(ctx.actions.declare_file("objects/{}/{}/base/{}".format(_platform(ctx), _module_top(ctx), object)))

    logs = []
    for log in log_names:
        logs.append(ctx.actions.declare_file("logs/{}/{}/base/{}".format(_platform(ctx), _module_top(ctx), log)))

    reports = []
    for report in report_names:
        reports.append(ctx.actions.declare_file("reports/{}/{}/base/{}".format(_platform(ctx), _module_top(ctx), report)))

    transitive_inputs = [
        ctx.attr.src[DefaultInfo].default_runfiles.files,
        ctx.attr.src[DefaultInfo].default_runfiles.symlinks,
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
    ]

    transitive_runfiles = []
    for datum in ctx.attr.data:
        transitive_runfiles.append(datum[DefaultInfo].default_runfiles.files)
        transitive_runfiles.append(datum[DefaultInfo].default_runfiles.symlinks)

    ctx.actions.run(
        arguments = ["--file", ctx.file._makefile.path] + steps,
        executable = "make",
        env = {
            "HOME": "/".join([ctx.genfiles_dir.path, ctx.label.package]),
            "WORK_HOME": "/".join([ctx.genfiles_dir.path, ctx.label.package]),
            "DESIGN_CONFIG": config.path,
            "FLOW_HOME": ctx.file._makefile.dirname,
            "OPENROAD_EXE": ctx.executable._openroad.path,
            "KLAYOUT_CMD": ctx.executable._klayout.path,
            "TCL_LIBRARY": common_prefix(ctx.files._tcl),
        },
        inputs = depset(
            ctx.files.src +
            ctx.files.data +
            ctx.files._tcl +
            [config, ctx.executable._openroad, ctx.executable._klayout, ctx.file._makefile],
            transitive = transitive_inputs + transitive_runfiles,
        ),
        outputs = results + objects + logs + reports,
    )

    return [
        DefaultInfo(
            files = depset([config] + results),
            runfiles = ctx.runfiles(transitive_files = depset(transitive = transitive_runfiles)),
        ),
        OutputGroupInfo(
            logs = depset(logs),
            reports = depset(reports),
            **{f.basename: depset([f]) for f in [config] + results + objects + logs + reports}
        ),
        OrfsInfo(
            odb = odb,
            gds = gds,
            lef = lef,
            lib = lib,
            additional_gds = ctx.attr.src[OrfsInfo].additional_gds,
            additional_lefs = ctx.attr.src[OrfsInfo].additional_lefs,
            additional_libs = ctx.attr.src[OrfsInfo].additional_libs,
        ),
        ctx.attr.src[PdkInfo],
        ctx.attr.src[TopInfo],
    ]

orfs_floorplan = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "2_floorplan",
        steps = ["do-floorplan"],
        result_names = [
            "2_floorplan.odb",
            "2_floorplan.sdc",
        ],
        object_names = [
            "copyright.txt",
        ],
        log_names = [
            "2_1_floorplan.log",
        ],
        report_names = [
            "2_floorplan_final.rpt",
        ],
    ),
    attrs = openroad_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = False,
)

orfs_place = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "3_place",
        steps = ["do-place"],
        result_names = [
            "3_place.odb",
            "3_place.sdc",
        ],
        log_names = [],
        report_names = [],
    ),
    attrs = openroad_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = False,
)

orfs_cts = rule(
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
    attrs = openroad_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = False,
)

orfs_route = rule(
    implementation = lambda ctx: _make_impl(
        ctx = ctx,
        stage = "5_route",
        steps = ["do-route"],
        result_names = [
            "5_route.odb",
            "5_route.sdc",
        ],
        log_names = [
            "5_1_grt.log",
            "5_2_fillcell.log",
            "5_3_route.log",
        ],
        report_names = [
            "5_route_drc.rpt",
            "5_global_route.rpt",
            "congestion.rpt",
        ],
    ),
    attrs = openroad_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = False,
)

orfs_final = rule(
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
    attrs = openroad_attrs(),
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = False,
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
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, PdkInfo, TopInfo],
    executable = False,
)

STAGE_IMPLS = [
    struct(stage = "synth", impl = orfs_synth),
    struct(stage = "floorplan", impl = orfs_floorplan),
    struct(stage = "place", impl = orfs_place),
    struct(stage = "cts", impl = orfs_cts),
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
      visibility: the visibility attribute on a target controls whether the target can be used in other packages
    """
    steps = []
    for step in STAGE_IMPLS:
        steps.append(step)
        if step.stage == abstract_stage:
            break
    steps.append(ABSTRACT_IMPL)

    synth_step = steps[0]
    synth_step.impl(
        name = "{}_{}".format(name, synth_step.stage),
        arguments = stage_args.get(synth_step.stage, {}),
        data = stage_sources.get(synth_step.stage, []),
        deps = macros,
        module_top = name,
        verilog_files = verilog_files,
        visibility = visibility,
    )

    for step, prev in zip(steps[1:], steps):
        step.impl(
            name = "{}_{}".format(name, step.stage),
            src = "{}_{}".format(name, prev.stage),
            arguments = stage_args.get(step.stage, {}),
            data = stage_sources.get(step.stage, []),
            visibility = visibility,
        )
