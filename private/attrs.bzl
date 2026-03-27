"""Attribute builders for OpenROAD-flow-scripts Bazel rules."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load(
    "@config//:global_config.bzl",
    "CONFIG_KLAYOUT",
    "CONFIG_MAKEFILE",
    "CONFIG_MAKEFILE_YOSYS",
    "CONFIG_OPENROAD",
    "CONFIG_PDK",
    "CONFIG_YOSYS",
    "CONFIG_YOSYS_ABC",
)
load(
    "//private:providers.bzl",
    "LoggingInfo",
    "OrfsDepInfo",
    "OrfsInfo",
    "PdkInfo",
    "TopInfo",
)

def flow_provides():
    return [
        DefaultInfo,
        OutputGroupInfo,
        OrfsDepInfo,
        OrfsInfo,
        LoggingInfo,
        PdkInfo,
        TopInfo,
    ]

def orfs_attrs():
    return {
        "arguments": attr.string_dict(
            doc = "Dictionary of additional flow arguments.",
            default = {},
        ),
        "data": attr.label_list(
            doc = "List of additional flow data.",
            allow_files = True,
            default = [],
        ),
        "settings": attr.string_keyed_label_dict(
            doc = "Arguments with build settings.",
            providers = [BuildSettingInfo],
        ),
        "extra_configs": attr.label_list(
            doc = "List of additional flow configuration files.",
            allow_files = True,
            default = [],
        ),
        "tools": attr.label_list(
            doc = "List of tool binaries.",
            allow_files = True,
            cfg = "exec",
            default = [],
        ),
        "variant": attr.string(
            doc = "Variant of the used flow.",
            default = "base",
        ),
        "_make": attr.label(
            doc = "make binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:make"),
        ),
        "_makefile": attr.label(
            doc = "Top level makefile.",
            allow_single_file = ["Makefile"],
            default = CONFIG_MAKEFILE,
        ),
        "_python": attr.label(
            doc = "Python wrapper.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@bazel-orfs//pythonwrapper:python3"),
        ),
        "_tcl": attr.label(
            doc = "Tcl library.",
            allow_files = True,
            default = Label("@docker_orfs//:tcl8.6"),
        ),
    }

def flow_attrs():
    return {
        "_deploy_template": attr.label(
            default = Label("@bazel-orfs//:deploy.tpl"),
            allow_single_file = True,
        ),
        "lite_flow": attr.bool(
            doc = "Use minimal tool dependencies (for lint/mock flows).",
            default = False,
        ),
        "_klayout": attr.label(
            doc = "Klayout binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_KLAYOUT,
        ),
        "_make_template": attr.label(
            default = Label("@bazel-orfs//:make.tpl"),
            allow_single_file = True,
        ),
        "_opengl": attr.label(
            doc = "OpenGL drivers.",
            allow_files = True,
            default = Label("@docker_orfs//:opengl"),
        ),
        "_openroad": attr.label(
            doc = "OpenROAD binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_OPENROAD,
        ),
        "_opensta": attr.label(
            doc = "OpenSTA binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:sta"),
        ),
        "_qt_plugins": attr.label(
            doc = "Qt plugins.",
            allow_files = True,
            default = Label("@docker_orfs//:qt_plugins"),
        ),
        "_ruby": attr.label(
            doc = "Ruby library.",
            allow_files = True,
            default = Label("@docker_orfs//:ruby3.0.0"),
        ),
        "_ruby_dynamic": attr.label(
            doc = "Ruby dynamic library.",
            allow_files = True,
            default = Label("@docker_orfs//:ruby_dynamic3.0.0"),
        ),
        "openroad": attr.label(
            doc = "OpenROAD binary. Override to use a custom or locally-built openroad.",
            executable = True,
            allow_files = True,
            cfg = "exec",
        ),
    } | orfs_attrs()

def yosys_only_attrs():
    return {
        "_abc": attr.label(
            doc = "Abc binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_YOSYS_ABC,
        ),
        "_makefile_yosys": attr.label(
            doc = "Top level makefile yosys.",
            allow_single_file = ["Makefile"],
            default = CONFIG_MAKEFILE_YOSYS,
        ),
        "yosys": attr.label(
            doc = "Yosys binary. Override to use a custom or locally-built yosys.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_YOSYS,
        ),
    }

def renamed_inputs_attr():
    return {
        "renamed_inputs": attr.string_keyed_label_dict(
            default = {},
        ),
    }

def synth_attrs():
    return {
        "deps": attr.label_list(
            default = [],
            providers = [OrfsInfo, TopInfo],
        ),
        "module_top": attr.string(mandatory = True),
        "pdk": attr.label(
            doc = "Process design kit.",
            default = CONFIG_PDK,
            providers = [PdkInfo],
        ),
        "verilog_files": attr.label_list(
            allow_files = [
                ".v",
                ".sv",
                ".svh",
                ".rtlil",
            ],
            allow_rules = [],
            providers = [DefaultInfo],
        ),
    }

def openroad_only_attrs():
    return {
        "src": attr.label(
            providers = [DefaultInfo],
        ),
    }

def yosys_attrs():
    # flow_attrs() is not used by synthesis, but by bazel run foo_synth to
    # open synthesis results in OpenROAD
    return flow_attrs() | yosys_only_attrs()

def openroad_attrs():
    return flow_attrs() | openroad_only_attrs()
