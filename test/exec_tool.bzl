"""exec_tool: a tool in the exec configuration, for a test's data.

A test that lists `@openroad` or `@yosys` in `data` builds the binary in
the target configuration, a second compile of it and everything it links
next to the exec-configuration one every flow stage uses. Listing an
exec_tool instead hands the test the binary the stages already built:
same file, same short path, so `$(rootpath ...)` is unchanged.
"""

def _exec_tool_impl(ctx):
    info = ctx.attr.tool[DefaultInfo]
    exe = info.files_to_run.executable
    return [DefaultInfo(
        files = depset([exe]),
        runfiles = ctx.runfiles([exe]).merge(info.default_runfiles),
    )]

exec_tool = rule(
    implementation = _exec_tool_impl,
    attrs = {
        "tool": attr.label(
            mandatory = True,
            executable = True,
            cfg = "exec",
        ),
    },
)
