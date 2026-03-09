# kepler-formal integration
#
# Currently uses a local wrapper script that delegates to whatever
# kepler-formal binary is on $PATH (or $KEPLER_FORMAL).
#
# When kepler-formal is published to the Bazel Central Registry (BCR),
# replace this with a proper module dependency in MODULE.bazel:
#
#   bazel_dep(name = "kepler-formal", version = "x.y.z")
#
# Until then, you can pin to a specific git commit via git_override
# in MODULE.bazel:
#
#   git_override(
#       module_name = "kepler-formal",
#       remote = "https://github.com/keplertech/kepler-formal.git",
#       commit = "<sha>",
#   )
#
# Or build from source and set KEPLER_FORMAL=/path/to/kepler-formal.

sh_binary(
    name = "kepler_formal",
    srcs = ["kepler_formal.sh"],
    visibility = ["//visibility:public"],
)
