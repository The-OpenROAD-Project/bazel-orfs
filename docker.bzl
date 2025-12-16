"""Repository rules for exporting file trees from docker images"""

load("@bazel_tools//tools/build_defs/repo:utils.bzl", "patch")

def _impl(repository_ctx):
    if repository_ctx.attr.sha256 != "":
        image = "{}@sha256:{}".format(
            repository_ctx.attr.image,
            repository_ctx.attr.sha256,
        )
    else:
        image = repository_ctx.attr.image

    python_name = "python3"
    python = repository_ctx.which(python_name)
    if not python:
        fail("Failed to find {}.".format(python_name))
    docker_name = "docker"
    docker = repository_ctx.which(docker_name)
    if not docker:
        fail("Failed to find {}.".format(docker_name))

    if repository_ctx.attr.sha256 == "":
        inspect = repository_ctx.execute(
            [
                docker,
                "inspect",
                "--type=image",
                image,
            ],
        )
        if inspect.return_code != 0:
            fail(
                "Local image {} does not exist: {}".format(image, inspect.stderr),
                inspect.return_code,
            )
        repository_ctx.report_progress(
            "Using local {}.".format(repository_ctx.attr.image),
        )
    else:
        pull = repository_ctx.execute(
            [
                docker,
                "pull",
                image,
            ],
        )
        if pull.return_code != 0:
            fail(
                "Image {} cannot be pulled: {}".format(image, pull.stderr),
                pull.return_code,
            )
        repository_ctx.report_progress("Pulled {}.".format(repository_ctx.attr.image))

    created = repository_ctx.execute(
        [
            docker,
            "create",
            image,
        ],
    )
    if created.return_code != 0:
        fail(
            "Failed to create stopped container: {}".format(created.stderr),
            created.return_code,
        )
    container_id = created.stdout.strip()
    cp = repository_ctx.execute(
        [
            docker,
            "cp",
            "{}:/".format(container_id),
            ".",
        ],
    )
    remove = repository_ctx.execute(
        [
            docker,
            "rm",
            container_id,
        ],
    )
    if remove.return_code != 0:
        print(
            "Container {} has not been removed".format(container_id),
        )  # buildifier: disable=print
    if cp.return_code != 0:
        fail("Failed to copy image content: {}".format(cp.stderr), cp.return_code)

    repository_ctx.report_progress("Extracted {}.".format(repository_ctx.attr.image))

    patcher = repository_ctx.path(repository_ctx.attr._patcher).realpath
    patchelf = repository_ctx.path(repository_ctx.attr._patchelf).realpath
    patcher_result = repository_ctx.execute(
        [
            patcher,
            "--patchelf",
            patchelf,
            repository_ctx.path("."),
        ],
    )
    if patcher_result.return_code != 0:
        fail(
            "Failed to run {}:".format(repository_ctx.attr._patcher),
            patcher_result.stderr,
        )

    repository_ctx.report_progress(
        "Fixed `RUNPATH`s for {}.".format(repository_ctx.attr.image),
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
