load("@bazel_tools//tools/build_defs/repo:utils.bzl", "patch")

def _impl(repository_ctx):
    docker_path = repository_ctx.path(repository_ctx.attr._docker).realpath
    image_archive = "data.tar"
    build_result = repository_ctx.execute(
        [
            docker_path,
            "build",
            "--file",
            repository_ctx.attr.docker_file,
            "--output",
            "type=tar,dest={image_archive}".format(image_archive = image_archive),
            ".",
        ],
    )
    if build_result.return_code != 0:
        fail(
            "Failed to build {docker}:".format(docker = repository_ctx.attr.docker_file),
            build_result.stderr,
        )

    check_result = repository_ctx.execute([
        "sha256sum",
        image_archive,
    ])
    if check_result.return_code != 0 or not check_result.stdout.startswith(repository_ctx.attr.sha256):
        fail(
            "Checksum error in {repo}, expected {sha256}, got:".format(repo = repository_ctx.attr.name, sha256 = repository_ctx.attr.sha256),
            check_result.stdout,
        )

    for src, dest in repository_ctx.attr.strip_prefixes.items():
        repository_ctx.extract(archive = image_archive, stripPrefix = src, output = dest)

    if not repository_ctx.attr.strip_prefixes:
        repository_ctx.extract(archive = image_archive)

    repository_ctx.symlink(repository_ctx.attr.build_file, "BUILD")
    patch(repository_ctx)

docker_pkg = repository_rule(
    implementation = _impl,
    attrs = {
        "build_file": attr.label(mandatory = True),
        "docker_file": attr.label(mandatory = True),
        "sha256": attr.string(mandatory = True),
        "strip_prefixes": attr.string_dict(),
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
    },
)
