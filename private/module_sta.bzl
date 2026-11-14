"""Module-in-context timing: one module of a synthesised design, timed with the rest of the design around it, for an AI loop iterating on that module.

    load("@bazel-orfs//:openroad.bzl", "orfs_module_context", "orfs_module_sta_base")

    orfs_module_sta_base(name = "cpu_hier", synth = ":cpu_synth")
    orfs_module_context(
        name = "alu_ctx",
        base = ":cpu_hier",
        module = "core/alu",
        clocks = {"clock": "1000"},
    )

    bazelisk run //my:alu_ctx_iterate -- Alu_new alu_new.v

`orfs_module_sta_base` writes the whole design as a hierarchical database
(ORFS's load_design with OPENROAD_HIERARCHICAL=1) and the liberty it is
timed with. `orfs_module_context` cuts module M's context from it, once:
the cells of the rest of the design on every reg2reg path that crosses
M's ports, real cells only, and nothing else (tools/module_sta/
context_db.tcl). Each iteration then loads that context with read_db
-hier, reads the new M with read_verilog, links it (link_hier_module,
carried OpenROAD patch 0222) and swaps it in (replace_hier_module, with
patch 0223 for a module with children of its own), and times: M's
endpoints and those of the registers M's outputs reach, each as the whole
design times it. After synthesis the clocks are ideal and there are no
wires, so the slacks are the flat netlist's; `orfs_flat_sta` times the
whole netlist flat to check that.

`<name>_iterate` runs an iteration from a dirty lane: the new module's
name, then its netlist and the netlists of the modules it instantiates.
It writes `<name>.ends` and `<name>.json` to the working directory.
`orfs_module_iteration` is the same as a build action, for tests and
A/B (`orfs_timing_ab`).

Limits: one clock, ideal; nothing but create_clock is applied (no
exceptions, no IO delays), so every path timed starts at a register.
"""

load("//private:providers.bzl", "TopInfo")
load("//private:rules.bzl", "orfs_run")

ModuleContextInfo = provider(
    "A module's timing context.",
    fields = ["odb", "exact", "libs", "module", "clocks"],
)

def _clocks(clocks):
    return " ".join(["%s %s" % (k, v) for k, v in sorted(clocks.items())])

def _pick(target, basename):
    for f in target[DefaultInfo].files.to_list():
        if f.basename == basename:
            return f
    fail("%s has no %s" % (target.label, basename))

_TOOLS = {
    "_common": attr.label(default = Label("//tools/module_sta:common.tcl"), allow_single_file = True),
    "_sta_sh": attr.label(default = Label("//tools/module_sta:sta.sh"), allow_single_file = True),
}

_OPENROAD = {
    "_openroad": attr.label(default = Label("@openroad//:openroad"), executable = True, cfg = "exec"),
}

def orfs_module_sta_base(name, synth, tags = [], **kwargs):
    """The whole design as a hierarchical database, and its liberty.

    Args:
        name: Target name; `<name>/base.odb` and `<name>/libs.tar`.
        synth: The synthesis stage, e.g. `:cpu_synth`.
        tags: Tags of the target.
        **kwargs: Passed to the target, e.g. `visibility`.
    """
    orfs_run(
        name = name,
        src = synth,
        outs = [name + "/base.odb", name + "/libs.tar"],
        arguments = {"OPENROAD_HIERARCHICAL": "1"},
        script = Label("//tools/module_sta:base.tcl"),
        tags = tags,
        user_arguments = {
            "PSTA_BASE_DB": "$(location %s/base.odb)" % name,
            "PSTA_LIBS_TAR": "$(location %s/libs.tar)" % name,
        },
        **kwargs
    )

def _context_impl(ctx):
    base = _pick(ctx.attr.base, "base.odb")
    libs = _pick(ctx.attr.base, "libs.tar")
    odb = ctx.actions.declare_file(ctx.label.name + ".odb")
    exact = ctx.actions.declare_file(ctx.label.name + "_exact.txt")
    stats = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.run(
        executable = ctx.file._sta_sh,
        arguments = [ctx.executable._openroad.path, ctx.file._script.path, libs.path],
        inputs = [base, libs, ctx.file._script, ctx.file._common],
        outputs = [odb, exact, stats],
        env = {
            "PSTA_BASE_DB": base.path,
            "PSTA_CLOCKS": _clocks(ctx.attr.clocks),
            "PSTA_CONTEXT_DB": odb.path,
            "PSTA_EXACT": exact.path,
            "PSTA_M": ctx.attr.module,
            "PSTA_STATS": stats.path,
        },
        tools = [ctx.executable._openroad],
        mnemonic = "ModuleContext",
        progress_message = "Cutting the timing context of %s" % ctx.attr.module,
    )
    return [
        DefaultInfo(files = depset([odb, exact, stats])),
        ModuleContextInfo(odb = odb, exact = exact, libs = libs, module = ctx.attr.module, clocks = ctx.attr.clocks),
    ]

