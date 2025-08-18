"""Implementation of scala_tool_map."""

load(
    "//toolchains/scala/impl:collect.bzl",
    "collect_provider",
)
load(
    ":scala_toolchain_info.bzl",
    "ActionTypeSetInfo",
    "ToolConfigInfo",
)

def _scala_tool_map_impl(ctx):
    action_sets = collect_provider(ctx.attr.actions, ActionTypeSetInfo)

    action_to_tool = {}
    action_to_as = {}
    for i in range(len(action_sets)):
        action_set = action_sets[i]
        tool = ctx.attr.tools[ctx.attr.tool_index_for_action[i]]

        for action in action_set.actions.to_list():
            if action in action_to_as:
                fail("The action %s appears multiple times in your tool_map (as %s and %s)" % (action.label, action_set.label, action_to_as[action].label))
            action_to_as[action] = action_set
            action_to_tool[action] = tool

    return [ToolConfigInfo(label = ctx.label, configs = action_to_tool)]

_scala_tool_map = rule(
    implementation = _scala_tool_map_impl,
    # @unsorted-dict-items
    attrs = {
        "actions": attr.label_list(
            providers = [ActionTypeSetInfo],
            mandatory = True,
            doc = """A list of action names to apply this action to.

See //cc/toolchains/actions:BUILD for valid options.
""",
        ),
        "tools": attr.label_list(
            mandatory = True,
            cfg = "exec",
            allow_files = True,
            doc = """The tool to use for the specified actions.

The tool may be a `scala_tool` or other executable rule.
""",
        ),
        "tool_index_for_action": attr.int_list(
            mandatory = True,
            doc = """The index of the tool in `tools` for the action in `actions`.""",
        ),
    },
    provides = [ToolConfigInfo],
)

def scala_tool_map(name, tools, **kwargs):
    """A toolchain configuration rule that maps toolchain actions to tools.

    A `scala_tool_map` aggregates all the tools that may be used for a given toolchain
    and maps them to their corresponding actions. Conceptually, this is similar to the
    `CXX=/path/to/clang++` environment variables that most build systems use to determine which
    tools to use for a given action. To simplify usage, some actions have been grouped together (for
    example,
    [@rules_cc//cc/toolchains/actions:cpp_compile_actions](https://github.com/bazelbuild/rules_cc/tree/main/cc/toolchains/actions/BUILD)) to
    logically express "all the C++ compile actions".

    In Bazel, there is a little more granularity to the mapping, so the mapping doesn't follow the
    traditional `CXX`, `AR`, etc. naming scheme. For a comprehensive list of all the well-known
    actions, see //cc/toolchains/actions:BUILD.

    Example usage:
    ```
    load("//cc/toolchains:tool_map.bzl", "scala_tool_map")

    scala_tool_map(
        name = "all_tools",
        tools = {
            "//cc/toolchains/actions:assembly_actions": ":asm",
            "//cc/toolchains/actions:c_compile": ":clang",
            "//cc/toolchains/actions:cpp_compile_actions": ":clang++",
            "//cc/toolchains/actions:link_actions": ":lld",
            "//cc/toolchains/actions:objcopy_embed_data": ":llvm-objcopy",
            "//cc/toolchains/actions:strip": ":llvm-strip",
            "//cc/toolchains/actions:ar_actions": ":llvm-ar",
        },
    )
    ```

    Args:
        name: (str) The name of the target.
        tools: (Dict[Label, Label]) A mapping between
            `scala_action_type`/`scala_action_type_set` targets
            and the `scala_tool` or executable target that implements that action.
        **kwargs: [common attributes](https://bazel.build/reference/be/common-definitions#common-attributes) that should be applied to this rule.
    """
    actions = []
    tool_index_for_action = []
    deduplicated_tools = {}
    for action, tool in tools.items():
        actions.append(action)
        label = native.package_relative_label(tool)
        if label not in deduplicated_tools:
            deduplicated_tools[label] = len(deduplicated_tools)
        tool_index_for_action.append(deduplicated_tools[label])

    _scala_tool_map(
        name = name,
        actions = actions,
        tools = deduplicated_tools.keys(),
        tool_index_for_action = tool_index_for_action,
        **kwargs
    )
