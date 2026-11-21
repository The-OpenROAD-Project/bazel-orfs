"""Build settings owned by bazel-orfs.

Bazel's own `config.bool` build setting, rather than bazel_skylib's
`bool_flag`: skylib is a `dev_dependency` in MODULE.bazel, so reaching
for it here would force it on every consumer for the sake of eight
lines.
"""

OrfsFlagInfo = provider(
    doc = "Value of a bazel-orfs command-line flag.",
    fields = {"value": "The flag's value."},
)

def _orfs_bool_flag_impl(ctx):
    return OrfsFlagInfo(value = ctx.build_setting_value)

orfs_bool_flag = rule(
    doc = "A boolean flag settable on the command line with --@bazel-orfs//:<name>.",
    implementation = _orfs_bool_flag_impl,
    build_setting = config.bool(flag = True),
)

def _orfs_int_flag_impl(ctx):
    return OrfsFlagInfo(value = ctx.build_setting_value)

orfs_int_flag = rule(
    doc = "An integer flag settable on the command line with --@bazel-orfs//:<name>=<n>.",
    implementation = _orfs_int_flag_impl,
    build_setting = config.int(flag = True),
)

def _orfs_string_flag_impl(ctx):
    if ctx.attr.values and ctx.build_setting_value not in ctx.attr.values:
        fail("--%s=%s: one of %s" % (ctx.label, ctx.build_setting_value, ", ".join(ctx.attr.values)))
    return OrfsFlagInfo(value = ctx.build_setting_value)

orfs_string_flag = rule(
    doc = "A string flag settable on the command line with --@bazel-orfs//:<name>=<value>.",
    implementation = _orfs_string_flag_impl,
    build_setting = config.string(flag = True),
    attrs = {"values": attr.string_list(doc = "The values allowed; any, when empty.")},
)
