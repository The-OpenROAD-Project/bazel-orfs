"""Repository rule to detect the number of CPUs available on the host.

This runs once during workspace setup and writes a .bzl file with the
CPU count, which openroad.bzl uses for resource_set scheduling.
"""

def _detect_cpus_impl(repository_ctx):
    python = repository_ctx.path(repository_ctx.attr.python_interpreter)
    result = repository_ctx.execute([
        str(python),
        "-c",
        "import os; print(os.cpu_count() or 1)",
    ])
    if result.return_code == 0:
        cpus = int(result.stdout.strip())
    else:
        cpus = 8
    repository_ctx.file("BUILD.bazel", "")
    repository_ctx.file("cpus.bzl", "NUM_CPUS = %d\n" % cpus)

detect_cpus = repository_rule(
    implementation = _detect_cpus_impl,
    attrs = {
        "python_interpreter": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "Hermetic Python interpreter used to detect CPU count.",
        ),
    },
    local = True,
    configure = True,
)
