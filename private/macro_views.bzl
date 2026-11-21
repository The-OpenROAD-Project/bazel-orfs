"""Tiered views of a macro, so a parent need not wait for its blocks.

    load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_macro_tiers")

    orfs_macro_tiers(
        name = "Block_views",
        module_top = "Block",
        clocks = {"clock": "1000"},
        lef = ":Block_plan.lef",
        real = ":Block_generate_abstract",
        synth = ":Block_synth",
        verilog_files = ["top.sv"],
    )

    orfs_flow(
        name = "Top",
        macros = [":Block_views"],
        macro_view = "mock",
        ...
    )

A macro's view is the liberty its parent reads beside its LEF. Three tiers,
each waiting for less of the block than the next:

| tier  | the liberty                                   | waits for            |
| ----- | --------------------------------------------- | -------------------- |
| mock  | the block's ports, no arcs (`orfs_ports_macro`) | nothing              |
| synth | the timing model of the block's synthesis     | the block's synthesis |
| real  | the block's abstract                          | the block's flow     |

`mock` and `synth` take their LEF, the outline and pins, from `lef`: the
plan the parent's floorplan is made to, so moving between them swaps only
the liberty. `real` is the block's abstract as it is, LEF and all; the two
outlines agree when the block was built to the plan.

The mock is made from the parent's Verilog port list of the module, so a
change inside the block leaves its bytes, and every parent stage that reads
it, as they were.

The tier is the parent's: `orfs_flow(macro_view = ...)` picks it for every
`orfs_macro_tiers` among its macros (a plain macro is used as it is), and
`--@bazel-orfs//:macro_view=<tier>` overrides it for one run. A macro
without the tier (no `synth` for a block whose synthesis is not
partitioned) gives the highest tier below it. A
command-line flag leaves the output paths alone, so the other tiers'
results stay cached. `orfs_macro_view_report` compares a tier's boundary
timing with the real one, per port bus.
"""

load("//private:providers.bzl", "OrfsInfo", "TopInfo")
load("//private:rules.bzl", "orfs_macro")
load("//private:settings.bzl", "OrfsFlagInfo")
load("//private:timing_models.bzl", "orfs_timing_models")

MACRO_VIEWS = ["mock", "synth", "real"]

MacroViewsInfo = provider(
    "A macro's views, one per tier; a tier the macro lacks is None.",
    fields = ["module_top", "mock", "synth", "real"],
)

_PYTHON = {
    "_python": attr.label(
        default = Label("//pythonwrapper:python3"),
        executable = True,
        allow_files = True,
        cfg = "exec",
    ),
}

def _empty_orfs_info(lef, lib):
    return OrfsInfo(
        odb = None,
        sdc = None,
        gds = None,
        lef = lef,
        lib = lib,
        lib_pre_layout = None,
        additional_gds = depset([]),
        additional_lefs = depset([]),
        additional_libs = depset([]),
        additional_libs_pre_layout = depset([]),
        memories = depset([]),
        arguments = depset([]),
    )

def _ports_impl(ctx):
    lib = ctx.actions.declare_file("%s/%s.lib" % (ctx.label.name, ctx.attr.module_top))
    args = ctx.actions.args()
    args.add(ctx.file._script)
    args.add("--module", ctx.attr.module_top)
    args.add("--out", lib)
    args.add("--lef", ctx.file.lef)
    args.add_all(ctx.attr.clocks, before_each = "--clock")
    args.add_all(ctx.files.verilog_files)
    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = [args],
        inputs = [ctx.file._script, ctx.file.lef] + ctx.files.verilog_files,
        outputs = [lib],
        mnemonic = "PortsLib",
        progress_message = "Writing the ports-only liberty of %s" % ctx.attr.module_top,
    )
    files = [ctx.file.lef, lib]
    return [
        DefaultInfo(files = depset(files)),
        OutputGroupInfo(**{f.basename: depset([f]) for f in files}),
        _empty_orfs_info(ctx.file.lef, lib),
        TopInfo(module_top = ctx.attr.module_top),
    ]

orfs_ports_macro = rule(
    implementation = _ports_impl,
    doc = "A macro from its module's Verilog port list and a LEF: a liberty " +
          "cell with the ports as pins and no timing arcs " +
          "(tools/macro_views/ports_lib.py).",
    provides = [DefaultInfo, OutputGroupInfo, OrfsInfo, TopInfo],
    attrs = _PYTHON | {
        "clocks": attr.string_list(doc = "The clock ports."),
        "lef": attr.label(
            mandatory = True,
            allow_single_file = [".lef"],
            doc = "The macro's LEF; its SIZE is the cell's area.",
        ),
        "module_top": attr.string(mandatory = True, doc = "The module, and the cell's name."),
        "verilog_files": attr.label_list(
            mandatory = True,
            allow_files = True,
            doc = "Verilog that defines the module, with an ANSI header.",
        ),
        "_script": attr.label(
            default = Label("//tools/macro_views:ports_lib.py"),
            allow_single_file = True,
        ),
    },
)

def _views_impl(ctx):
    tops = [t[TopInfo].module_top for t in [ctx.attr.mock, ctx.attr.synth, ctx.attr.real] if t]
    if not tops:
        fail("%s: no view" % ctx.label)
    for top in tops:
        if top != tops[0]:
            fail("%s: the views are of different modules: %s" % (ctx.label, ", ".join(tops)))
    return [
        MacroViewsInfo(
            module_top = tops[0],
            mock = ctx.attr.mock,
            synth = ctx.attr.synth,
            real = ctx.attr.real,
        ),
        TopInfo(module_top = tops[0]),
    ]

