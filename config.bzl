"""Global configuration repository rule."""

def _global_config_impl(repository_ctx):
    repository_ctx.file(
        "global_config.bzl",
        """
CONFIG_MAKEFILE = "{}"
""".format(
            repository_ctx.attr.makefile,
        ),
    )
    repository_ctx.file("BUILD", "")

global_config = repository_rule(
    implementation = _global_config_impl,
    attrs = {
        "makefile": attr.label(
            default = Label("@docker_orfs//:makefile"),
        ),
    },
    doc = "A repository that provides global configuration values as strings.",
)
