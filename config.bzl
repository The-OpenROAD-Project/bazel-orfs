"""Global configuration repository rule."""

def _global_config_impl(repository_ctx):
    repository_ctx.file(
        "global_config.bzl",
        """
CONFIG_KLAYOUT = "{klayout}"
CONFIG_MAKEFILE = "{makefile}"
CONFIG_PDK = "{pdk}"
CONFIG_MAKEFILE_YOSYS = "{makefile_yosys}"
CONFIG_OPENROAD = "{openroad}"
CONFIG_YOSYS = "{yosys}"
CONFIG_YOSYS_ABC = "{yosys_abc}"
""".format(
            klayout = repository_ctx.attr.klayout,
            makefile = repository_ctx.attr.makefile,
            pdk = repository_ctx.attr.pdk,
            makefile_yosys = repository_ctx.attr.makefile_yosys,
            openroad = repository_ctx.attr.openroad,
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
        ),
        "makefile": attr.label(mandatory = True),
        "makefile_yosys": attr.label(mandatory = True),
        "openroad": attr.label(
            mandatory = True,
            cfg = "exec",
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
