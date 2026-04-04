"""Stub @docker_orfs repository for zero-docker mode.

Creates a repository with empty filegroups and no-op executables for
all targets that attrs.bzl references from @docker_orfs. This allows
zero-docker mode where real tools come from CONFIG_* overrides.
"""

_STUB_BUILD = """\
package(default_visibility = ["//visibility:public"])

# Stub targets for zero-docker mode.
# Real tools are provided via CONFIG_* overrides in global_config.

[filegroup(name = n, srcs = []) for n in [
    "opengl",
    "qt_plugins",
    "tcl8.6",
    "ruby3.0.0",
    "ruby_dynamic3.0.0",
    "ld.so",
    "libexec",
    "yosys_share",
]]

# No-op executable stubs for tools that may be referenced but not
# invoked on the mock/lint path.
[sh_binary(name = n, srcs = ["noop.sh"]) for n in [
    "make",
    "makefile",
    "makefile_yosys",
    "sta",
    "openroad",
    "yosys",
    "yosys-abc",
    "klayout",
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
    repository_ctx.file("noop.sh", "#!/bin/bash\nexit 0\n", executable = True)

stub_docker_orfs = repository_rule(
    implementation = _stub_docker_orfs_impl,
    doc = "Creates a stub @docker_orfs repo with no-op executables for zero-docker mode.",
)
