load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

def _param_impl(ctx):
    """Implementation of the param rule."""

    # 1. Gather configuration values from the build settings
    config_map = {}
    for target, param_name in ctx.attr.parameters.items():
        # Extract the typed value (int, bool, string) from the provider
        if BuildSettingInfo in target:
            config_map[param_name] = target[BuildSettingInfo].value
        else:
            fail("Target {} must provide BuildSettingInfo.".format(target.label))

    # 2. Serialize to JSON
    # using encode_indent for readability, or encode for compactness
    json_content = json.encode_indent(config_map)

    # 3. Write the JSON file
    out_file = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(
        output = out_file,
        content = json_content,
    )

    return [DefaultInfo(files = depset([out_file]))]

param = rule(
    implementation = _param_impl,
    attrs = {
        "parameters": attr.label_keyed_string_dict(
            doc = "Dictionary mapping build setting labels (flags) to JSON keys.",
            providers = [BuildSettingInfo],
            mandatory = True,
        ),
    },
    doc = """
    Converts configuration parameters to a .json file that can be fed into a static
    orfs_flow() graph. Each stage runs an action to whittle the .json file down to
    the parameters needed for that stage.
    
    This allows configuring the orfs_flow() graph entirely on the command line of
    bazel via --//path:parameter=value pairs defined by the user.
    """,
)
