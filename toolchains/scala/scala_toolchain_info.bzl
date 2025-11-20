"""
This module defines providers for Scala toolchain information.
"""

ArgsInfo = provider(
    doc = "A set of arguments to be added to the command line for specific actions",
    # @unsorted-dict-items
    fields = {
        "args": "(List[str]) The command-line arguments that are applied by using this rule.",
        "format": "(Dict[str, Label]) A mapping of format strings to the label of the corresponding `scala_variable`",
        "label": "(Label) The label defining this provider. Place in error messages to simplify debugging",
        "iterate_over": "(Optional[VariableInfo]) The variable to iterate over",
        "join_with": "(Optional[str]) A delimiter string used to join together the strings",
        "actions": "(depset[ActionTypeInfo]) The set of actions this is associated with",
        "files": "(depset[File]) Files required for the args",
        "env": "(dict[str, str]) Environment variables to apply",
    },
)

ArgsListInfo = provider(
    doc = "A ordered list of arguments",
    # @unsorted-dict-items
    fields = {
        "label": "(Label) The label defining this provider. Place in error messages to simplify debugging",
        "args": "(Sequence[ArgsInfo]) The flag sets contained within",
        "files": "(depset[File]) The files required for all of the arguments",
        "by_action": "(Sequence[struct(action=ActionTypeInfo, args=List[ArgsInfo], files=depset[Files])]) Relevant information about the args keyed by the action type.",
    },
)

ActionTypeInfo = provider(
    doc = "A type of action (eg. c-compile, c++-link-executable)",
    # @unsorted-dict-items
    fields = {
        "label": "(Label) The label defining this provider. Place in error messages to simplify debugging",
        "name": "(str) The action name, as defined by action_names.bzl",
    },
)

ActionTypeSetInfo = provider(
    doc = "A set of types of actions",
    # @unsorted-dict-items
    fields = {
        "label": "(Label) The label defining this provider. Place in error messages to simplify debugging",
        "actions": "(depset[ActionTypeInfo]) Set of action types",
    },
)

ToolConfigInfo = provider(
    doc = "A mapping from action to tool",
    # @unsorted-dict-items
    fields = {
        "label": "(Label) The label defining this provider. Place in error messages to simplify debugging",
        "configs": "(dict[ActionTypeInfo, Target]) A mapping from action to tool.",
    },
)

VariableInfo = provider(
    """A variable defined by the toolchain""",
    # @unsorted-dict-items
    fields = {
        "name": "(str) The variable name",
        "label": "(Label) The label defining this provider. Place in error messages to simplify debugging",
        "actions": "(Optional[depset[ActionTypeInfo]]) The actions this variable is available for",
        "type": "A type constructed using variables.types.*",
    },
)

BuiltinVariablesInfo = provider(
    doc = "The builtin variables",
    fields = {
        "variables": "(dict[str, VariableInfo]) A mapping from variable name to variable metadata.",
    },
)
