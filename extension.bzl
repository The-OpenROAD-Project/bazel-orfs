"""
This module extension gathers miscellaneous files, binaries, and pdks
from a OpenROAD-flow-scripts docker image and provides rules for its
build stages.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive", "http_file")
load("@bazel_tools//tools/build_defs/repo:utils.bzl", "maybe")
load("//:docker.bzl", "docker_pkg")

_default_tag = tag_class(
    attrs = {
        "image": attr.string(
            mandatory = True,
        ),
        "sha256": attr.string(
            mandatory = True,
        ),
    },
)

def _orfs_dependencies():
    maybe(
        http_file,
        name = "com_github_docker_buildx_file",
        executable = True,
        sha256 = "8d486f0088b7407a90ad675525ba4a17d0a537741b9b33fe3391a88cafa2dd0b",
        urls = ["https://github.com/docker/buildx/releases/download/v0.15.1/buildx-v0.15.1.linux-amd64"],
    )

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
        urls = ["https://github.com/NixOS/patchelf/releases/download/0.18.0/patchelf-0.18.0-x86_64.tar.gz"],
    )

_INFO = {
    "openroad/orfs:3b01a139cce34b01bad3c25526d7fa718aa5ce84": {
        "build_file": ":docker.BUILD.bazel",
        "timeout": 3600,
        "patches": [
            ":Makefile.patch",
            ":BUILD-0.patch",
            ":BUILD-1.patch",
            ":BUILD-2.patch",
            ":BUILD-3.patch",
            ":BUILD-4.patch",
            ":BUILD-5.patch",
        ],
    },
}

def _orfs_repositories_impl(module_ctx):
    _orfs_dependencies()

    for default in module_ctx.modules[0].tags.default:
        docker_pkg(
            name = "docker_orfs",
            image = default.image,
            sha256 = default.sha256,
            **_INFO[default.image]
        )

orfs_repositories = module_extension(
    implementation = _orfs_repositories_impl,
    tag_classes = {
        "default": _default_tag,
    },
)
