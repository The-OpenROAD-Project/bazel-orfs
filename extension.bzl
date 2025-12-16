"""
This module extension gathers miscellaneous files, binaries, and pdks
from a OpenROAD-flow-scripts docker image and provides rules for its
build stages.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("@bazel_tools//tools/build_defs/repo:utils.bzl", "maybe")
load("//:config.bzl", "global_config")
load("//:docker.bzl", "docker_pkg")

_default_tag = tag_class(
    attrs = {
        "image": attr.string(
            mandatory = True,
        ),
        "makefile": attr.label(
            mandatory = False,
            default = Label("@docker_orfs//:makefile"),
        ),
        "makefile_yosys": attr.label(
            mandatory = False,
            default = Label("@docker_orfs//:makefile_yosys"),
        ),
        "openroad": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:openroad"),
        ),
        "pdk": attr.label(
            mandatory = False,
            default = Label("@docker_orfs//:asap7"),
        ),
        "sha256": attr.string(
            mandatory = False,
        ),
        "yosys": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:yosys"),
        ),
        "yosys_abc": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:yosys-abc"),
        ),
    },
)

def _orfs_dependencies():
    maybe(
        http_archive,
        name = "com_github_nixos_patchelf_download",
        build_file_content = """
    export_files(
      ["bin/patchelf"],
      visibility = ["//visibility:public"],
    )
    """,
        sha256 = "ce84f2447fb7a8679e58bc54a20dc2b01b37b5802e12c57eece772a6f14bf3f0",
        urls = [
            "https://github.com/NixOS/patchelf/releases/download/0.18.0/patchelf-0.18.0-x86_64.tar.gz",
        ],
    )

def _orfs_repositories_impl(module_ctx):
    _orfs_dependencies()

    for default in module_ctx.modules[0].tags.default:
        docker_pkg(
            name = "docker_orfs",
            image = default.image,
            sha256 = default.sha256,
            build_file = ":docker.BUILD.bazel",
            timeout = 3600,
            patch_cmds = [
                "find . -name BUILD.bazel -delete",
            ],
            # This is normally an empty patch, but is useful to
            # apply patches while waiting for some pull request to land
            # in the official ORFS docker image:
            #
            # git diff -u origin/master HEAD > orfs-patch.txt
            patches = [
                # "//:orfs-patch.txt",
            ],
            patch_args = ["-p1", "-d", "OpenROAD-flow-scripts"],
        )
        global_config(
            name = "config",
            makefile = default.makefile,
            pdk = default.pdk,
            makefile_yosys = default.makefile_yosys,
            openroad = default.openroad,
            yosys = default.yosys,
            yosys_abc = default.yosys_abc,
        )

orfs_repositories = module_extension(
    implementation = _orfs_repositories_impl,
    tag_classes = {
        "default": _default_tag,
    },
)
