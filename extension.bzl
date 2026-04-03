"""
This module extension provides rules for OpenROAD-flow-scripts build stages.

By default, tools are real implementations: OpenROAD and OpenSTA from
the @openroad module, yosys+slang from source (@yosys via rules_foreign_cc),
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
load("//:yosys_build.bzl", "yosys_sources")

_default_tag = tag_class(
    attrs = {
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
    },
)

def _orfs_repositories_impl(module_ctx):
    # Stub repo with no-op executables for residual @docker_orfs references
    stub_docker_orfs(name = "docker_orfs")

    # GNU Make built from source
    gnumake(name = "gnumake")

    # Yosys + yosys-slang sources (build via rules_foreign_cc in generated BUILD)
    for default in module_ctx.modules[0].tags.default:
        yosys_sources(
            name = "yosys",
            yosys_commit = "d3e297fcd479247322f83d14f42b3556db7acdfb",
            abc_commit = "8e401543d3ecf65e3a3631c7a271793a4d356cb0",
            cxxopts_commit = "4bf61f08697b110d9e3991864650a405b3dd515d",
            yosys_slang_commit = "64b44616a3798f07453b14ea03e4ac8a16b77313",
            slang_commit = "d7888c90a048e47384e530fef9863e65952c9e3c",
            fmt_commit = "553ec11ec06fbe0beebfbb45f9dc3c9eabd83d28",
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
