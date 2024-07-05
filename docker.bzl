"""Repository rules for exporting file trees from docker images"""

load("@bazel_tools//tools/build_defs/repo:utils.bzl", "patch")

def _impl(repository_ctx):
    docker_path = repository_ctx.path(repository_ctx.attr._docker).realpath
    image_archive = repository_ctx.path("data.tar")
    dockerfile = repository_ctx.path("Dockerfile")

    repository_ctx.file(dockerfile, content = "FROM {}@sha256:{}".format(repository_ctx.attr.image, repository_ctx.attr.sha256))
    build_result = repository_ctx.execute(
        [
            docker_path,
            "build",
            "--file",
            dockerfile,
            "--output",
            "type=tar,dest={}".format(image_archive),
            ".",
        ],
    )
    if build_result.return_code != 0:
        fail("Failed to build {}:".format(repository_ctx.attr.image), build_result.stderr)

    repository_ctx.report_progress("Built {}.".format(repository_ctx.attr.image))

    repository_ctx.extract(archive = image_archive)
    repository_ctx.delete(image_archive)
    repository_ctx.report_progress("Extracted {}.".format(repository_ctx.attr.image))

    python_name = "python3"
    python = repository_ctx.which(python_name)
    if not python:
        fail("Failed to find {}.".format(python_name))

    patcher = repository_ctx.path(repository_ctx.attr._patcher).realpath
    patchelf = repository_ctx.path(repository_ctx.attr._patchelf).realpath
    patcher_result = repository_ctx.execute(
        [
            patcher,
            "--patchelf",
            patchelf,
            repository_ctx.path("."),
        ],
        quiet = False,
    )
    if patcher_result.return_code != 0:
        fail("Failed to run {}:".format(repository_ctx.attr._patcher), build_result.stderr)

    repository_ctx.report_progress("Fixed `RUNPATH`s for {}.".format(repository_ctx.attr.image))

    repository_ctx.symlink(repository_ctx.attr.build_file, "BUILD")
    patch(repository_ctx)

docker_pkg = repository_rule(
    implementation = _impl,
    attrs = {
        "build_file": attr.label(mandatory = True),
        "image": attr.string(mandatory = True),
        "sha256": attr.string(mandatory = True),
        "patches": attr.label_list(default = []),
        "patch_tool": attr.string(default = ""),
        "patch_args": attr.string_list(default = ["-p0"]),
        "patch_cmds": attr.string_list(default = []),
        "patch_cmds_win": attr.string_list(default = []),
        "timeout": attr.int(default = 600),
        "_docker": attr.label(
            doc = "Docker command line interface.",
            default = Label("@com_docker_download//:docker"),
            executable = True,
            cfg = "exec",
        ),
        "_patchelf": attr.label(
            doc = "Patchelf binary.",
            default = Label("@com_github_nixos_patchelf_download//:bin/patchelf"),
            executable = True,
            cfg = "exec",
        ),
        "_patcher": attr.label(
            doc = "Python script to remap `RUNPATH`s.",
            default = Label("//:patcher.py"),
            executable = True,
            cfg = "exec",
        ),
    },
)