_module_context = rule(
    implementation = _context_impl,
    attrs = _TOOLS | _OPENROAD | {
        "base": attr.label(mandatory = True, doc = "An orfs_module_sta_base."),
        "clocks": attr.string_dict(mandatory = True, doc = "{port: period}, one ideal clock, the period in picoseconds."),
        "module": attr.string(mandatory = True, doc = "M's instance path, e.g. `core/alu`."),
        "_script": attr.label(default = Label("//tools/module_sta:context_db.tcl"), allow_single_file = True),
    },
)

def _runner_impl(ctx):
    info = ctx.attr.context[ModuleContextInfo]
    script = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.expand_template(
        template = ctx.file._template,
        output = script,
        substitutions = {
            "%%CLOCKS%%": _clocks(info.clocks),
            "%%CONTEXT%%": info.odb.short_path,
            "%%EXACT%%": info.exact.short_path,
            "%%LIBS%%": info.libs.short_path,
            "%%MODULE%%": info.module,
            "%%NAME%%": ctx.attr.context.label.name,
            "%%OPENROAD%%": ctx.executable._openroad.short_path,
            "%%SCRIPT%%": ctx.file._script.short_path,
            "%%STA_SH%%": ctx.file._sta_sh.short_path,
        },
        is_executable = True,
    )
    runfiles = ctx.runfiles(files = [info.odb, info.exact, info.libs, ctx.file._script, ctx.file._common, ctx.file._sta_sh])
    runfiles = runfiles.merge(ctx.attr._openroad[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = script, runfiles = runfiles)]

_module_runner = rule(
    implementation = _runner_impl,
    executable = True,
    attrs = _TOOLS | {
        "context": attr.label(mandatory = True, providers = [ModuleContextInfo]),
        "_openroad": attr.label(default = Label("@openroad//:openroad"), executable = True, cfg = "target"),
        "_script": attr.label(default = Label("//tools/module_sta:iterate.tcl"), allow_single_file = True),
        "_template": attr.label(default = Label("//tools/module_sta:iterate.sh.tpl"), allow_single_file = True),
    },
)

def orfs_module_context(name, base, module, clocks, tags = [], **kwargs):
    """Module `module`'s timing context, and `<name>_iterate` to time a new one in it.

    Args:
        name: Target name; `<name>.odb`, `<name>_exact.txt`, `<name>.json`.
        base: An orfs_module_sta_base of the design.
        module: M's instance path, e.g. `core/alu`.
        clocks: {port: period}, one ideal clock, the period in picoseconds.
        tags: Tags of the targets.
        **kwargs: Passed to the targets, e.g. `visibility`.
    """
    if len(clocks) != 1:
        fail("orfs_module_context: one clock, got %s" % clocks)
    _module_context(name = name, base = base, module = module, clocks = clocks, tags = tags, **kwargs)
    _module_runner(name = name + "_iterate", context = ":" + name, tags = tags, **kwargs)

def _iteration_impl(ctx):
    info = ctx.attr.context[ModuleContextInfo]
    ends = ctx.actions.declare_file(ctx.label.name + ".ends")
    stats = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.run(
        executable = ctx.file._sta_sh,
        arguments = [ctx.executable._openroad.path, ctx.file._script.path, info.libs.path],
        inputs = [info.odb, info.exact, info.libs, ctx.file._script, ctx.file._common] + ctx.files.netlists,
        outputs = [ends, stats],
        env = {
            "PSTA_CLOCKS": _clocks(info.clocks),
            "PSTA_CONTEXT_DB": info.odb.path,
            "PSTA_ENDPOINTS": ends.path,
            "PSTA_EXACT": info.exact.path,
            "PSTA_M": info.module,
            "PSTA_NEW": " ".join([f.path for f in ctx.files.netlists]),
            "PSTA_NEW_MODULE": ctx.attr.new_module,
            "PSTA_STATS": stats.path,
        },
        tools = [ctx.executable._openroad],
        mnemonic = "ModuleIteration",
        progress_message = "Timing %s in the context of %s" % (ctx.attr.new_module, info.module),
    )
    return [DefaultInfo(files = depset([ends])), OutputGroupInfo(stats = depset([stats]))]

