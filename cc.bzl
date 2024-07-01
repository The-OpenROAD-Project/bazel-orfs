def _cc_patch(ctx, input):
    out = ctx.actions.declare_file(ctx.label.name)

    runfiles = ctx.runfiles(files = [])
    for dep in ctx.attr.deps:
        for link in dep[CcInfo].linking_context.linker_inputs.to_list():
            runfiles = runfiles.merge(ctx.runfiles([lib.dynamic_library for lib in link.libraries]))

    for dep in runfiles.files.to_list():
        if ctx.label.package != dep.owner.package or ctx.label.workspace_name != dep.owner.workspace_name or dep.is_source:
            link = ctx.actions.declare_file(dep.basename)
            ctx.actions.symlink(output = link, target_file = dep)
            runfiles = runfiles.merge(ctx.runfiles([link]))

    ctx.actions.run(
        arguments = ["--set-rpath", "$ORIGIN", "--output", out.path, input.path],
        executable = ctx.executable._patchelf,
        inputs = [input],
        outputs = [out],
    )

    return [DefaultInfo(
        executable = out,
        runfiles = runfiles.merge(ctx.runfiles(files = ctx.files.data)),
        files = depset([out]),
    )]

def _cc_import_binary_impl(ctx):
    return _cc_patch(ctx, ctx.executable.executable)

def _cc_import_library_impl(ctx):
    [default] = _cc_patch(ctx, ctx.file.shared_library)
    return [DefaultInfo(
        runfiles = default.default_runfiles.merge(ctx.runfiles(transitive_files = default.files)),
        files = default.files,
    )]

cc_import_binary = rule(
    implementation = _cc_import_binary_impl,
    attrs = {
        "executable": attr.label(
            doc = "Executable to import.",
            mandatory = True,
            executable = True,
            allow_files = True,
            cfg = "exec",
        ),
        "data": attr.label_list(allow_files = True),
        "deps": attr.label_list(
            allow_rules = [
                "cc_library",
                "cc_proto_library",
                "cc_import",
            ],
            flags = ["SKIP_ANALYSIS_TIME_FILETYPE_CHECK"],
            providers = [CcInfo],
        ),
        "_patchelf": attr.label(
            doc = "Modify ELF files.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@patchelf//:patchelf"),
        ),
    },
    provides = [DefaultInfo],
    executable = True,
)

cc_import_library = rule(
    implementation = _cc_import_library_impl,
    attrs = {
        "shared_library": attr.label(
            doc = "Executable to import.",
            mandatory = True,
            allow_single_file = True,
            cfg = "exec",
        ),
        "data": attr.label_list(allow_files = True),
        "deps": attr.label_list(
            allow_rules = [
                "cc_library",
                "objc_library",
                "cc_proto_library",
                "cc_import",
            ],
            flags = ["SKIP_ANALYSIS_TIME_FILETYPE_CHECK"],
            providers = [CcInfo],
        ),
        "_patchelf": attr.label(
            doc = "Modify ELF files.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@patchelf//:patchelf"),
        ),
    },
    provides = [DefaultInfo],
)
