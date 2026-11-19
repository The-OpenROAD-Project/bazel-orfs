"""A design's reg2reg timing in shards, each small enough for one machine.

    load("@bazel-orfs//:openroad.bzl", "orfs_sharded_sta", "orfs_timing_models")

    orfs_timing_models(
        name = "cpu_models",
        synth = ":cpu_synth",
        modules = ["Core", "Cache"],
        clocks = {"clock": "1000"},
    )
    orfs_sharded_sta(
        name = "cpu_sta",
        models = ":cpu_models",
        shards = {"core": ["Core"], "cache": ["Cache"]},
    )

`orfs_timing_models` (private/timing_models.bzl) writes a liberty model
of each subtree a shard does not hold as netlists.

`orfs_sharded_sta` gives each shard the instances of the kept modules it
lists and the instances below them that no other shard lists; what no
shard owns belongs to the glue shard (`glue`, an extra shard). A module
kept in two places can belong to two shards. A shard links the
partitions along the instances it owns, their ancestors' included (a
liberty cell cannot hold an instance), as netlists, every other subtree
as its root's timing model, and reports the register data pins of its
own instances: `<name>_<shard>`, one build action each. Every endpoint
is reported by exactly one shard; `<name>` merges them into
`<name>.json`, `<name>.md` and `<name>.ends`.

An endpoint is exact when no timing model reaches it, through the model's
outputs or through a net one of its inputs loads (the driver's delay and
slew then follow the model's pin capacitance): every path into it is timed
as in the netlist, and its slack is the flat netlist's. A timing model is
wrong in both directions at its boundary, so the merge
keeps the endpoints it reaches apart (`modelled`), out of the period
(`wns_exact`) and out of `<name>.ends`, which `ends.py compare` checks
against `orfs_flat_sta`. Put a module whose endpoints come out modelled
in the shard of the modules that drive it.

A shard's memory is its netlists' cells plus the models it reads: give
each shard a worker reservation with `shard_exec_properties`.

Limits: module_sta's (one ideal clock, nothing but create_clock applied).
"""

load("//private:timing_models.bzl", "TimingModelsInfo")

def _clocks(clocks):
    return " ".join(["%s %s" % (k, v) for k, v in sorted(clocks.items())])

_PYTHON = {
    "_python": attr.label(default = Label("//pythonwrapper:python3"), executable = True, allow_files = True, cfg = "exec"),
}

_TOOLS = _PYTHON | {
    "_common": attr.label(default = Label("//tools/module_sta:common.tcl"), allow_single_file = True),
    "_opensta": attr.label(default = Label("@openroad//openroad/sta:opensta"), executable = True, cfg = "exec"),
    "_plan": attr.label(default = Label("//tools/sharded_sta:plan.py"), allow_single_file = True),
    "_run": attr.label(default = Label("//tools/sharded_sta:run.py"), allow_single_file = True),
    "_sta_sh": attr.label(default = Label("//tools/module_sta:sta.sh"), allow_single_file = True),
}

ShardInfo = provider("One shard's outputs.", fields = ["name", "rows", "paths", "stats"])

def _shard_impl(ctx):
    info = ctx.attr.models[TimingModelsInfo]
    shards = ctx.actions.declare_file(ctx.label.name + "/shards.json")
    ctx.actions.write(shards, json.encode(json.decode(ctx.attr.shards)))
    rows = ctx.actions.declare_file(ctx.label.name + "/rows.txt")
    paths = ctx.actions.declare_file(ctx.label.name + "/paths.txt")
    stats = ctx.actions.declare_file(ctx.label.name + "/stats.json")
    libs = info.models.values()
    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = [
            ctx.file._run.path,
            "shard",
            info.tree.path,
            shards.path,
            ctx.attr.glue,
            ctx.attr.shard,
            ctx.file._sta_sh.path,
            ctx.executable._opensta.path,
            ctx.file._script.path,
            info.libs.path,
            rows.path,
            paths.path,
            stats.path,
            str(ctx.attr.path_count),
        ] + ["%s=%s" % (m, lib.path) for m, lib in sorted(info.models.items())],
        inputs = [info.tree, info.libs, shards, ctx.file._run, ctx.file._plan, ctx.file._sta_sh, ctx.file._script, ctx.file._common] + info.netlists + libs,
        outputs = [rows, paths, stats],
        env = {"PSTA_CLOCKS": _clocks(info.clocks), "PSTA_THREADS": str(ctx.attr.threads)},
        tools = [ctx.executable._opensta],
        mnemonic = "StaShard",
        progress_message = "Timing shard %s" % ctx.attr.shard,
    )
    return [
        DefaultInfo(files = depset([rows, paths, stats])),
        ShardInfo(name = ctx.attr.shard, rows = rows, paths = paths, stats = stats),
    ]

