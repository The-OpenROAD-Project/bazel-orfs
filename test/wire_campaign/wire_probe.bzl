"""One row of the wire campaign from a place checkpoint (wire_probe.tcl)."""

load("@bazel-orfs//:openroad.bzl", "orfs_run")

def wire_probe(name, src, arguments, sources, stage_stem = "3_place", **kwargs):
    """The reg2reg period, its wire-free floor, wirelength and the place steps' cost, as `<name>.json`.

    Args:
      name: the target, and the stem of the JSON it writes.
      src: the flow's place stage, e.g. ":XSTile_place".
      arguments: the flow's arguments, as orfs_run wants them.
      sources: the flow's sources, as orfs_run wants them.
      stage_stem: the checkpoint to read, 3_place by default.
      **kwargs: passed to orfs_run (variant, tags, ...).
    """
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".json"],
        arguments = arguments,
        script = "//test/wire_campaign:wire_probe.tcl",
        sources = sources,
        src_logs = True,
        user_arguments = {
            "OUTPUT_JSON": "$(location %s.json)" % name,
            "STAGE_STEM": stage_stem,
        },
        **kwargs
    )
