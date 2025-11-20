"""Helper functions to allow us to collect data from attr.label_list."""

load(
    "//toolchains/scala:scala_toolchain_info.bzl",
    "ActionTypeSetInfo",
    "ArgsListInfo",
)

visibility(
    [
        "//toolchains/scala/...",
    ],
)

def collect_provider(targets, provider):
    """Collects providers from a label list.

    Args:
        targets: (List[Target]) An attribute from attr.label_list
        provider: (provider) The provider to look up
    Returns:
        A list of the providers
    """
    return [target[provider] for target in targets]

def collect_defaultinfo(targets):
    """Collects DefaultInfo from a label list.

    Args:
        targets: (List[Target]) An attribute from attr.label_list
    Returns:
        A list of the associated defaultinfo
    """
    return collect_provider(targets, DefaultInfo)

def _make_collector(provider, field):
    def collector(targets, direct = [], transitive = []):
        # Avoid mutating what was passed in.
        transitive = transitive[:]
        for value in collect_provider(targets, provider):
            transitive.append(getattr(value, field))
        return depset(direct = direct, transitive = transitive)

    return collector

collect_action_types = _make_collector(ActionTypeSetInfo, "actions")
collect_files = _make_collector(DefaultInfo, "files")

def collect_data(ctx, targets):
    """Collects from a 'data' attribute.

    This is distinguished from collect_files by the fact that data attributes
    attributes include runfiles.

    Args:
        ctx: (Context) The ctx for the current rule
        targets: (List[Target]) A list of files or executables

    Returns:
        A depset containing all files for each of the targets, and all runfiles
        required to run them.
    """
    return ctx.runfiles(transitive_files = collect_files(targets)).merge_all(
        [
            info.default_runfiles
            for info in collect_defaultinfo(targets)
            if info.default_runfiles != None
        ],
    )

def collect_args_lists(targets, label):
    """Collects a label_list of ArgsListInfo into a single ArgsListInfo

    Args:
        targets: (List[Target]) A label_list of targets providing ArgsListInfo
        label: The label to attach to the resulting ArgsListInfo
    Returns:
        An ArgsListInfo that is the result of joining all of the ArgsListInfos
        together.
    """
    args = []
    by_action = {}
    transitive_files = []
    for target in targets:
        args_list = target[ArgsListInfo]
        args.extend(args_list.args)
        transitive_files.extend([args_info.files for args_info in args_list.args])
        for value in args_list.by_action:
            out = by_action.setdefault(
                value.action,
                struct(args = [], transitive_files = [], action = value.action),
            )
            out.args.extend(value.args)
            out.transitive_files.append(value.files)

    return ArgsListInfo(
        label = label,
        args = tuple(args),
        files = depset(transitive = transitive_files),
        by_action = tuple(
            [
                struct(
                    action = k,
                    args = tuple(v.args),
                    files = depset(transitive = v.transitive_files),
                )
                for k, v in by_action.items()
            ],
        ),
    )
