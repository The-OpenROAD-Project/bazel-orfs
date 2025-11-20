"""Variables"""

load(
    "//toolchains/scala:scala_toolchain_info.bzl",
    "ActionTypeSetInfo",
    "BuiltinVariablesInfo",
    "VariableInfo",
)
load(":collect.bzl", "collect_action_types", "collect_provider")

types = struct(
    unknown = dict(name = "unknown", repr = "unknown"),
    void = dict(name = "void", repr = "void"),
    string = dict(name = "string", repr = "string"),
    bool = dict(name = "bool", repr = "bool"),
    # File and directory are basically the same thing as string for now.
    file = dict(name = "file", repr = "File"),
    directory = dict(name = "directory", repr = "directory"),
    option = lambda element: dict(
        name = "option",
        elements = element,
        repr = "Option[%s]" % element["repr"],
    ),
    list = lambda elements: dict(
        name = "list",
        elements = elements,
        repr = "List[%s]" % elements["repr"],
    ),
    struct = lambda **kv: dict(
        name = "struct",
        kv = kv,
        repr = "struct(%s)" %
               ", ".join(
                   ["{k}={v}".format(k = k, v = v["repr"]) for k, v in sorted(kv.items())],
               ),
    ),
)

def _scala_variable_impl(ctx):
    return [
        VariableInfo(
            name = ctx.label.name,
            label = ctx.label,
            type = json.decode(ctx.attr.type),
            actions = (
                collect_action_types(ctx.attr.actions) if ctx.attr.actions else None
            ),
        ),
    ]

_scala_variable = rule(
    implementation = _scala_variable_impl,
    attrs = {
        "actions": attr.label_list(providers = [ActionTypeSetInfo]),
        "type": attr.string(mandatory = True),
    },
    provides = [VariableInfo],
)

def scala_variable(name, type, **kwargs):
    """Exposes a toolchain variable to use in toolchain argument expansions.

    This internal rule exposes [toolchain variables](https://bazel.build/docs/cc-toolchain-config-reference#cctoolchainconfiginfo-build-variables)
    that may be expanded in `scala_args` or `scala_nested_args`
    rules. Because these varaibles merely expose variables inherrent to Bazel,
    it's not possible to declare custom variables.

    For a full list of available variables, see
    [@rules_cc//cc/toolchains/varaibles:BUILD](https://github.com/bazelbuild/rules_cc/tree/main/cc/toolchains/variables/BUILD).

    Example:
    ```
    load("//cc/toolchains/impl:variables.bzl", "scala_variable")

    # Defines two targets, ":foo" and ":foo.bar"
    scala_variable(
        name = "foo",
        type = types.list(types.struct(bar = types.string)),
    )
    ```

    Args:
        name: (str) The name of the outer variable, and the rule.
        type: The type of the variable, constructed using `types` factory in
            [@rules_cc//cc/toolchains/impl:variables.bzl](https://github.com/bazelbuild/rules_cc/tree/main/cc/toolchains/impl/variables.bzl).
        **kwargs: [common attributes](https://bazel.build/reference/be/common-definitions#common-attributes) that should be applied to this rule.
    """
    _scala_variable(name = name, type = json.encode(type), **kwargs)

def _scala_builtin_variables_impl(ctx):
    return [
        BuiltinVariablesInfo(
            variables = {
                variable.name: variable
                for variable in collect_provider(ctx.attr.srcs, VariableInfo)
            },
        ),
    ]

scala_builtin_variables = rule(
    implementation = _scala_builtin_variables_impl,
    attrs = {
        "srcs": attr.label_list(providers = [VariableInfo]),
    },
)
