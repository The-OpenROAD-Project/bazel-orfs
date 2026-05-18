"""Global configuration repository rule."""

def _global_config_impl(repository_ctx):
    result = repository_ctx.execute(["nproc"])
    if result.return_code == 0:
        num_cpus = int(result.stdout.strip())
    else:
        num_cpus = 4
    yosys_plugins_repr = "[" + ", ".join(
        ['"{}"'.format(p) for p in repository_ctx.attr.yosys_plugins],
    ) + "]"
    repository_ctx.file(
        "global_config.bzl",
        """
CONFIG_KLAYOUT = "{klayout}"
CONFIG_MAKE = "{make}"
CONFIG_MAKEFILE = "{makefile}"
CONFIG_MAKEFILE_YOSYS = "{makefile_yosys}"
CONFIG_OPENROAD = "{openroad}"
CONFIG_OPENROAD_QT = "{openroad_qt}"
CONFIG_OPENSTA = "{opensta}"
CONFIG_PDK = "{pdk}"
CONFIG_YOSYS = "{yosys}"
CONFIG_YOSYS_ABC = "{yosys_abc}"
CONFIG_YOSYS_SHARE = "{yosys_share}"
CONFIG_YOSYS_PLUGINS = {yosys_plugins}
NUM_CPUS = {num_cpus}
""".format(
            klayout = repository_ctx.attr.klayout,
            make = repository_ctx.attr.make,
            makefile = repository_ctx.attr.makefile,
            makefile_yosys = repository_ctx.attr.makefile_yosys,
            openroad = repository_ctx.attr.openroad,
            openroad_qt = repository_ctx.attr.openroad_qt,
            opensta = repository_ctx.attr.opensta,
            pdk = repository_ctx.attr.pdk,
            yosys = repository_ctx.attr.yosys,
            yosys_abc = repository_ctx.attr.yosys_abc,
            yosys_share = repository_ctx.attr.yosys_share,
            yosys_plugins = yosys_plugins_repr,
            num_cpus = num_cpus,
        ),
    )
    repository_ctx.file("BUILD", "")

global_config = repository_rule(
    implementation = _global_config_impl,
    attrs = {
        "klayout": attr.label(
            mandatory = True,
            cfg = "exec",
        ),
        "make": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@gnumake//:make"),
        ),
        "makefile": attr.label(mandatory = True),
        "makefile_yosys": attr.label(mandatory = True),
        "openroad": attr.label(
            mandatory = True,
            cfg = "exec",
        ),
        "openroad_qt": attr.label(
            mandatory = True,
            cfg = "exec",
        ),
        "opensta": attr.label(
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
        "yosys_share": attr.label(mandatory = True),
        "yosys_plugins": attr.label_list(),
    },
    doc = "A repository that provides global configuration values as strings.",
)