orfs_module_iteration = rule(
    implementation = _iteration_impl,
    doc = "One iteration as a build action: a new module timed in an orfs_module_context, `<name>.ends` (output group `stats`: `<name>.json`).",
    attrs = _TOOLS | _OPENROAD | {
        "context": attr.label(mandatory = True, providers = [ModuleContextInfo], doc = "An orfs_module_context."),
        "netlists": attr.label_list(allow_files = True, mandatory = True, doc = "The new module's netlist and those of the modules it instantiates."),
        "new_module": attr.string(mandatory = True, doc = "The new module's name, other than the one it replaces."),
        "_script": attr.label(default = Label("//tools/module_sta:iterate.tcl"), allow_single_file = True),
    },
)

def _flat_impl(ctx):
    netlist = getattr(ctx.attr.synth[OutputGroupInfo], "1_2_yosys.v").to_list()[0]
    libs = _pick(ctx.attr.base, "libs.tar")
    ends = ctx.actions.declare_file(ctx.label.name + ".ends")
    stats = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.run(
        executable = ctx.file._sta_sh,
        arguments = [ctx.executable._opensta.path, ctx.file._script.path, libs.path],
        inputs = [netlist, libs, ctx.file._script, ctx.file._common],
        outputs = [ends, stats],
        env = {
            "PSTA_CLOCKS": _clocks(ctx.attr.clocks),
            "PSTA_ENDPOINTS": ends.path,
            "PSTA_NETLIST": netlist.path,
            "PSTA_STATS": stats.path,
            "PSTA_TOP": ctx.attr.synth[TopInfo].module_top,
        },
        tools = [ctx.executable._opensta],
        mnemonic = "FlatSta",
        progress_message = "Timing %s flat" % ctx.attr.synth[TopInfo].module_top,
    )
    return [DefaultInfo(files = depset([ends])), OutputGroupInfo(stats = depset([stats]))]

orfs_flat_sta = rule(
    implementation = _flat_impl,
    doc = "The whole synthesised netlist timed flat in one session, the reference: `<name>.ends` (output group `stats`: `<name>.json`).",
    attrs = _TOOLS | {
        "base": attr.label(mandatory = True, doc = "An orfs_module_sta_base, for its liberty."),
        "clocks": attr.string_dict(mandatory = True, doc = "{port: period}, one ideal clock, the period in picoseconds."),
        "synth": attr.label(mandatory = True, providers = [TopInfo], doc = "The synthesis stage."),
        "_opensta": attr.label(default = Label("@openroad//src/sta:opensta"), executable = True, cfg = "exec"),
        "_script": attr.label(default = Label("//tools/module_sta:flat.tcl"), allow_single_file = True),
    },
)

def _timing_ab_impl(ctx):
    a = ctx.attr.a[DefaultInfo].files.to_list()
    b = ctx.attr.b[DefaultInfo].files.to_list()
    if len(a) != 1 or len(b) != 1:
        fail("%s: a and b each give one .ends file" % ctx.label)
    out = ctx.actions.declare_file(ctx.label.name + ".txt")
    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = [ctx.file._ab.path, a[0].path, b[0].path, out.path],
        inputs = [a[0], b[0], ctx.file._ab, ctx.file._ends],
        outputs = [out],
        mnemonic = "TimingAb",
        progress_message = "Timing A/B %s" % ctx.label,
    )
    return [DefaultInfo(files = depset([out]))]

orfs_timing_ab = rule(
    implementation = _timing_ab_impl,
    doc = "What an edit did to reg2reg timing: two targets' `.ends` compared, `<name>.txt`.",
    attrs = {
        "a": attr.label(mandatory = True, doc = "Before the edit: an orfs_module_iteration or orfs_flat_sta."),
        "b": attr.label(mandatory = True, doc = "After it."),
        "_ab": attr.label(default = Label("//tools/module_sta:ab.py"), allow_single_file = True),
        "_ends": attr.label(default = Label("//tools/module_sta:ends.py"), allow_single_file = True),
        "_python": attr.label(default = Label("//pythonwrapper:python3"), executable = True, allow_files = True, cfg = "exec"),
    },
)
