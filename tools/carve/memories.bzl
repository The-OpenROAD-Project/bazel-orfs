"""carve_memories: the memories inside the macros a top level dissolves,
as one LEF and one Liberty file (merge_memories.py)."""

load("//private:providers.bzl", "OrfsInfo")

def _carve_memories_impl(ctx):
    trees = depset(transitive = [
        getattr(src[OrfsInfo], "memories", depset())
        for src in ctx.attr.srcs
    ])
    args = ctx.actions.args()
    args.add(ctx.outputs.lef)
    args.add(ctx.outputs.lib)
    args.add_all(trees)
    ctx.actions.run(
        executable = ctx.executable._merge,
        arguments = [args],
        inputs = trees,
        outputs = [ctx.outputs.lef, ctx.outputs.lib],
        mnemonic = "CarveMemories",
        progress_message = "Merging the memories of %{label}",
    )
    return [DefaultInfo(files = depset([ctx.outputs.lef, ctx.outputs.lib]))]

carve_memories = rule(
    implementation = _carve_memories_impl,
    attrs = {
        "lef": attr.output(mandatory = True, doc = "The merged LEF."),
        "lib": attr.output(mandatory = True, doc = "The merged Liberty file."),
        "srcs": attr.label_list(
            providers = [OrfsInfo],
            doc = "The stages of the flows dissolved, whose memories are merged.",
        ),
        "_merge": attr.label(
            default = Label("//tools/carve:merge_memories"),
            executable = True,
            cfg = "exec",
        ),
    },
)
