"""Pinning of artifacts"""

def _serialize_file(file):
    return "@".join(
        [
            file.path,
            file.root.path,
            file.owner.workspace_root,
        ],
    )

def _serialize(target):
    if len(target.files.to_list()) == 0:
        fail("Target {} has no files to pin".format(target.label))

    return repr(
        ",".join(
            [
                str(target.label),
                target.label.workspace_root,
                ":".join([_serialize_file(file) for file in target.files.to_list()]),
            ],
        ),
    )

def _pin_data_impl(ctx):
    exe = ctx.actions.declare_file(ctx.attr.name + ".sh")
    ctx.actions.expand_template(
        substitutions = {
            '"$@"': " ".join([_serialize(target) for target in ctx.attr.srcs]),
            "${BUCKET}": ctx.attr.bucket,
            "${LOCK}": ctx.attr.artifacts_lock,
            "${PACKAGE}": ctx.label.package,
            "${PINNER}": ctx.file._pinner.short_path,
        },
        template = ctx.file._pin_template,
        output = exe,
    )
    return [
        DefaultInfo(
            executable = exe,
            files = depset([exe]),
            runfiles = ctx.runfiles(ctx.files._pinner + ctx.files.srcs),
        ),
    ]

pin_data = rule(
    implementation = _pin_data_impl,
    provides = [DefaultInfo, OutputGroupInfo],
    attrs = {
        "artifacts_lock": attr.string(mandatory = True),
        "bucket": attr.string(mandatory = True),
        "srcs": attr.label_list(
            allow_files = True,
            default = [],
        ),
        "_pin_template": attr.label(
            default = "@bazel-orfs//tools/pin:pin.sh.tpl",
            allow_single_file = True,
        ),
        "_pinner": attr.label(
            default = "@bazel-orfs//tools/pin:pin.py",
            allow_single_file = True,
        ),
    },
    executable = True,
)
