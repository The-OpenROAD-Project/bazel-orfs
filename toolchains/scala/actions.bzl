"""
This module defines rules for working with Scala actions.
"""

load("//toolchains/scala/impl:collect.bzl", "collect_action_types")
load(":scala_toolchain_info.bzl", "ActionTypeInfo", "ActionTypeSetInfo")

def _scala_action_type_impl(ctx):
    action_type = ActionTypeInfo(label = ctx.label, name = ctx.attr.action_name)
    return [
        action_type,
        ActionTypeSetInfo(
            label = ctx.label,
            actions = depset([action_type]),
        ),
    ]

scala_action_type = rule(
    implementation = _scala_action_type_impl,
    attrs = {
        "action_name": attr.string(
            mandatory = True,
        ),
    },
    doc = """A type of action (eg. c_compile, assemble, strip).

`scala_action_type` rules are used to associate arguments and tools together to
perform a specific action. Bazel prescribes a set of known action types that are used to drive
typical C/C++/ObjC actions like compiling, linking, and archiving. The set of well-known action
types can be found in [@rules_cc//cc/toolchains/actions:BUILD](https://github.com/bazelbuild/rules_cc/tree/main/cc/toolchains/actions/BUILD).

It's possible to create project-specific action types for use in toolchains. Be careful when
doing this, because every toolchain that encounters the action will need to be configured to
support the custom action type. If your project is a library, avoid creating new action types as
it will reduce compatibility with existing toolchains and increase setup complexity for users.

Example:
```
load("//cc:action_names.bzl", "ACTION_NAMES")
load("//cc/toolchains:actions.bzl", "scala_action_type")

scala_action_type(
    name = "cpp_compile",
    action_name =  = ACTION_NAMES.cpp_compile,
)
```
""",
    provides = [ActionTypeInfo, ActionTypeSetInfo],
)

def _scala_action_type_set_impl(ctx):
    if not ctx.attr.actions and not ctx.attr.allow_empty:
        fail("Each scala_action_type_set must contain at least one action type.")
    return [ActionTypeSetInfo(
        label = ctx.label,
        actions = collect_action_types(ctx.attr.actions),
    )]

scala_action_type_set = rule(
    doc = """Represents a set of actions.

This is a convenience rule to allow for more compact representation of a group of action types.
Use this anywhere a `scala_action_type` is accepted.

Example:
```
load("//cc/toolchains:actions.bzl", "scala_action_type_set")

scala_action_type_set(
    name = "link_executable_actions",
    actions = [
        "//cc/toolchains/actions:cpp_link_executable",
        "//cc/toolchains/actions:lto_index_for_executable",
    ],
)
```
""",
    implementation = _scala_action_type_set_impl,
    attrs = {
        "actions": attr.label_list(
            providers = [ActionTypeSetInfo],
            mandatory = True,
            doc = "A list of scala_action_type or scala_action_type_set",
        ),
        "allow_empty": attr.bool(default = False),
    },
    provides = [ActionTypeSetInfo],
)
