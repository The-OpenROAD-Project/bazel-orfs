"""
This module extension gathers miscellaneous files, binaries, and pdks
from a OpenROAD-flow-scripts docker image and provides rules for its
build stages.

When no image is provided, a stub @docker_orfs repo is created with
empty filegroups, enabling zero-docker mode where all tools come from
local sources.
"""

load("//:config.bzl", "global_config")
load("//:docker.bzl", "docker_pkg")
load("//:load_json_file.bzl", "load_json_file")
load("//:stub.bzl", "stub_docker_orfs")

_default_tag = tag_class(
    attrs = {
        "image": attr.string(
            mandatory = False,
            default = "",
        ),
        "klayout": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:klayout"),
        ),
        "make": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:make"),
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
        "opensta": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:sta"),
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
        "variables_yaml": attr.label(
            mandatory = False,
            default = Label("@docker_orfs//:OpenROAD-flow-scripts/flow/scripts/variables.yaml"),
        ),
        "yosys_abc": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:yosys-abc"),
        ),
    },
)

def _orfs_repositories_impl(module_ctx):
    for default in module_ctx.modules[0].tags.default:
        if default.image:
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
        else:
            # Zero-docker mode: create stub repo with empty filegroups
            stub_docker_orfs(name = "docker_orfs")

        global_config(
            name = "config",
            klayout = default.klayout,
            make = default.make,
            makefile = default.makefile,
            makefile_yosys = default.makefile_yosys,
            openroad = default.openroad,
            opensta = default.opensta,
            pdk = default.pdk,
            yosys = default.yosys,
            yosys_abc = default.yosys_abc,
        )

        load_json_file(
            name = "orfs_variable_metadata",
            src = default.variables_yaml,
        )

orfs_repositories = module_extension(
    implementation = _orfs_repositories_impl,
    tag_classes = {
        "default": _default_tag,
    },
)