_sta_shard = rule(
    implementation = _shard_impl,
    attrs = _TOOLS | {
        "glue": attr.string(mandatory = True),
        "models": attr.label(mandatory = True, providers = [TimingModelsInfo]),
        "path_count": attr.int(mandatory = True),
        "shard": attr.string(mandatory = True),
        "shards": attr.string(mandatory = True, doc = "The shard spec, JSON."),
        "threads": attr.int(default = 1),
        "_script": attr.label(default = Label("//tools/sharded_sta:shard.tcl"), allow_single_file = True),
    },
)

def _check_spec(ctx):
    shards = json.decode(ctx.attr.shards)
    seen = {}
    for shard, modules in shards.items():
        if shard == ctx.attr.glue:
            fail("the glue shard %s is not listed in shards; it owns what no shard lists" % ctx.attr.glue)
        for m in modules:
            if m in seen:
                fail("%s is listed by both shard %s and shard %s" % (m, seen[m], shard))
            seen[m] = shard
    for shard in ctx.attr.exec_property_shards:
        if shard not in shards and shard != ctx.attr.glue:
            fail("shard_exec_properties names %s, which is not a shard" % shard)

def _merge_impl(ctx):
    _check_spec(ctx)
    out_json = ctx.actions.declare_file(ctx.label.name + ".json")
    out_md = ctx.actions.declare_file(ctx.label.name + ".md")
    out_ends = ctx.actions.declare_file(ctx.label.name + ".ends")
    args = [ctx.file._merge.path, out_json.path, out_md.path, out_ends.path, str(ctx.attr.path_count)]
    inputs = [ctx.file._merge]
    for s in ctx.attr.shard_targets:
        i = s[ShardInfo]
        args.append("%s=%s,%s,%s" % (i.name, i.rows.path, i.paths.path, i.stats.path))
        inputs += [i.rows, i.paths, i.stats]
    ctx.actions.run(
        executable = ctx.executable._python,
        arguments = args,
        inputs = inputs,
        outputs = [out_json, out_md, out_ends],
        mnemonic = "StaMerge",
        progress_message = "Merging the timing shards of %s" % ctx.label.name,
    )
    return [DefaultInfo(files = depset([out_json, out_md, out_ends]))]

_sta_merge = rule(
    implementation = _merge_impl,
    attrs = {
        "exec_property_shards": attr.string_list(),
        "glue": attr.string(mandatory = True),
        "path_count": attr.int(mandatory = True),
        "shards": attr.string(mandatory = True, doc = "The shard spec, JSON."),
        "shard_targets": attr.label_list(mandatory = True, providers = [ShardInfo]),
        "_merge": attr.label(default = Label("//tools/sharded_sta:merge.py"), allow_single_file = True),
    } | _PYTHON,
)

def orfs_sharded_sta(name, models, shards, glue = "glue", path_count = 20, shard_exec_properties = {}, threads = 1, tags = [], **kwargs):
    """A design's reg2reg timing in shards, merged into one report.

    Args:
        name: Target name: `<name>.json`, `<name>.md`, `<name>.ends`; each
            shard is `<name>_<shard>`.
        models: An orfs_timing_models of the design; it must model every
            subtree a shard reads as a model.
        shards: {shard: [kept module, ...]}, each by name or by the name
            before a uniquified module's `$` (every module of that name); a
            module is listed at most once.
        glue: The shard that owns every module no shard lists, the top's
            included; it lists nothing.
        path_count: The worst exact endpoints the report lists, with paths.
        shard_exec_properties: {shard: exec_properties}, e.g. a worker
            reservation sized to the shard.
        threads: The threads each shard's timer uses.
        tags: Tags of the targets.
        **kwargs: Passed to the merged report's target.
    """
    spec = json.encode(shards)
    targets = []
    for shard in [s for s in sorted(shards.keys()) if s != glue] + [glue]:
        _sta_shard(
            name = "%s_%s" % (name, shard),
            models = models,
            shards = spec,
            glue = glue,
            shard = shard,
            path_count = path_count,
            exec_properties = shard_exec_properties.get(shard, {}),
            threads = threads,
            tags = tags,
        )
        targets.append(":%s_%s" % (name, shard))
    _sta_merge(
        name = name,
        exec_property_shards = sorted(shard_exec_properties.keys()),
        glue = glue,
        shards = spec,
        shard_targets = targets,
        path_count = path_count,
        tags = tags,
        **kwargs
    )
