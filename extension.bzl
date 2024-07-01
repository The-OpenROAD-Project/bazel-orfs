load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("//:docker.bzl", "docker_pkg")

def _orfs_repositories():
    http_archive(
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
    docker_pkg(
        name = "docker_orfs",
        timeout = 3600,
        build_file = ":docker.BUILD.bazel",
        docker_file = ":Dockerfile",
        sha256 = "70ea7eac09277b429e4cbac1668f29a795656b45993684425d8de0fd1977b65b",
        strip_prefixes = {
            "OpenROAD-flow-scripts/flow": "flow/",
            "OpenROAD-flow-scripts/tools/install/OpenROAD/bin/": "bin/",
            "OpenROAD-flow-scripts/tools/install/yosys/bin/": "bin/",
            "OpenROAD-flow-scripts/tools/install/yosys/share/yosys/": "share/",
            "OpenROAD-flow-scripts/dependencies/lib/": "lib/",
            "usr/lib/x86_64-linux-gnu/": "lib/",
            "usr/lib/klayout/": "lib/klayout/",
            "usr/lib/tcltk/x86_64-linux-gnu/tclreadline2.3.8/": "tcl/",
        },
        patches = [
            ":Makefile.patch",
        ],
    )

def _orfs_repositories_impl(module_ctx):
    _orfs_repositories()

orfs_repositories = module_extension(
    implementation = _orfs_repositories_impl,
)
