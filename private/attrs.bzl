"""Attribute builders for OpenROAD-flow-scripts Bazel rules."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load(
    "@config//:global_config.bzl",
    "CONFIG_KLAYOUT",
    "CONFIG_MAKE",
    "CONFIG_MAKEFILE",
    "CONFIG_MAKEFILE_YOSYS",
    "CONFIG_OPENROAD",
    "CONFIG_OPENROAD_QT",
    "CONFIG_OPENSTA",
    "CONFIG_PDK",
    "CONFIG_YOSYS",
    "CONFIG_YOSYS_ABC",
    "CONFIG_YOSYS_PLUGINS",
    "CONFIG_YOSYS_SHARE",
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
        "extra_arguments": attr.label_list(
            doc = "List of .json argument files to merge into stage config.",
            allow_files = [".json"],
            default = [],
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
            default = CONFIG_MAKE,
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
        "_merge_arguments": attr.label(
            doc = "Python script for merging .json argument files into .mk config.",
            allow_single_file = True,
            default = Label("@bazel-orfs//private:merge_arguments.py"),
        ),
        "_package_stage": attr.label(
            doc = "Python script for creating portable stage tarballs.",
            allow_single_file = True,
            default = Label("@bazel-orfs//:package_stage.py"),
        ),
    }

def flow_attrs():
    return {
        "_deploy_template": attr.label(
            default = Label("@bazel-orfs//:deploy.tpl"),
            allow_single_file = True,
        ),
        "lint": attr.bool(
            doc = "Lint mode: minimal tool dependencies, skip full synthesis, silent make.",
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
        "openroad": attr.label(
            doc = "OpenROAD binary. Override to use a custom or locally-built openroad.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_OPENROAD,
        ),
        "openroad_qt": attr.label(
            doc = "OpenROAD binary with Qt GUI linked in. Used by " +
                  "`bazelisk run <target> gui_<stage>` so opening the " +
                  "GUI reuses the CLI binary's cache instead of " +
                  "triggering a full Qt-linked rebuild.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_OPENROAD_QT,
        ),
        "opensta": attr.label(
            doc = "OpenSTA binary. Override to use a custom or locally-built opensta.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = CONFIG_OPENSTA,
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
        "_yosys_share": attr.label(
            doc = "Yosys share directory (plugins, etc.).",
            cfg = "exec",
            default = CONFIG_YOSYS_SHARE,
        ),
        "_yosys_plugins": attr.label_list(
            doc = "Extra .so plugin files exposed via YOSYS_PLUGIN_PATH.",
            allow_files = True,
            cfg = "exec",
            default = CONFIG_YOSYS_PLUGINS,
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
        "kept_macros": attr.string_list_dict(
            default = {},
            doc = "Per-kept-module macro allowlist. Keys are kept-module " +
                  "names (a subset of SYNTH_KEEP_MODULES); values are " +
                  "short names of macros in `deps` that the kept module " +
                  "instantiates (transitively, stopping at descendant " +
                  "kept modules). Active only when kept_macros_enabled. " +
                  "Empty dict ({}) opts into a pre-synth validation that " +
                  "prints the correct dict and errors. Non-empty dict " +
                  "scopes each parallel partition's macro inputs to the " +
                  "union of macros for its assigned modules.",
        ),
        "canon_blackbox_macros": attr.string_list(
            default = [],
            doc = "Module names (subset of `deps`) to blackbox at the global " +
                  "canonicalize via slang --blackboxed-module, instead of " +
                  "reading their liberty. Use for hardened logic macros whose " +
                  "only liberty is a post-PnR abstract (e.g. SHARED_LOGIC): " +
                  "blackboxing them by name takes the interface from the " +
                  "design Verilog and keeps the bare module name (so OpenROAD's " +
                  "LEF-master lookup still matches), so canonicalize no longer " +
                  "depends on their place-and-route. Leave memory macros out — " +
                  "they have cheap pre-layout liberty and blackboxing them by " +
                  "name would elaborate their bodies into every partition slice.",
        ),
        "kept_macros_enabled": attr.bool(
            default = False,
            doc = "Set automatically by the orfs_flow() wrapper when the " +
                  "user passes kept_macros=. Distinguishes 'unset' " +
                  "(False, default → all macros to all partitions, no " +
                  "validation) from 'empty dict opt-in' (True with " +
                  "kept_macros={}).",
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
    return flow_attrs() | openroad_only_attrs() | {
        "substeps": attr.bool(
            default = False,
            doc = "When True, capture intermediate substep .odb files as " +
                  "additional action outputs in per-substep output groups. " +
                  "Enables shared cache of substep intermediates for " +
                  "debugging via //:deps.",
        ),
    }
