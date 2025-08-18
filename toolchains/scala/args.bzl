"""All providers for rule-based bazel toolchain config."""

load(
    "//toolchains/scala/impl:collect.bzl",
    "collect_action_types",
    "collect_files",
)
load(
    ":scala_toolchain_info.bzl",
    "ActionTypeSetInfo",
    "ArgsInfo",
    "ArgsListInfo",
    "VariableInfo",
)

visibility("public")

def _scala_args_impl(ctx):
    actions = collect_action_types(ctx.attr.actions)

    files = collect_files(ctx.attr.data)

    args = ArgsInfo(
        actions = actions,
        args = ctx.attr.args,
        env = ctx.attr.env,
        files = files,
        format = ctx.attr.format,
        join_with = ctx.attr.join_with,
        iterate_over = ctx.attr.iterate_over,
        label = ctx.label,
    )

    return [
        args,
        ArgsListInfo(
            label = ctx.label,
            args = tuple([args]),
            files = files,
            by_action = tuple([
                struct(action = action, args = tuple([args]), files = files)
                for action in actions.to_list()
            ]),
        ),
    ]

_scala_args = rule(
    implementation = _scala_args_impl,
    attrs = {
        "actions": attr.label_list(
            providers = [ActionTypeSetInfo],
            mandatory = True,
            doc = """See documentation for scala_args macro wrapper.""",
        ),
        "args": attr.string_list(
            doc = """json-encoded arguments to be added to the command-line.

    Usage:
    cc_args(
        ...,
        args = ["--foo={foo}"],
        format = {
            "//cc/toolchains/variables:foo": "foo"
        },
    )

    This is equivalent to flag_group(flags = ["--foo", "%{foo}"])
    """,
        ),
        "env": attr.string_dict(
            doc = """See documentation for scala_args macro wrapper.""",
        ),
        "data": attr.label_list(
            allow_files = True,
            doc = """Files required to add this argument to the command-line.

    For example, a flag that sets the header directory might add the headers in that
    directory as additional files.
    """,
        ),
        "format": attr.label_keyed_string_dict(
            doc = "Variables to be used in substitutions",
        ),
        "join_with": attr.label_keyed_string_dict(
            doc = "A delimiter string used to join together the strings",
        ),
        "iterate_over": attr.label(providers = [VariableInfo], doc = "Replacement for flag_group.iterate_over"),
        "requires_not_none": attr.label(providers = [VariableInfo], doc = "Replacement for flag_group.expand_if_available"),
        "requires_none": attr.label(providers = [VariableInfo], doc = "Replacement for flag_group.expand_if_not_available"),
        "requires_true": attr.label(providers = [VariableInfo], doc = "Replacement for flag_group.expand_if_true"),
        "requires_false": attr.label(providers = [VariableInfo], doc = "Replacement for flag_group.expand_if_false"),
        "requires_equal": attr.label(providers = [VariableInfo], doc = "Replacement for flag_group.expand_if_equal"),
        "requires_equal_value": attr.string(),
        "_variables": attr.label(
            default = "//toolchains/scala/variables:variables",
        ),
    },
    provides = [ArgsInfo],
    doc = """Declares a list of arguments bound to a set of actions.

Roughly equivalent to ctx.actions.args()

Examples:
    scala_args(
        name = "warnings_as_errors",
        args = ["-Werror"],
    )
""",
)

