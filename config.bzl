"""Global configuration repository rule."""

def _global_config_impl(repository_ctx):
    repository_ctx.file(
        "global_config.bzl",
        """
CONFIG_KLAYOUT = "{klayout}"
CONFIG_MAKE = "{make}"
CONFIG_MAKEFILE = "{makefile}"
CONFIG_MAKEFILE_YOSYS = "{makefile_yosys}"
CONFIG_OPENROAD = "{openroad}"
CONFIG_OPENSTA = "{opensta}"
CONFIG_PDK = "{pdk}"
CONFIG_YOSYS = "{yosys}"
CONFIG_YOSYS_ABC = "{yosys_abc}"
""".format(
            klayout = repository_ctx.attr.klayout,
            make = repository_ctx.attr.make,
            makefile = repository_ctx.attr.makefile,
            makefile_yosys = repository_ctx.attr.makefile_yosys,
            openroad = repository_ctx.attr.openroad,
            opensta = repository_ctx.attr.opensta,
            pdk = repository_ctx.attr.pdk,
            yosys = repository_ctx.attr.yosys,
            yosys_abc = repository_ctx.attr.yosys_abc,
        ),
    )
    repository_ctx.file("BUILD", "")

global_config = repository_rule(
    implementation = _global_config_impl,
    attrs = {
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
        "makefile": attr.label(mandatory = True),
        "makefile_yosys": attr.label(mandatory = True),
        "openroad": attr.label(
            mandatory = True,
            cfg = "exec",
        ),
        "opensta": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@docker_orfs//:sta"),
        ),
        "pdk": attr.label(mandatory = True),
        "yosys": attr.label(
            mandatory = True,
            cfg = "exec",
        ),
        "yosys_abc": attr.label(
            mandatory = True,
            cfg = "exec",
        ),
    },
    doc = "A repository that provides global configuration values as strings.",
)
