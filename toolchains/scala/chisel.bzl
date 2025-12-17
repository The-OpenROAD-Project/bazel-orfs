# buildifier: disable=module-docstring
load("//toolchains/scala:scala_binary.bzl", "scala_binary", "scala_test")
load("//toolchains/scala:scala_library.bzl", "scala_library")

def chisel_binary(name, **kwargs):
    scala_binary(
        name = name,
        deps = [
                   "@maven//:com_chuusai_shapeless_2_13",
                   "@maven//:com_lihaoyi_os_lib_2_13",
                   "@maven//:io_circe_circe_core_2_13",
                   "@maven//:io_circe_circe_generic_2_13",
                   "@maven//:io_circe_circe_generic_extras_2_13",
                   "@maven//:io_circe_circe_parser_2_13",
                   "@maven//:org_chipsalliance_chisel_2_13",
                   "@maven//:org_scala_lang_scala_library_2_13_18",
                   "@maven//:org_scala_lang_scala_reflect_2_13_18",
                   "@maven//:org_typelevel_cats_core_2_13",
                   "@maven//:org_typelevel_cats_kernel_2_13",
               ] +
               kwargs.pop("deps", []),
        scalacopts = [
                         "-language:reflectiveCalls",
                         "-deprecation",
                         "-feature",
                         "-Xcheckinit",
                     ] +
                     kwargs.pop("scalacopts", []),
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_18",
        ],
        **kwargs
    )

def chisel_library(name, **kwargs):
    scala_library(
        name = name,
        deps = [
                   "@maven//:com_chuusai_shapeless_2_13",
                   "@maven//:com_lihaoyi_os_lib_2_13",
                   "@maven//:io_circe_circe_core_2_13",
                   "@maven//:io_circe_circe_generic_2_13",
                   "@maven//:io_circe_circe_generic_extras_2_13",
                   "@maven//:io_circe_circe_parser_2_13",
                   "@maven//:org_chipsalliance_chisel_2_13",
                   "@maven//:org_scala_lang_scala_library_2_13_18",
                   "@maven//:org_scala_lang_scala_reflect_2_13_18",
                   "@maven//:org_typelevel_cats_core_2_13",
                   "@maven//:org_typelevel_cats_kernel_2_13",
               ] +
               kwargs.pop("deps", []),
        scalacopts = [
                         "-language:reflectiveCalls",
                         "-deprecation",
                         "-feature",
                         "-Xcheckinit",
                     ] +
                     kwargs.pop("scalacopts", []),
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_18",
        ],
        **kwargs
    )

def chisel_test(name, **kwargs):
    scala_test(
        name = name,
        data = [
                   "@circt//:bin/firtool",
                   "@verilator//:bin/verilator",
                   "@verilator//:verilator_includes",
                   "//toolchains/verilator:verilator_includer",
               ] +
               kwargs.pop("data", []),
        deps = [
                   "@maven//:com_chuusai_shapeless_2_13",
                   "@maven//:com_lihaoyi_os_lib_2_13",
                   "@maven//:io_circe_circe_core_2_13",
                   "@maven//:io_circe_circe_generic_2_13",
                   "@maven//:io_circe_circe_generic_extras_2_13",
                   "@maven//:io_circe_circe_parser_2_13",
                   "@maven//:org_chipsalliance_chisel_2_13",
                   "@maven//:org_scala_lang_scala_library_2_13_18",
                   "@maven//:org_scala_lang_scala_reflect_2_13_18",
                   "@maven//:org_typelevel_cats_core_2_13",
                   "@maven//:org_typelevel_cats_kernel_2_13",
               ] +
               kwargs.pop("deps", []),
        env = {
                  # Doesn't work in hermetic mode, no point in Bazel, no home folder
                  "CCACHE_DISABLE": "1",
                  "CHISEL_FIRTOOL_BINARY_PATH": "$(rootpath @circt//:bin/firtool)",
                  "VERILATOR_BIN": "$(rootpath @verilator//:bin/verilator)",
              } |
              kwargs.pop("env", {}),
        scalacopts = [
                         "-language:reflectiveCalls",
                         "-deprecation",
                         "-feature",
                         "-Xcheckinit",
                     ] +
                     kwargs.pop("scalacopts", []),
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_18",
        ],
        **kwargs
    )