def scala_args(
        *,
        name,
        actions = None,
        args = None,
        data = None,
        env = None,
        format = {},
        join_with = {},
        iterate_over = None,
        requires_not_none = None,
        requires_none = None,
        requires_true = None,
        requires_false = None,
        requires_equal = None,
        requires_equal_value = None,
        **kwargs):
    """Action-specific arguments for use with a `scala_toolchain`.

    This rule is the fundamental building building block for every toolchain tool invocation. Each
    argument expressed in a toolchain tool invocation (e.g. `gcc`, `llvm-ar`) is declared in a
    `scala_args` rule that applies an ordered list of arguments to a set of toolchain
    actions. `scala_args` rules can be added unconditionally to a
    `scala_toolchain`, conditionally via `select()` statements, or dynamically via an
    intermediate `scala_feature`.

    Conceptually, this is similar to the old `CFLAGS`, `CPPFLAGS`, etc. environment variables that
    many build systems use to determine which flags to use for a given action. The significant
    difference is that `scala_args` rules are declared in a structured way that allows for
    significantly more powerful and sharable toolchain configurations. Also, due to Bazel's more
    granular action types, it's possible to bind flags to very specific actions (e.g. LTO indexing
    for an executable vs a dynamic library) multiple different actions (e.g. C++ compile and link
    simultaneously).

    Example usage:
    ```
    load("//cc/toolchains:args.bzl", "scala_args")

    # Basic usage: a trivial flag.
    #
    # An example of expressing `-Werror` as a `scala_args` rule.
    scala_args(
        name = "warnings_as_errors",
        actions = [
            # Applies to all C/C++ compile actions.
            "//cc/toolchains/actions:compile_actions",
        ],
        args = ["-Werror"],
    )

    # Basic usage: ordered flags.
    #
    # An example of linking against libc++, which uses two flags that must be applied in order.
    scala_args(
        name = "link_libcxx",
        actions = [
            # Applies to all link actions.
            "//cc/toolchains/actions:link_actions",
        ],
        # On tool invocation, this appears as `-Xlinker -lc++`. Nothing will ever end up between
        # the two flags.
        args = [
            "-Xlinker",
            "-lc++",
        ],
    )

    # Advanced usage: built-in variable expansions.
    #
    # Expands to `-L/path/to/search_dir` for each directory in the built-in variable
    # `library_search_directories`. This variable is managed internally by Bazel through inherent
    # behaviors of Bazel and the interactions between various C/C++ build rules.
    scala_args(
        name = "library_search_directories",
        actions = [
            "//cc/toolchains/actions:link_actions",
        ],
        args = ["-L{search_dir}"],
        iterate_over = "//cc/toolchains/variables:library_search_directories",
        requires_not_none = "//cc/toolchains/variables:library_search_directories",
        format = {
            "search_dir": "//cc/toolchains/variables:library_search_directories",
        },
    )
    ```

    For more extensive examples, see the usages here:
        https://github.com/bazelbuild/rules_cc/tree/main/cc/toolchains/args

    Args:
        name: (str) The name of the target.
        actions: (List[Label]) A list of labels of `scala_action_type` or
            `scala_action_type_set` rules that dictate which actions these
            arguments should be applied to.
        args: (List[str]) The command-line arguments that are applied by using this rule.
        data: (List[Label]) A list of runtime data dependencies that are required for these
            arguments to work as intended.
        env: (Dict[str, str]) Environment variables that should be set when the tool is invoked.
        format: (Dict[str, Label]) A mapping of format strings to the label of the corresponding
            `scala_variable` that the value should be pulled from. All instances of
            `{variable_name}` will be replaced with the expanded value of `variable_name` in this
            dictionary. The complete list of possible variables can be found in
            https://github.com/bazelbuild/rules_cc/tree/main/cc/toolchains/variables/BUILD.
            It is not possible to declare custom variables--these are inherent to Bazel itself.
        join_with: (Dict[str, Label]) A mapping of string delimiter to the label of the corresponding
            `scala_variable` to join.
        iterate_over: (Label) The label of a `scala_variable` that should be iterated over. This is
            intended for use with built-in variables that are lists.
        requires_not_none: (Label) The label of a `scala_variable` that should be checked
            for existence before expanding this rule. If the variable is None, this rule will be
            ignored.
        requires_none: (Label) The label of a `scala_variable` that should be checked for
            non-existence before expanding this rule. If the variable is not None, this rule will be
            ignored.
        requires_true: (Label) The label of a `scala_variable` that should be checked for
            truthiness before expanding this rule. If the variable is false, this rule will be
            ignored.
        requires_false: (Label) The label of a `scala_variable` that should be checked
            for falsiness before expanding this rule. If the variable is true, this rule will be
            ignored.
        requires_equal: (Label) The label of a `scala_variable` that should be checked
            for equality before expanding this rule. If the variable is not equal to
            (requires_equal_value)[#scala_args-requires_equal_value], this rule will be ignored.
        requires_equal_value: (str) The value to compare (requires_equal)[#scala_args-requires_equal]
            against.
        **kwargs: [common attributes](https://bazel.build/reference/be/common-definitions#common-attributes) that should be applied to this rule.
    """
    return _scala_args(
        name = name,
        actions = actions,
        args = args,
        data = data,
        env = env,
        # We flip the key/value pairs in the dictionary here because Bazel doesn't have a
        # string-keyed label dict attribute type.
        format = {k: v for v, k in format.items()},
        join_with = {k: v for v, k in join_with.items()},
        iterate_over = iterate_over,
        requires_not_none = requires_not_none,
        requires_none = requires_none,
        requires_true = requires_true,
        requires_false = requires_false,
        requires_equal = requires_equal,
        requires_equal_value = requires_equal_value,
        **kwargs
    )
