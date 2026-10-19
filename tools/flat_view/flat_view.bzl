"""flat_view: a hierarchical flow's stage with its blocks put back in place.

    load("@bazel-orfs//tools/flat_view:flat_view.bzl", "flat_view")

    flat_view(
        name = "top_flat_grt",
        src = ":top_grt",
        blocks = {":BlockA_cts": "cts", ":BlockB_cts": "cts"},
    )

    bazelisk run //my:top_flat_grt_odb_debug -- ODB_DEBUG_DIR=tmp/odb-debug

builds top_flat_grt.odb, the parent's stage with every instance of each
block's macro replaced by the block's own cells at its own stage
(flatten.tcl says what is and is not copied), and <name>_odb_debug, the
odb-debug daemon and its GUI link on it, geometry only.
"""

load("//:openroad.bzl", "odb_debug", "orfs_run")

_ODB = {
    "cts": "4_cts.odb",
    "final": "6_final.odb",
    "floorplan": "2_floorplan.odb",
    "grt": "5_1_grt.odb",
    "place": "3_place.odb",
    "route": "5_route.odb",
}

def flat_view(name, src, blocks, tags = ["manual"], **kwargs):
    """The flat ODB of `src` and an odb_debug target on it.

    Args:
        name: Target name; the ODB is <name>.odb, the daemon <name>_odb_debug.
        src: The parent's stage, an orfs_flow `_<stage>` target.
        blocks: Each block's stage target and that stage's name, the stage
            whose ODB goes in the block's place: the stage the block is
            abstracted at.
        tags: Tags of every target made.
        **kwargs: Passed to both targets (`visibility`).
    """
    stage = src.rsplit("_", 1)[1]
    if stage not in _ODB:
        fail("flat_view %s: src %s is not a stage target (%s)" % (name, src, ", ".join(sorted(_ODB))))
    odbs = []
    for block, block_stage in blocks.items():
        if block_stage not in _ODB:
            fail("flat_view %s: %s's stage %s is not one of %s" % (name, block, block_stage, ", ".join(sorted(_ODB))))
        odb = "%s_%s_odb" % (name, block.rsplit(":", 1)[-1])
        native.filegroup(
            name = odb,
            srcs = [block],
            output_group = _ODB[block_stage],
            tags = tags,
        )
        odbs.append(":" + odb)
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".odb"],
        script = Label(":flatten.tcl"),
        tags = tags,
        user_arguments = {
            "FLAT_OUTPUT": "$(location %s.odb)" % name,
            "FLAT_STAGE": stage,
        },
        user_sources = {
            "FLAT_BLOCK_ODBS": odbs,
        },
        **kwargs
    )
    odb_debug(
        name = name + "_odb_debug",
        src = src,
        arguments = {"GUI_TIMING": "0"},
        odb = ":" + name,
        tags = tags,
        **kwargs
    )
