load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("@bazel_tools//tools/build_defs/repo:utils.bzl", "maybe")

scala_version = "2.13.14"

# This file marks the root of the Bazel workspace.
# See MODULE.bazel for external dependencies setup.
maybe(
    http_archive,
    name = "io_bazel_rules_scala",
    sha256 = "462689f49a130f6d9b57c03aed3da47b4ff44e0b712c73970ce99c6ca36316e9",
    strip_prefix = "rules_scala-3da60a8a8c34ca213836d5b3a499875636139c44",
    url = "https://github.com/bazelbuild/rules_scala/archive/3da60a8a8c34ca213836d5b3a499875636139c44.zip",
)

load("@io_bazel_rules_scala//:scala_config.bzl", "scala_config")

scala_config(scala_version = scala_version)

load("@io_bazel_rules_scala//scala:scala.bzl", "rules_scala_setup", "rules_scala_toolchain_deps_repositories")

rules_scala_setup()

rules_scala_toolchain_deps_repositories(fetch_sources = True)

register_toolchains("//toolchains:scala_toolchain")

rules_scala_setup()

rules_scala_toolchain_deps_repositories(fetch_sources = True)

register_toolchains("//toolchains:scala_toolchain")
