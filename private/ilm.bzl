"""Interface-logic-model timing of a parent and its blocks, made by orfs_flow.

A flow whose `macros` include other orfs_flow's abstracts gets

    <parent>_ilm_sta          the parent timed in OpenSTA with every block's
                              interface logic in place of its abstract,
                              with each part's parasitics
    <parent>_ilm_sta_nowire   the same netlist without wires

and every flow with an abstract gets `<flow>_ilm_part`, its interface logic
model, which a parent reads. All are tagged manual.

Each block keeps its interface logic only (tools/headroom/sta_part.tcl,
STA_ILM=1): the cells from its data inputs to the first flops and from the
last flops to its outputs, every load of a net those cells drive, and the
clock tree of the flops it keeps, read at the stage its abstract was made
from (global route for an abstract made later). The parent is read whole at
global route, or at its last stage when it stops at place or cts.
tools/headroom/sta_flat.tcl links them and writes the reg2reg min period,
the worst path, the reg2reg endpoints by the class of their worst path
(tools/headroom/classify.tcl) and each class's worst path, cell by cell.
"""

load("//private:providers.bzl", "TopInfo")
load("//private:rules.bzl", "orfs_run")

_STAGES = ["synth", "floorplan", "place", "cts", "grt", "route", "final"]
_ABSTRACT_SUFFIX = "_generate_abstract"

# The suffix of a flow's interface logic model, beside its abstract.
ILM_PART = "ilm_part"

def ilm_read_stage(stop, start = "synth", squash = False):
    """The stage a flow's part is read at, or None when it has none.

    Args:
        stop: the flow's last stage: its abstract_stage or last_stage, None
            for a flow run to the end.
        start: the first stage the flow builds itself: a previous_stage key.
        squash: whether the stages after synthesis are one target, named by
            the last.

    Returns:
        "place", "cts" or "grt": the last of them the flow builds a target
        for, global route for a flow that runs past it.
    """
    stop = stop or "final"
    read = stop if _STAGES.index(stop) <= _STAGES.index("grt") else "grt"
    if read not in ["place", "cts", "grt"]:
        return None
    if _STAGES.index(read) < _STAGES.index(start):
        return None
    if squash and read != stop:
        return None
    return read

def ilm_blocks(macros):
    """The macros that are orfs_flow abstracts, each with its interface logic model.

    Args:
        macros: an orfs_flow's `macros`.

    Returns:
        [(macro, part)]: each `<flow>_generate_abstract` and its
        `<flow>_ilm_part`; a macro made otherwise is timed by its liberty.
    """
    blocks = []
    for m in macros:
        m = str(m)
        if m.endswith(_ABSTRACT_SUFFIX):
            blocks.append((m, m.removesuffix(_ABSTRACT_SUFFIX) + "_" + ILM_PART))
    return blocks

def orfs_ilm_part(name, src, stage, ilm, tags, **kwargs):
    orfs_run(
        name = name,
        src = src,
        outs = ["%s/part.%s" % (name, e) for e in ["v", "spef", "sdc"]] +
               ["%s/part_libs.tar" % name],
        script = Label("//tools/headroom:sta_part.tcl"),
        tags = tags,
        user_arguments = {
            "PART_LIBS": "$(location %s/part_libs.tar)" % name,
            "PART_SDC": "$(location %s/part.sdc)" % name,
            "PART_SPEF": "$(location %s/part.spef)" % name,
            "PART_STAGE": stage,
            "PART_V": "$(location %s/part.v)" % name,
            "STA_ILM": "1" if ilm else "0",
        },
        **kwargs
    )

def _part_files(target):
    files = {}
    for f in target[DefaultInfo].files.to_list():
        for key in ["v", "spef", "sdc", "libs.tar"]:
            if f.basename == "part." + key or f.basename == "part_" + key:
                files[key] = f
    for key in ["v", "spef", "sdc", "libs.tar"]:
        if key not in files:
            fail("%s has no part %s" % (target.label, key))
    return files

def _sh(s):
    return "'" + s.replace("'", "'\\''") + "'"

