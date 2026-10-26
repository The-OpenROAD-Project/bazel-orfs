"""gperftools' profiler built without aw-backtrace.

aw-backtrace needs glibc 2.35 (_dl_find_object); the hermetic toolchain's
sysroot is older. The flag is set on this target alone, not in .bazelrc,
so nothing else in the build loads gperftools.
"""

def _no_aw_backtrace_impl(_settings, _attr):
    return {"@gperftools//:enable_aw_backtrace": False}

_no_aw_backtrace = transition(
    implementation = _no_aw_backtrace_impl,
    inputs = [],
    outputs = ["@gperftools//:enable_aw_backtrace"],
)

def _profiler_so_impl(ctx):
    src = ctx.attr.src[0][DefaultInfo].files.to_list()[0]
    out = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(output = out, target_file = src)
    return [DefaultInfo(files = depset([out]), runfiles = ctx.runfiles([out]))]

profiler_so = rule(
    implementation = _profiler_so_impl,
    attrs = {
        "src": attr.label(cfg = _no_aw_backtrace, mandatory = True),
    },
)
