"""
A repository rule to load a yaml file and convert it into a Starlark file.
"""

def _load_json_file_impl(ctx):
    yaml_file = ctx.path(ctx.attr.src)
    json_file = ctx.path(ctx.attr.out)

    ctx.execute([ctx.path(ctx.attr.script),yaml_file, json_file])

    json_data = json.decode(ctx.read(json_file))
    ctx.file("json.bzl", "orfs_variable_metadata = " + repr(json_data))
    ctx.file("BUILD", "")

load_json_file = repository_rule(
    implementation = _load_json_file_impl,
    attrs = {
        "src": attr.label(allow_single_file = True),
        "script": attr.label(
            allow_files = True,
            executable = True,
            cfg = "exec",
        ),
        "out": attr.string(),
    },
    local = True,
)
