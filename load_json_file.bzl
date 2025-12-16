"""
A repository rule to load a yaml file and convert it into a Starlark file.
"""

def _load_json_file_impl(repository_ctx):
    yaml_file = repository_ctx.path(repository_ctx.attr.src)
    json_file = repository_ctx.path(repository_ctx.attr.out)
    result = repository_ctx.execute(
        [
            "python3",
            repository_ctx.path(repository_ctx.attr.script),
            yaml_file,
            json_file,
        ],
    )
    if result.return_code != 0:
        fail(
            "Failed to convert yaml to json: {}".format(result.stderr),
            result.return_code,
        )
    json_data = json.decode(repository_ctx.read(json_file))
    repository_ctx.file("json.bzl", "orfs_variable_metadata = " + repr(json_data))
    repository_ctx.file("BUILD", "")

load_json_file = repository_rule(
    implementation = _load_json_file_impl,
    attrs = {
        "out": attr.string(),
        "script": attr.label(allow_single_file = True),
        "src": attr.label(allow_single_file = True),
    },
    local = True,
)
