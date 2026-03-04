"""orfs_genrule: a genrule variant where srcs use cfg = "exec".

Native genrule forces srcs into the target configuration. When srcs
come from ORFS rules (which build in the exec configuration), this
causes the entire ORFS pipeline to be rebuilt in a second configuration.

orfs_genrule avoids that by keeping srcs in exec configuration,
matching where ORFS outputs already live.

Supports the same cmd substitutions as native genrule:
  $(location label), $(locations label),
  $(execpath label), $(execpaths label),
  $(SRCS), $(OUTS), $<, $@, $$
"""

def _orfs_genrule_impl(ctx):
    outs = ctx.outputs.outs

    # Expand $(location ...), $(execpath ...), etc.
    targets = ctx.attr.srcs + ctx.attr.tools
    cmd = ctx.expand_location(ctx.attr.cmd, targets)

    # Substitute make-style variables
    srcs_paths = " ".join([f.path for f in ctx.files.srcs])
    outs_paths = " ".join([f.path for f in outs])
    first_src = ctx.files.srcs[0].path if ctx.files.srcs else ""
    first_out = outs[0].path if outs else ""

    _PLACEHOLDER = "ORFS_GENRULE_DOLLAR_LITERAL"
    cmd = cmd.replace("$$", _PLACEHOLDER)
    cmd = cmd.replace("$(SRCS)", srcs_paths)
    cmd = cmd.replace("$(OUTS)", outs_paths)
    cmd = cmd.replace("$<", first_src)
    cmd = cmd.replace("$@", first_out)
    cmd = cmd.replace("$(RULEDIR)", outs[0].dirname if outs else "")
    cmd = cmd.replace(_PLACEHOLDER, "$")

    # Pass FilesToRunProvider objects so that run_shell creates the
    # .runfiles tree in the sandbox for py_binary tools.
    tools_list = [
        tool[DefaultInfo].files_to_run
        for tool in ctx.attr.tools
        if tool[DefaultInfo].files_to_run
    ]

    ctx.actions.run_shell(
        command = cmd,
        inputs = ctx.files.srcs,
        outputs = outs,
        tools = tools_list,
        mnemonic = "OrfsGenrule",
        progress_message = "OrfsGenrule %s" % ctx.label,
    )

    return [DefaultInfo(files = depset(outs))]

orfs_genrule = rule(
    implementation = _orfs_genrule_impl,
    attrs = {
        "cmd": attr.string(mandatory = True),
        "outs": attr.output_list(mandatory = True),
        "srcs": attr.label_list(
            cfg = "exec",
            allow_files = True,
            default = [],
        ),
        "tools": attr.label_list(
            cfg = "exec",
            allow_files = True,
            default = [],
        ),
    },
)
