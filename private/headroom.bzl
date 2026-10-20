"""orfs_headroom: how much of a parent's reg2reg period is left on the table,
across the parent and its blocks.

    load("@bazel-orfs//:openroad.bzl", "orfs_headroom")

    orfs_headroom(
        name = "cpu_headroom",
        parent = "cpu",
        parent_stage = ":cpu_grt",
        blocks = {"alu": ":alu_grt", "regfile": ":regfile_grt"},
    )

    bazelisk build //my:cpu_headroom

exports each part at its stage (its netlist, its parasitics, its SDC and
liberty), stitches them in OpenSTA with every block's real cells in place
of its abstract, and runs the measurements of
tools/odb_debug/headroom.tcl on the whole: the reg2reg period, the
one-flop-loop and retiming floors, useful skew and threshold voltage
(with the leakage it costs), each split into the parent's part and the
blocks', and with a `target` the mass at or over it at each. `<name>.json` has them, and
`<name>_nowire.json` the zero-wire floor. The odb-debug daemon's
`headroom` tool asks the same of one stage alone, a block being its
abstract. When to ask and how to read the answer:
.claude/skills/repair-headroom/SKILL.md.

A whole core stitched this way needs memory: plan for the parent's own
stage's peak and more.
"""

load("//private:rules.bzl", "orfs_run")

def orfs_headroom(name, parent, parent_stage, blocks, ends = 0, target = 0, tags = ["manual"], **kwargs):
    """Repair headroom of `parent` and its `blocks`, stitched at their stages.

    Args:
        name: Target name; also names its outputs, `<name>.json` and
            `<name>_nowire.json`.
        parent: The parent's module name, as its netlist calls it.
        parent_stage: The parent's flow stage to measure, e.g. `:cpu_grt`.
        blocks: {module name: its flow stage}, one entry per hardened
            block module however often the parent instantiates it.
        ends: Scope of each measurement: the cones of this many worst
            reg2reg endpoints; 0, the default, is every endpoint. Limit it
            only to make a very large design answer at all.
        target: A target period in the liberty's time unit; each
            measurement then also counts the reg2reg endpoints at or over
            it and their total excess. 0, the default, counts none. For a
            design whose SDC asks far less than the goal, where nearly
            every endpoint violates and TNS says nothing.
        tags: Tags of every target; manual by default, as the stitched
            view of a large design is no CI job.
        **kwargs: Passed to every target, e.g. `visibility`.
    """
    parts = {parent: parent_stage} | blocks
    for part, stage in parts.items():
        orfs_run(
            name = "%s_%s_part" % (name, part),
            src = stage,
            outs = ["%s/%s.%s" % (name, part, e) for e in ["v", "spef", "sdc"]] +
                   ["%s/%s_libs.tar" % (name, part)],
            script = Label("//tools/headroom:sta_part.tcl"),
            tags = tags,
            user_arguments = {
                "PART_LIBS": "$(location %s/%s_libs.tar)" % (name, part),
                "PART_SDC": "$(location %s/%s.sdc)" % (name, part),
                "PART_SPEF": "$(location %s/%s.spef)" % (name, part),
                "PART_V": "$(location %s/%s.v)" % (name, part),
                "STA_ILM": "0",
            },
            **kwargs
        )
    files = ["%s/%s.%s" % (name, p, e) for p in parts for e in ["v", "spef", "sdc"]] + \
            ["%s/%s_libs.tar" % (name, p) for p in parts]
    for suffix, wires in [("", "1"), ("_nowire", "0")]:
        native.genrule(
            name = name + suffix,
            srcs = [":" + f for f in files],
            outs = [name + suffix + ".json"],
            cmd = " && ".join([
                "w=$$(mktemp -d -p $$PWD)",
                # the parent and every part's parasitics, SDC and liberty
                # beside each other; each block's netlist with its modules
                # renamed, so two blocks' copies of one module do not meet
                "for f in $(execpath :%s/%s.v) %s; do ln -s $$PWD/$$f $$w/; done" % (
                    name,
                    parent,
                    " ".join(
                        ["$(execpath :%s/%s.%s)" % (name, p, e) for p in parts for e in ["spef", "sdc"]] +
                        ["$(execpath :%s/%s_libs.tar)" % (name, p) for p in parts],
                    ),
                ),
            ] + [
                "$(execpath %s) %s $(execpath :%s/%s.v) $$w/%s.v" % (
                    Label("//tools/headroom:sta_prefix"),
                    b,
                    name,
                    b,
                    b,
                )
                for b in blocks
            ] + [
                "ulimit -s unlimited",
                ("STA_DIR=$$w STA_PARENT=%s STA_PARTS='%s' STA_WIRES=%s HR_ENDS=%d HR_TARGET=%s " +
                 "HR_TCL=$(execpath %s) HR_OUT=$@ $(execpath %s) -no_splash -threads max " +
                 "-exit $(execpath %s)") % (
                    parent,
                    " ".join(parts.keys()),
                    wires,
                    ends,
                    target,
                    Label("//tools/odb_debug:headroom.tcl"),
                    Label("@openroad//src/sta:opensta"),
                    Label("//tools/headroom:headroom_flat.tcl"),
                ),
            ]),
            tags = tags,
            tools = [
                Label("//tools/headroom:headroom_flat.tcl"),
                Label("//tools/headroom:sta_prefix"),
                Label("//tools/odb_debug:headroom.tcl"),
                Label("@openroad//src/sta:opensta"),
            ],
            **kwargs
        )
