"""orfs_schedule(): a scheduler at home (docs/schedule.md)."""

load("@rules_python//python:defs.bzl", "py_binary")

def _absolute(target):
    """`:t` or `t` in this package as `//pkg:t`, for a build at the root."""
    if target.startswith("//") or target.startswith("@"):
        return target
    return "//%s:%s" % (native.package_name(), target.removeprefix(":"))

def _units(flag, units):
    return [
        "%s=%s=%s" % (flag, name, ",".join([_absolute(t) for t in targets]))
        for name, targets in units.items()
    ]

def orfs_schedule(name, macros = {}, parent = {}, resources = "resources.json", **kwargs):
    """`bazelisk run :<name>` builds a design's flows in waves that fit memory.

    The macro units are packed into waves whose summed peak memory,
    recorded in `resources`, fits the free memory; the parent units run
    alone, last. Each wave is one `bazelisk build`. Afterwards the units'
    ORFS stage logs are read and `resources` is updated where it is
    estimated or materially off. With no `resources` file the run stops:
    the first one comes from an assessment (the scale-to-memory skill).

    Args:
      name: the target to `bazelisk run`.
      macros: {unit name: [targets]}, built in waves; a unit's name is what
        `resources` records it under, usually its flow's name.
      parent: {unit name: [targets]}, each built alone after the macros.
      resources: the record, beside this BUILD file, version-controlled.
      **kwargs: passed to the py_binary (tags, visibility).
    """
    py_binary(
        name = name,
        srcs = [Label("//tools/flow_schedule:schedule.py")],
        main = Label("//tools/flow_schedule:schedule.py"),
        args = [
            "--package=" + native.package_name(),
            "--resources=" + resources,
        ] + _units("--macro", macros) + _units("--parent", parent),
        **kwargs
    )
