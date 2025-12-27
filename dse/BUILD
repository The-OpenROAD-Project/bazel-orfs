load("@bazel_skylib//rules:common_settings.bzl", "string_flag")
load("//:param.bzl", "param")

string_flag(
    name = "density",
    build_setting_default = "50",
)

string_flag(
    name = "utilization",
    build_setting_default = "45",
)

param(
    name = "params",
    parameters = {
        ":density": "PLACE_DENSITY",
        ":utilization": "CORE_UTILIZATION",
    },
)
