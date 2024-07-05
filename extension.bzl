"""
This module extension gathers miscellaneous files, binaries, and pdks
from a OpenROAD-flow-scripts docker image and provides rules for its
build stages.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
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
        http_archive,
        name = "com_docker_download",
        build_file_content = """
    export_files(
      ["docker"],
      visibility = ["//visibility:public"],
    )
    """,
        sha256 = "a9cede81aa3337f310132c2c920dba2edc8d29b7d97065b63ba41cf47ae1ca4f",
        strip_prefix = "docker",
        urls = ["https://download.docker.com/linux/static/stable/x86_64/docker-26.1.4.tgz"],
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
