load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("@bazel_tools//tools/build_defs/repo:utils.bzl", "maybe")
load("//:docker.bzl", "docker_pkg")

_default_tag = tag_class(
    attrs = {
        "image": attr.string(
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

_INFO = {
    "openroad/orfs:f8d87d5bf1b2fa9a7e8724d1586a674180b31ae9": {
        "sha256": "7c3c2ebc85c83ca71c39012399d8b2bf0113b3409cfcd3cf828b2d8e9b0eb077",
        "build_file": ":docker.BUILD.bazel",
        "timeout": 3600,
        "strip_prefixes": {
            "OpenROAD-flow-scripts/flow": "flow/",
            "OpenROAD-flow-scripts/tools/install/OpenROAD/bin/": "bin/",
            "OpenROAD-flow-scripts/tools/install/yosys/bin/": "bin/",
            "OpenROAD-flow-scripts/tools/install/yosys/share/yosys/": "share/",
            "opt/or-tools/lib/": "lib/",
            "usr/lib/x86_64-linux-gnu/": "lib/",
            "usr/lib/klayout/": "lib/klayout/",
            "usr/lib/tcltk/x86_64-linux-gnu/tclreadline2.3.8/": "tcl/",
            "usr/bin/": "bin/",
        },
        "patches": [
            ":Makefile.patch",
        ],
    },
}

def _orfs_repositories_impl(module_ctx):
    _orfs_dependencies()

    for default in module_ctx.modules[0].tags.default:
        docker_pkg(
            name = "docker_orfs",
            image = default.image,
            **_INFO[default.image]
        )

orfs_repositories = module_extension(
    implementation = _orfs_repositories_impl,
    tag_classes = {
        "default": _default_tag,
    },
)
