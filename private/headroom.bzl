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
`<name>_nowire.json` the same at zero wire: the period, the one-flop-loop
floor of the logic alone and useful skew on it, and `<name>_classes.txt`
every reg2reg endpoint by where its worst path runs (classify.tcl): within
the parent or a block, from one part to another, or through a block it
neither starts nor ends in, the in2out arc surgery takes apart. The
odb-debug daemon's
`headroom` tool asks the same of one stage alone, a block being its
abstract. When to ask and how to read the answer:
.claude/skills/repair-headroom/SKILL.md.

A whole core stitched this way needs memory: plan for the parent's own
stage's peak and more.
"""

load("//private:rules.bzl", "orfs_run")

def orfs_headroom(name, parent, parent_stage, blocks, ends = 0, target = 0, period_only = False, stage = "grt", reports = {}, tags = ["manual"], **kwargs):
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
        stage: Which stage the parts are read at, "grt" by default;
            "place" and "cts" with placement parasitics, "floorplan" with
            none, for `<name>_nowire.json` alone. `parent_stage` and the
            blocks' stages name that stage's targets.
        period_only: Measure the stitched reg2reg period only, none of
            the floors and moves after it: a design's period across its
            parent and blocks, cheaply.
        reports: {suffix: a Tcl script}, a design's own reports on the
            stitched design: each script defines `hr_report where parent`,
            `where` every block instance and its block, and returns lines
            for `<name><suffix>.txt`.
        tags: Tags of every target; manual by default, as the stitched
            view of a large design is no CI job.
        **kwargs: Passed to every target, e.g. `visibility`.
    """
    read_stage = stage
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
                "PART_STAGE": read_stage,
                "PART_V": "$(location %s/%s.v)" % (name, part),
                "STA_ILM": "0",
            },
            **kwargs
        )
    files = ["%s/%s.%s" % (name, p, e) for p in parts for e in ["v", "spef", "sdc"]] + \
            ["%s/%s_libs.tar" % (name, p) for p in parts]
    for suffix, wires, ext, classes, report in [
        ("", "1", "json", "", None),
        ("_nowire", "0", "json", "", None),
        ("_classes", "1", "txt", "$(execpath %s)" % Label("//tools/headroom:classify.tcl"), None),
    ] + [(suffix, "1", "txt", "", script) for suffix, script in reports.items()]:
        native.genrule(
            name = name + suffix,
            srcs = [":" + f for f in files],
            outs = [name + suffix + "." + ext],
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
                ("STA_DIR=$$w STA_PARENT=%s STA_PARTS='%s' STA_WIRES=%s HR_ENDS=%d HR_TARGET=%s HR_PERIOD_ONLY=%d " +
                 "HR_CLASSES='%s' HR_REPORT='%s' HR_TCL=$(execpath %s) HR_OUT=$@ $(execpath %s) -no_splash " +
                 "-threads max -exit $(execpath %s)") % (
                    parent,
                    " ".join(parts.keys()),
                    wires,
                    ends,
                    target,
                    1 if period_only else 0,
                    classes,
                    "$(execpath %s)" % report if report else "",
                    Label("//tools/odb_debug:headroom.tcl"),
                    Label("@openroad//src/sta:opensta"),
                    Label("//tools/headroom:headroom_flat.tcl"),
                ),
            ]),
            tags = tags,
            tools = [
                Label("//tools/headroom:classify.tcl"),
                Label("//tools/headroom:headroom_flat.tcl"),
                Label("//tools/headroom:sta_prefix"),
                Label("//tools/odb_debug:headroom.tcl"),
                Label("@openroad//src/sta:opensta"),
            ] + ([report] if report else []),
            **kwargs
        )
