"""
This module extension provides rules for OpenROAD-flow-scripts build stages.

By default, tools are real implementations: OpenROAD and OpenSTA from
the @openroad module, yosys+slang built from source (@yosys repo created
by this extension), GNU Make from source (@gnumake).  Only klayout uses
a mock (mock-klayout) since GDS generation is end-of-line and most users
don't need it.

Users override individual tools via orfs.default() tag attributes.

A stub @docker_orfs repo with no-op executables is always created to
satisfy any residual label references in attrs.bzl.
"""

load("//:config.bzl", "global_config")
load("//:gnumake.bzl", "gnumake")
load("//:load_json_file.bzl", "load_json_file")
load("//:stub.bzl", "stub_docker_orfs")
load(
    "//:yosys_repo.bzl",
    "ABC_COMMIT",
    "CXXOPTS_COMMIT",
    "FMT_COMMIT",
    "SLANG_COMMIT",
    "YOSYS_COMMIT",
    "YOSYS_SLANG_COMMIT",
    "yosys_sources",
)

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
            default = Label("@yosys//:yosys-abc"),
        ),
        "yosys_share": attr.label(
            mandatory = False,
            default = Label("@yosys//:yosys_share"),
        ),
        # Yosys source commit overrides (rarely needed by consumers)
        "yosys_commit": attr.string(default = ""),
        "abc_commit": attr.string(default = ""),
        "cxxopts_commit": attr.string(default = ""),
        "yosys_slang_commit": attr.string(default = ""),
        "slang_commit": attr.string(default = ""),
        "fmt_commit": attr.string(default = ""),
    },
)

def _orfs_repositories_impl(module_ctx):
    # Stub repo with no-op executables for residual @docker_orfs references
    stub_docker_orfs(name = "docker_orfs")

    # GNU Make built from source
    gnumake(name = "gnumake")

    for default in module_ctx.modules[0].tags.default:
        # Build yosys from source (lazy — only fetches when targets are requested)
        yosys_sources(
            name = "yosys",
            yosys_commit = default.yosys_commit or YOSYS_COMMIT,
            abc_commit = default.abc_commit or ABC_COMMIT,
            cxxopts_commit = default.cxxopts_commit or CXXOPTS_COMMIT,
            yosys_slang_commit = default.yosys_slang_commit or YOSYS_SLANG_COMMIT,
            slang_commit = default.slang_commit or SLANG_COMMIT,
            fmt_commit = default.fmt_commit or FMT_COMMIT,
        )

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