orfs_macro_views = rule(
    implementation = _views_impl,
    doc = "A macro's views by tier; a parent's orfs_flow(macro_view) picks one.",
    provides = [MacroViewsInfo, TopInfo],
    attrs = {
        tier: attr.label(providers = [OrfsInfo, TopInfo], doc = "The %s tier's macro." % tier)
        for tier in MACRO_VIEWS
    },
)

def _view_impl(ctx):
    flag = ctx.attr._flag[OrfsFlagInfo].value
    view = flag or ctx.attr.view
    src = ctx.attr.src
    if MacroViewsInfo in src:
        tiers = MACRO_VIEWS[:MACRO_VIEWS.index(view) + 1]
        chosen = [getattr(src[MacroViewsInfo], t) for t in reversed(tiers)]
        chosen = [t for t in chosen if t]
        if not chosen:
            fail("%s has no %s view, nor one below it (%s)" % (
                src.label,
                view,
                "--@bazel-orfs//:macro_view" if flag else "macro_view",
            ))
        src = chosen[0]
    providers = [
        DefaultInfo(files = src[DefaultInfo].files),
        src[OrfsInfo],
        src[TopInfo],
    ]
    if OutputGroupInfo in src:
        providers.append(src[OutputGroupInfo])
    return providers

orfs_macro_view = rule(
    implementation = _view_impl,
    doc = "One of a macro's views, for a parent's stages: `view`, or the " +
          "--@bazel-orfs//:macro_view flag when set; a macro without that " +
          "tier gives the highest tier below it, so the parent never waits " +
          "for more than it asked. A macro without views is passed through.",
    provides = [DefaultInfo, OrfsInfo, TopInfo],
    attrs = {
        "src": attr.label(mandatory = True, providers = [TopInfo]),
        "view": attr.string(mandatory = True, values = MACRO_VIEWS),
        "_flag": attr.label(default = Label("//:macro_view")),
    },
)

def orfs_macro_tiers(
        name,
        module_top,
        lef,
        verilog_files,
        clocks,
        real = None,
        synth = None,
        tags = [],
        visibility = None):
    """A macro's three views: its ports, its synthesis timing model, its abstract.

    Declares `<name>_mock` (orfs_ports_macro), with `synth`
    `<name>_timing` (orfs_timing_models of the module) and `<name>_synth`
    (orfs_macro: `lef` and that model), and `<name>`, the orfs_macro_views
    a parent lists among its macros.

    Args:
        name: The views' name.
        module_top: The macro's module, its cell name in every view.
        lef: The macro's planned LEF, for the mock and synth views.
        verilog_files: Verilog with the module's ANSI header: the parent's
            sources, so the mock follows the ports the parent instantiates.
        clocks: {port: period}, the period in picoseconds: the mock's
            clock pins and the timing model's clock.
        real: The block's abstract, `<block>_generate_abstract`.
        synth: The block's synthesis, partitioned (SYNTH_KEEP_MODULES).
        tags: Tags of every target.
        visibility: Visibility of `<name>`.
    """
    orfs_ports_macro(
        name = name + "_mock",
        module_top = module_top,
        lef = lef,
        verilog_files = verilog_files,
        clocks = sorted(clocks.keys()),
        tags = tags,
    )
    synth_view = None
    if synth:
        orfs_timing_models(
            name = name + "_timing",
            synth = synth,
            modules = [module_top],
            clocks = clocks,
            tags = tags,
        )
        orfs_macro(
            name = name + "_synth",
            module_top = module_top,
            lef = lef,
            lib = name + "_timing",
            tags = tags,
        )
        synth_view = name + "_synth"
    orfs_macro_views(
        name = name,
        mock = name + "_mock",
        synth = synth_view,
        real = real,
        tags = tags,
        visibility = visibility,
    )

def _report_impl(ctx):
    views = ctx.attr.views[MacroViewsInfo]
    estimated = getattr(views, ctx.attr.estimated)
    if not estimated or not views.real:
        fail("%s: %s needs its %s and real views" % (ctx.label, ctx.attr.views.label, ctx.attr.estimated))
    out = ctx.actions.declare_file(ctx.label.name + ".md")
    args = ctx.actions.args()
    args.add(ctx.file._script)
    args.add("--cell", views.module_top)
    args.add("--period", ctx.attr.period)
    args.add("--estimated", estimated[OrfsInfo].lib)
    args.add("--real", views.real[OrfsInfo].lib)
    args.add("--out", out)
    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = [args],
        inputs = [ctx.file._script, estimated[OrfsInfo].lib, views.real[OrfsInfo].lib],
        outputs = [out],
        mnemonic = "MacroViewReport",
        progress_message = "Comparing %s's %s view with its real one" % (views.module_top, ctx.attr.estimated),
    )
    return [DefaultInfo(files = depset([out]))]

orfs_macro_view_report = rule(
    implementation = _report_impl,
    doc = "A tier's boundary timing against the real view's, per port bus: " +
          "worst arrival of each output bus and tightest required time of " +
          "each input bus, in ps (tools/macro_views/compare_libs.py).",
    attrs = _PYTHON | {
        "estimated": attr.string(default = "synth", values = ["mock", "synth"]),
        "period": attr.string(mandatory = True, doc = "The clock period, ps."),
        "views": attr.label(mandatory = True, providers = [MacroViewsInfo]),
        "_script": attr.label(
            default = Label("//tools/macro_views:compare_libs.py"),
            allow_single_file = True,
        ),
    },
)
