"""A tool built for the exec platform, as a flow's openroad is: optimised,
and the remote cache's builds of OpenROAD's libraries are hits."""

def _exec_tool_impl(ctx):
    tool = ctx.attr.tool[DefaultInfo]
    return [DefaultInfo(
        files = depset([ctx.executable.tool]),
        runfiles = ctx.runfiles([ctx.executable.tool]).merge(tool.default_runfiles),
    )]

exec_tool = rule(
    implementation = _exec_tool_impl,
    doc = "The executable `tool` in the exec configuration, with its runfiles, as data.",
    attrs = {
        "tool": attr.label(executable = True, cfg = "exec", mandatory = True),
    },
)
