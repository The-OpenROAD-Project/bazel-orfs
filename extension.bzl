"""
This module extension provides rules for OpenROAD-flow-scripts build stages.

Tools are built from source: OpenROAD and OpenSTA from the @openroad
module, yosys from the Bazel Central Registry (@yosys), ABC from BCR
(@abc), and GNU Make from source (@gnumake).  Only klayout uses a mock
(mock-klayout) since GDS generation is end-of-line and most users
don't need it.

Users override individual tools via orfs.default() tag attributes.
"""

load("//:config.bzl", "global_config")
load("//:gnumake.bzl", "gnumake")
load("//:load_json_file.bzl", "load_json_file")
load("//:mock_klayout.bzl", "mock_klayout")

_default_tag = tag_class(
    attrs = {
        "klayout": attr.label(
            mandatory = False,
            cfg = "exec",
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
            default = Label("@abc//:abc_bin"),
        ),
        "yosys_share": attr.label(
            mandatory = False,
            default = Label("@yosys//:yosys_share"),
        ),
    },
)

def _orfs_repositories_impl(module_ctx):
    # GNU Make built from source
    gnumake(name = "gnumake")

    # Mock klayout that produces dummy GDS files — used as default
    # when no real klayout is provided by the consumer.
    mock_klayout(name = "mock_klayout")

    for default in module_ctx.modules[0].tags.default:
        global_config(
            name = "config",
            klayout = default.klayout if default.klayout else "@mock_klayout//:klayout",
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
