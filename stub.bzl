"""Stub @docker_orfs repository for zero-docker mode.

Creates a repository with empty filegroups for all targets that
attrs.bzl references from @docker_orfs. This allows zero-docker
mode where real tools come from CONFIG_* overrides.
"""

_STUB_BUILD = """\
package(default_visibility = ["//visibility:public"])

# Stub targets for zero-docker mode.
# Real tools are provided via CONFIG_* overrides in global_config.

[filegroup(name = n, srcs = []) for n in [
    "make",
    "opengl",
    "qt_plugins",
    "sta",
    "tcl8.6",
    "ruby3.0.0",
    "ruby_dynamic3.0.0",
    "openroad",
    "yosys",
    "yosys-abc",
    "klayout",
    "makefile",
    "makefile_yosys",
    "ld.so",
    "libexec",
    "yosys_share",
]]

# Stub PDK targets
[filegroup(name = pdk, srcs = []) for pdk in [
    "asap7",
    "gf180",
    "nangate45",
    "sky130hd",
    "sky130hs",
    "ihp-sg13g2",
]]
"""

def _stub_docker_orfs_impl(repository_ctx):
    repository_ctx.file("BUILD.bazel", _STUB_BUILD)

stub_docker_orfs = repository_rule(
    implementation = _stub_docker_orfs_impl,
    doc = "Creates a stub @docker_orfs repo with empty filegroups for zero-docker mode.",
)
