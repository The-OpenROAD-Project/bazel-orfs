"""Liberty timing models of a partitioned synthesis's kept modules.

    load("@bazel-orfs//:openroad.bzl", "orfs_timing_models")

    orfs_timing_models(
        name = "cpu_models",
        synth = ":cpu_synth",
        modules = ["Core", "Cache"],
        clocks = {"clock": "1000"},
    )

The synthesis is a partitioned one (SYNTH_KEEP_MODULES): each kept module is
a partition netlist. Each listed module's model is OpenSTA's
write_timing_model of its partition linked with every partition below it,
timed with one ideal clock and zero input and output delays: one cached
action per module, `<name>/<module>.lib`, the cell named after the module.
The kept-module tree read from the partitions is output group `tree`.

A model stands in for a subtree when timing the rest of the design. Paths
inside the modelled subtree stay out; paths across its boundary are timed
through the model's arcs, which differ from the netlist's in both
directions.
"""

load("//private:providers.bzl", "TopInfo")
load("//private:rules.bzl", "orfs_run")

TimingModelsInfo = provider(
    "Timing models of a partitioned synthesis's kept modules.",
    fields = ["tree", "libs", "models", "netlists", "clocks"],
)

def _clocks(clocks):
    return " ".join(["%s %s" % (k, v) for k, v in sorted(clocks.items())])

def _netlists(synth):
    return [
        f
        for f in synth[OutputGroupInfo].partitions.to_list()
        if f.basename.startswith("partition_") and f.extension == "v" and not f.basename.endswith("_slice.v")
    ]

def _libs_tar(target):
    for f in target[DefaultInfo].files.to_list():
        if f.basename == "libs.tar":
            return f
    fail("%s has no libs.tar" % target.label)

_TOOLS = {
    "_common": attr.label(default = Label("//tools/module_sta:common.tcl"), allow_single_file = True),
    "_opensta": attr.label(default = Label("@openroad//openroad/sta:opensta"), executable = True, cfg = "exec"),
    "_plan": attr.label(default = Label("//tools/sharded_sta:plan.py"), allow_single_file = True),
    "_python": attr.label(default = Label("//pythonwrapper:python3"), executable = True, allow_files = True, cfg = "exec"),
    "_run": attr.label(default = Label("//tools/sharded_sta:run.py"), allow_single_file = True),
    "_sta_sh": attr.label(default = Label("//tools/module_sta:sta.sh"), allow_single_file = True),
}

def _models_impl(ctx):
    netlists = _netlists(ctx.attr.synth)
    if not netlists:
        fail("%s has no partition netlists: orfs_timing_models needs a partitioned synthesis (SYNTH_KEEP_MODULES)" % ctx.attr.synth.label)
    libs = _libs_tar(ctx.attr.libs)
    tree = ctx.actions.declare_file(ctx.label.name + "/tree.json")
    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = [ctx.file._tree.path, ctx.attr.synth[TopInfo].module_top, tree.path] + [f.path for f in netlists],
        inputs = [ctx.file._tree] + netlists,
        outputs = [tree],
        mnemonic = "PartitionTree",
        progress_message = "Reading the kept-module tree of %s" % ctx.attr.synth[TopInfo].module_top,
    )
    models = {}
    stats = []
    for module in ctx.attr.modules:
        lib = ctx.actions.declare_file("%s/%s.lib" % (ctx.label.name, module))
        stat = ctx.actions.declare_file("%s/%s.json" % (ctx.label.name, module))
        ctx.actions.run(
            executable = ctx.executable._python,
            arguments = [
                ctx.file._run.path,
                "model",
                tree.path,
                module,
                ctx.file._sta_sh.path,
                ctx.executable._opensta.path,
                ctx.file._script.path,
                libs.path,
                lib.path,
                stat.path,
            ],
            inputs = [tree, libs, ctx.file._run, ctx.file._plan, ctx.file._sta_sh, ctx.file._script, ctx.file._common] + netlists,
            outputs = [lib, stat],
            env = {"PSTA_CLOCKS": _clocks(ctx.attr.clocks), "PSTA_THREADS": str(ctx.attr.threads)},
            tools = [ctx.executable._opensta],
            mnemonic = "TimingModel",
            progress_message = "Writing the timing model of %s" % module,
        )
        models[module] = lib
        stats.append(stat)
    return [
        DefaultInfo(files = depset(models.values())),
        OutputGroupInfo(stats = depset(stats), tree = depset([tree])),
        TimingModelsInfo(tree = tree, libs = libs, models = models, netlists = netlists, clocks = ctx.attr.clocks),
    ]

_timing_models = rule(
    implementation = _models_impl,
    attrs = _TOOLS | {
        "clocks": attr.string_dict(mandatory = True, doc = "{port: period}, one ideal clock, the period in picoseconds."),
        "libs": attr.label(mandatory = True, doc = "The liberty the design is timed with (libs.tar)."),
        "modules": attr.string_list(mandatory = True, doc = "The kept modules to model."),
        "synth": attr.label(mandatory = True, providers = [TopInfo], doc = "A partitioned synthesis."),
        "threads": attr.int(default = 1, doc = "The threads each model's timer uses."),
        "_script": attr.label(default = Label("//tools/sharded_sta:model.tcl"), allow_single_file = True),
        "_tree": attr.label(default = Label("//tools/sharded_sta:tree.py"), allow_single_file = True),
    },
)

def orfs_timing_models(name, synth, modules, clocks, threads = 1, tags = [], **kwargs):
    """A liberty timing model of each listed kept module, one cached action each.

    Args:
        name: Target name; `<name>/<module>.lib` per module, and the
            kept-module tree in output group `tree`.
        synth: A partitioned synthesis (SYNTH_KEEP_MODULES), e.g. `:cpu_synth`.
        modules: The kept modules to model, by name or by the name before
            a uniquified module's `$`; each model holds the module's
            partition and every partition below it.
        clocks: {port: period}, one ideal clock, the period in picoseconds.
        threads: The threads each model's timer uses; write_timing_model
            on a wide module is most of its time. Match it to the CPUs
            the action's exec_properties reserve.
        tags: Tags of the targets.
        **kwargs: Passed to the models target, e.g. `exec_properties`.
    """
    orfs_run(
        name = name + "_libs",
        src = synth,
        outs = [name + "_libs/libs.tar"],
        script = Label("//tools/module_sta:libs.tcl"),
        tags = tags,
        user_arguments = {"PSTA_LIBS_TAR": "$(location %s_libs/libs.tar)" % name},
    )
    _timing_models(
        name = name,
        synth = synth,
        libs = name + "_libs",
        modules = modules,
        clocks = clocks,
        threads = threads,
        tags = tags,
        **kwargs
    )
