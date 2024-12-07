# buildifier: disable=module-docstring
load("@io_bazel_rules_scala//scala:scala.bzl", "scala_binary", "scala_library", "scala_test")

def chisel_binary(name, main_class, srcs, deps = []):
    scala_binary(
        name = name,
        srcs = srcs,
        deps = deps + [
            "@maven//:com_chuusai_shapeless_2_13",
            "@maven//:com_lihaoyi_os_lib_2_13",
            "@maven//:io_circe_circe_core_2_13",
            "@maven//:io_circe_circe_generic_2_13",
            "@maven//:io_circe_circe_generic_extras_2_13",
            "@maven//:io_circe_circe_parser_2_13",
            "@maven//:org_chipsalliance_chisel_2_13",
            "@maven//:org_scala_lang_scala_library_2_13_14",
            "@maven//:org_scala_lang_scala_reflect_2_13_14",
            "@maven//:org_typelevel_cats_core_2_13",
            "@maven//:org_typelevel_cats_kernel_2_13",
        ],
        main_class = main_class,
        scalacopts = [
            "-language:reflectiveCalls",
            "-deprecation",
            "-feature",
            "-Xcheckinit",
        ],
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_14",
        ],
    )

def chisel_library(name, srcs, deps = []):
    scala_library(
        name = name,
        srcs = srcs,
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_14",
        ],
        scalacopts = [
            "-language:reflectiveCalls",
            "-deprecation",
            "-feature",
            "-Xcheckinit",
        ],
        deps = deps + [
            "@maven//:com_chuusai_shapeless_2_13",
            "@maven//:com_lihaoyi_os_lib_2_13",
            "@maven//:io_circe_circe_core_2_13",
            "@maven//:io_circe_circe_generic_2_13",
            "@maven//:io_circe_circe_generic_extras_2_13",
            "@maven//:io_circe_circe_parser_2_13",
            "@maven//:org_chipsalliance_chisel_2_13",
            "@maven//:org_scala_lang_scala_library_2_13_14",
            "@maven//:org_scala_lang_scala_reflect_2_13_14",
            "@maven//:org_typelevel_cats_core_2_13",
            "@maven//:org_typelevel_cats_kernel_2_13",
        ],
    )

def chisel_test(name, srcs, deps = []):
    scala_test(
        name = name,
        srcs = srcs,
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_14",
        ],
        scalacopts = [
            "-language:reflectiveCalls",
            "-deprecation",
            "-feature",
            "-Xcheckinit",
        ],
        deps = deps + [
            "@io_bazel_rules_scala//testing/toolchain:scalatest_classpath",
            "@maven//:com_chuusai_shapeless_2_13",
            "@maven//:com_lihaoyi_os_lib_2_13",
            "@maven//:io_circe_circe_core_2_13",
            "@maven//:io_circe_circe_generic_2_13",
            "@maven//:io_circe_circe_generic_extras_2_13",
            "@maven//:io_circe_circe_parser_2_13",
            "@maven//:org_chipsalliance_chisel_2_13",
            "@maven//:org_scala_lang_scala_library_2_13_14",
            "@maven//:org_scala_lang_scala_reflect_2_13_14",
            "@maven//:org_typelevel_cats_core_2_13",
            "@maven//:org_typelevel_cats_kernel_2_13",
        ],
    )