def _ilm_sta_impl(ctx):
    parts = [(ctx.attr.top, ctx.attr.parent)]
    seen = {ctx.attr.top: True}
    for macro, part in zip(ctx.attr.macros, ctx.attr.parts):
        top = macro[TopInfo].module_top
        if top in seen:
            continue
        seen[top] = True
        parts.append((top, part))
    report = ctx.actions.declare_file(ctx.attr.name + ".txt")
    paths = ctx.actions.declare_file(ctx.attr.name + "_paths.txt")
    cmd = ["set -e", 'w=$(mktemp -d -p "$PWD")']
    inputs = []
    for i, (top, part) in enumerate(parts):
        files = _part_files(part)
        inputs.extend(files.values())
        for key, ext in [("spef", ".spef"), ("sdc", ".sdc"), ("libs.tar", "_libs.tar")]:
            cmd.append('ln -s "$PWD"/%s "$w"/%s' % (_sh(files[key].path), _sh(top + ext)))
        if i == 0:
            cmd.append('ln -s "$PWD"/%s "$w"/%s' % (_sh(files["v"].path), _sh(top + ".v")))
        else:
            # each block's modules renamed <block>__<module>, so two
            # blocks' copies of one module do not meet
            cmd.append('%s %s %s "$w"/%s' % (
                _sh(ctx.executable._sta_prefix.path),
                _sh(top),
                _sh(files["v"].path),
                _sh(top + ".v"),
            ))
    cmd.append("ulimit -s unlimited")
    cmd.append(
        ('STA_DIR="$w" STA_PARENT=%s STA_PARTS=%s STA_WIRES=%s STA_CLASSIFY=%s ' +
         "STA_OUT=%s STA_PATHS=%s %s -no_splash -threads max -exit %s") % (
            _sh(ctx.attr.top),
            _sh(" ".join([t for t, _ in parts])),
            "1" if ctx.attr.wires else "0",
            _sh(ctx.file._classify.path),
            _sh(report.path),
            _sh(paths.path),
            _sh(ctx.executable._opensta.path),
            _sh(ctx.file._sta_flat.path),
        ),
    )
    cmd.append('rm -rf "$w"')
    ctx.actions.run_shell(
        command = "\n".join(cmd),
        inputs = inputs + [ctx.file._classify, ctx.file._sta_flat],
        outputs = [report, paths],
        tools = [ctx.attr._opensta[DefaultInfo].files_to_run, ctx.attr._sta_prefix[DefaultInfo].files_to_run],
        mnemonic = "IlmSta",
        progress_message = "Timing %s with its blocks' interface logic" % ctx.attr.top,
    )
    return [DefaultInfo(files = depset([report, paths]))]

orfs_ilm_sta = rule(
    implementation = _ilm_sta_impl,
    doc = "A parent's part timed with its blocks' interface logic models " +
          "(tools/headroom/sta_flat.tcl): `<name>.txt`, the reg2reg min " +
          "period, worst path and endpoints by class, and " +
          "`<name>_paths.txt`, each class's worst path.",
    attrs = {
        "macros": attr.label_list(
            doc = "The blocks' abstracts, for their module names.",
            providers = [TopInfo],
        ),
        "parent": attr.label(
            doc = "The parent's part, read whole (sta_part.tcl).",
            mandatory = True,
        ),
        "parts": attr.label_list(
            doc = "Each of `macros`' part, in the same order.",
        ),
        "top": attr.string(
            doc = "The parent's module.",
            mandatory = True,
        ),
        "wires": attr.bool(
            doc = "Read every part's parasitics; False times the logic alone.",
            default = True,
        ),
        "_classify": attr.label(
            default = Label("//tools/headroom:classify.tcl"),
            allow_single_file = True,
        ),
        "_opensta": attr.label(
            default = Label("@openroad//openroad/sta:opensta"),
            executable = True,
            cfg = "exec",
        ),
        "_sta_flat": attr.label(
            default = Label("//tools/headroom:sta_flat.tcl"),
            allow_single_file = True,
        ),
        "_sta_prefix": attr.label(
            default = Label("//tools/headroom:sta_prefix"),
            executable = True,
            cfg = "exec",
        ),
    },
)

def orfs_ilm_targets(
        step_name,
        top,
        macros,
        abstract_stage,
        last_stage,
        previous_stage,
        squash,
        tags,
        **kwargs):
    """A flow's interface-logic-model targets (module docstring).

    Args:
        step_name: the flow's stage target name for a stage, a function.
        top: the flow's top module.
        macros: the flow's macros.
        abstract_stage: the flow's abstract_stage.
        last_stage: the flow's last_stage.
        previous_stage: the flow's previous_stage.
        squash: the flow's squash.
        tags: the flow's tags; the targets are also manual.
        **kwargs: visibility and openroad, passed on.
    """
    tags = tags + ([] if "manual" in tags else ["manual"])
    start = previous_stage.keys()[0] if previous_stage else "synth"
    if abstract_stage or not last_stage:
        stage = ilm_read_stage(abstract_stage, start, squash)
        if stage:
            orfs_ilm_part(step_name(ILM_PART), ":" + step_name(stage), stage, True, tags, **kwargs)
    blocks = ilm_blocks(macros)
    stage = ilm_read_stage(abstract_stage or last_stage, start, squash)
    if not blocks or not stage:
        return
    parent = step_name("ilm_sta_parent")
    orfs_ilm_part(parent, ":" + step_name(stage), stage, False, tags, **kwargs)
    for suffix, wires in [("", True), ("_nowire", False)]:
        orfs_ilm_sta(
            name = step_name("ilm_sta") + suffix,
            top = top,
            parent = ":" + parent,
            macros = [m for m, _ in blocks],
            parts = [p for _, p in blocks],
            wires = wires,
            tags = tags,
            visibility = kwargs.get("visibility"),
        )
