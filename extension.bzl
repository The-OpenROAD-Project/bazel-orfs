"""
This module extension provides rules for OpenROAD-flow-scripts build stages.

By default, tools are real implementations: OpenROAD and OpenSTA from
the @openroad module, yosys from the Bazel Central Registry (@yosys),
GNU Make from source (@gnumake).  Only klayout uses a mock (mock-klayout)
since GDS generation is end-of-line and most users don't need it.

Users override individual tools via orfs.default() tag attributes.

A stub @docker_orfs repo with no-op executables is always created to
satisfy any residual label references in attrs.bzl.
"""

load("//:config.bzl", "global_config")
load("//:gnumake.bzl", "gnumake")
load("//:load_json_file.bzl", "load_json_file")
load("//:stub.bzl", "stub_docker_orfs")

_default_tag = tag_class(
    attrs = {
        "image": attr.string(
            mandatory = False,
            doc = "Deprecated: Docker image is no longer used. Accepted for backward compatibility.",
        ),
        "sha256": attr.string(
            mandatory = False,
            doc = "Deprecated: Docker image is no longer used. Accepted for backward compatibility.",
        ),
        "klayout": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@mock-klayout//src/bin:klayout"),
        ),
        "make": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@gnumake//:make"),
        ),
        "makefile": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:makefile"),
        ),
        "makefile_yosys": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:makefile_yosys"),
        ),
        "openroad": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@openroad//:openroad"),
        ),
        "opensta": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@openroad//src/sta:opensta"),
        ),
        "pdk": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:asap7"),
        ),
        "yosys": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@yosys//:yosys"),
        ),
        "variables_yaml": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:scripts/variables.yaml"),
        ),
        "yosys_abc": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@yosys//:yosys_abc"),
        ),
        "yosys_share": attr.label(
            mandatory = False,
            default = Label("@yosys//:yosys_share"),
        ),
    },
)

def _orfs_repositories_impl(module_ctx):
    # Stub repo with no-op executables for residual @docker_orfs references
    stub_docker_orfs(name = "docker_orfs")

    # GNU Make built from source
    gnumake(name = "gnumake")

    for default in module_ctx.modules[0].tags.default:
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
            yosys_share = default.yosys_share,
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
