"""Global configuration repository rule."""

def _global_config_impl(repository_ctx):
    result = repository_ctx.execute(["nproc"])
    if result.return_code == 0:
        num_cpus = int(result.stdout.strip())
    else:
        num_cpus = 4
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
CONFIG_YOSYS_SHARE = "{yosys_share}"
NUM_CPUS = {num_cpus}
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
            yosys_share = repository_ctx.attr.yosys_share,
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
        "yosys_share": attr.label(
            mandatory = False,
            default = Label("@docker_orfs//:yosys_share"),
        ),
    },
    doc = "A repository that provides global configuration values as strings.",
)
