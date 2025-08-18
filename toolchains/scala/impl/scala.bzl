"""Scala rules"""

load("//toolchains/scala:scala_toolchain_info.bzl", "VariableInfo")
load("//toolchains/scala/impl:args_utils.bzl", "get_action_type")
load("//toolchains/scala/impl:collect.bzl", "collect_args_lists")
load("//toolchains/scala/impl:variables.bzl", "types")

def format(t, var):
    """
    Formats a variable based on its type.

    Args:
        t: The type of the variable.
        var: The variable to format.

    Returns:
        The formatted variable.
    """
    if t == types.unknown:
        fail("can't format unkown struct")
    if t == types.void:
        return types.void["name"]
    if t == types.string:
        return var
    if t == types.bool:
        return var
    if t == types.file:
        return var.path
    if t == types.list(types.file) and len(var) == 1:
        return var[0].path
    fail("format(): did not handle {}".format(t))

def collect(t, var):
    """
    Collects variables based on their type.

    Args:
        t: The type of the variable.
        var: The variable to collect.

    Returns:
        A set of collected variables.
    """
    if t in [types.unknown, types.void, types.string, types.bool, types.list(types.string)]:
        return depset([])
    if t in [types.file, types.directory, types.list(types.file)]:
        if type(var) in ["File", "depset"]:
            return var

    fail("collect(): did not handle {}".format(t))

def collect_formats(arg, variable):
    """Collects formatted argument values based on the argument specification and variable values.

    Args:
        arg: The argument specification.
        variable: The variable values to format.

    Returns:
        A list of formatted argument values.
    """
    if arg.iterate_over:
        return [{arg.format[arg.iterate_over]: format(arg.iterate_over[VariableInfo].type["elements"], var)} for var in variable[arg.iterate_over[VariableInfo]].to_list()]
    elif arg.join_with:
        return [{arg.format[var]: delimiter.join([format(var[VariableInfo].type["elements"], f) for f in variable[var[VariableInfo]].to_list()]) for var, delimiter in arg.join_with.items()}]
    elif arg.format:
        return [{v: format(types.list(types.file), k.files.to_list())} for k, v in arg.format.items()]
    else:
        return [{}]

def collect_files(arg, variable):
    """
    Collects file variables based on the argument specification and variable values.

    Args:
        arg: The argument specification.
        variable: The variable values to collect.

    Returns:
        A set of collected file variables.
    """
    if arg.iterate_over:
        return collect(arg.iterate_over[VariableInfo].type, variable[arg.iterate_over[VariableInfo]])
    if arg.join_with:
        return depset(transitive = [collect(var[VariableInfo].type, variable[var[VariableInfo]]) for var in arg.join_with])
    else:
        return depset(transitive = [target.files for target in arg.format.keys()])

def args_by_action(toolchain, variable, action, label):
    """
    Collects argument values based on the action type and label.

    Args:
        toolchain: The toolchain information.
        variable: The variable values to collect.
        action: The action type to filter by.
        label: The label to filter by.

    Returns:
        A struct containing the collected argument values and file variables.
    """
    args = []
    files = []
    arg_list = collect_args_lists(toolchain.args, label)
    arg_info = get_action_type(arg_list, action)
    for arg in arg_info.args:
        files.append(collect_files(arg, variable))
        for format in collect_formats(arg, variable):
            args.extend([a.format(**format) for a in arg.args])
    return struct(args = args, files = files)
