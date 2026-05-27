"""orfs_genrule: a genrule variant with a tools attr and select() in srcs.

Native genrule does not separate executable tools from data srcs and
does not allow select() in srcs. orfs_genrule adds both: declare
executable tools on the tools attr (cfg = "exec"), data on srcs
(caller's config), and parameterise srcs with select() where useful.

ORFS rules (orfs_run, orfs_synth, orfs_floorplan, ...) build in target
config, so leaving srcs in the caller's (target) config keeps
orfs_genrule consumers on the same action keys as orfs_run consumers
of the same pipeline.

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
