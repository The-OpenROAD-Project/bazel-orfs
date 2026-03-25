"""Repository rules for extracting file trees from OCI container images"""

load("@bazel_tools//tools/build_defs/repo:utils.bzl", "patch")

def _impl(repository_ctx):
    python = repository_ctx.path(repository_ctx.attr._python).realpath
    oci_extract = repository_ctx.path(repository_ctx.attr._oci_extract).realpath

    extract_args = [
        python,
        oci_extract,
        "extract",
        "--image",
        repository_ctx.attr.image,
        "--digest",
        repository_ctx.attr.sha256,
        "--output",
        str(repository_ctx.path(".")),
    ]
    extract_result = repository_ctx.execute(extract_args)
    if extract_result.return_code != 0:
        fail(
            "Failed to extract {}: {}".format(
                repository_ctx.attr.image,
                extract_result.stderr,
            ),
        )

    repository_ctx.report_progress("Extracted {}.".format(repository_ctx.attr.image))

    patcher = repository_ctx.path(repository_ctx.attr._patcher).realpath
    patcher_result = repository_ctx.execute(
        [
            python,
            patcher,
            repository_ctx.path("."),
        ],
    )
    if patcher_result.return_code != 0:
        fail(
            "Failed to run {}:".format(repository_ctx.attr._patcher),
            patcher_result.stderr,
        )

    repository_ctx.report_progress(
        "Created ld-linux wrappers for {}.".format(repository_ctx.attr.image),
    )

    repository_ctx.symlink(repository_ctx.attr.build_file, "BUILD")
    patch(repository_ctx)

docker_pkg = repository_rule(
    implementation = _impl,
    attrs = {
        "build_file": attr.label(mandatory = True),
        "image": attr.string(mandatory = True),
        "patch_args": attr.string_list(default = ["-p0"]),
        "patch_cmds": attr.string_list(default = []),
        "patch_cmds_win": attr.string_list(default = []),
        "patch_tool": attr.string(default = ""),
        "patches": attr.label_list(default = []),
        "sha256": attr.string(mandatory = False),
        "timeout": attr.int(default = 600),
        "_oci_extract": attr.label(
            doc = "OCI image extraction script.",
            default = Label("//:oci_extract.py"),
            allow_single_file = True,
        ),
        "_python": attr.label(
            doc = "Hermetic Python interpreter.",
            default = Label("@python_3_13_host//:python"),
            executable = True,
            cfg = "exec",
        ),
        "_patcher": attr.label(
            doc = "Python script to create ld-linux wrapper scripts.",
            default = Label("//:patcher.py"),
            allow_single_file = True,
        ),
    },
)
