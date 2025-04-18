"""Global configuration repository rule."""

def _global_config_impl(repository_ctx):
    repository_ctx.file(
        "global_config.bzl",
        """
CONFIG_MAKEFILE = "{makefile}"
CONFIG_PDK = "{pdk}"
CONFIG_MAKEFILE_YOSYS = "{makefile_yosys}"
CONFIG_OPENROAD = "{openroad}"
""".format(
            makefile = repository_ctx.attr.makefile,
            pdk = repository_ctx.attr.pdk,
            makefile_yosys = repository_ctx.attr.makefile_yosys,
            openroad = repository_ctx.attr.openroad,
        ),
    )
    repository_ctx.file("BUILD", "")

global_config = repository_rule(
    implementation = _global_config_impl,
    attrs = {
        "makefile": attr.label(mandatory = True),
        "pdk": attr.label(mandatory = True),
        "makefile_yosys": attr.label(mandatory = True),
        "openroad": attr.label(mandatory = True),
    },
    doc = "A repository that provides global configuration values as strings.",
)
