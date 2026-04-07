"""Environment, input, and configuration helper functions for OpenROAD-flow-scripts rules."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load(
    "//private:providers.bzl",
    "LoggingInfo",
    "OrfsInfo",
    "PdkInfo",
    "TopInfo",
)
load("//private:stages.bzl", "ALL_STAGE_TO_VARIABLES")
load("//private:utils.bzl", "commonpath", "file_path", "flatten")

def odb_arguments(ctx, short = False):
    if ctx.attr.src[OrfsInfo].odb:
        odb = ctx.attr.src[OrfsInfo].odb
        return {"ODB_FILE": file_path(odb, short)}
    return {}

def _work_home(ctx):
    # For external repo targets, declared files are placed under
    # bin/external/<repo>/<package>, but genfiles_dir.path is just bin/.
    # Use the declared file path of a known output to derive the correct prefix.
    parts = [ctx.genfiles_dir.path]
    if ctx.label.workspace_name:
        parts.append("external")
        parts.append(ctx.label.workspace_name)
    if ctx.label.package:
        parts.append(ctx.label.package)
    return "/".join(parts)

def _optional_commonpath(files):
    """Returns commonpath of files, or empty string if files is empty."""
    return commonpath(files) if files else ""

def orfs_environment(ctx):
    env = {
        "HOME": _work_home(ctx),
        "PYTHON_EXE": ctx.executable._python.path,
        "STDBUF_CMD": "",
        "WORK_HOME": _work_home(ctx),
    }
    if ctx.files._tcl:
        env["TCL_LIBRARY"] = commonpath(ctx.files._tcl)
    return env

def _klayout_attr(ctx):
    """Returns the klayout attr, preferring public 'klayout' over private '_klayout'."""
    if hasattr(ctx.attr, "klayout") and ctx.attr.klayout:
        return ctx.attr.klayout
    return ctx.attr._klayout

def _openroad_attr(ctx):
    """Returns the openroad attr, preferring public 'openroad' over private '_openroad'."""
    if hasattr(ctx.attr, "openroad") and ctx.attr.openroad:
        return ctx.attr.openroad
    return ctx.attr._openroad

def _openroad_executable(ctx):
    """Returns the openroad executable path."""
    attr = _openroad_attr(ctx)
    return attr[DefaultInfo].files_to_run.executable.path

def _opensta_attr(ctx):
    """Returns the opensta attr, preferring public 'opensta' over private '_opensta'."""
    if hasattr(ctx.attr, "opensta") and ctx.attr.opensta:
        return ctx.attr.opensta
    return ctx.attr._opensta

def _opensta_executable(ctx):
    """Returns the opensta executable path."""
    attr = _opensta_attr(ctx)
    return attr[DefaultInfo].files_to_run.executable.path

def _klayout_executable(ctx):
    """Returns the klayout executable path."""
    attr = _klayout_attr(ctx)
    return attr[DefaultInfo].files_to_run.executable.path

def flow_environment(ctx):
    env = {
        "FLOW_HOME": ctx.file._makefile.dirname,
        "KLAYOUT_CMD": _klayout_executable(ctx),
        "OPENROAD_EXE": _openroad_executable(ctx),
        "OPENSTA_EXE": _opensta_executable(ctx),
    }
    if ctx.files._ruby_dynamic:
        env["DLN_LIBRARY_PATH"] = commonpath(ctx.files._ruby_dynamic)
    if ctx.files._qt_plugins:
        env["QT_PLUGIN_PATH"] = commonpath(ctx.files._qt_plugins)
        env["QT_QPA_PLATFORM_PLUGIN_PATH"] = commonpath(ctx.files._qt_plugins)
    if ctx.files._ruby or ctx.files._ruby_dynamic:
        env["RUBYLIB"] = ":".join(
            [_optional_commonpath(ctx.files._ruby), _optional_commonpath(ctx.files._ruby_dynamic)],
        )
    return env | orfs_environment(ctx)

def yosys_environment(ctx):
    return {
        "ABC": ctx.executable._abc.path,
        "FLOW_HOME": ctx.file._makefile_yosys.dirname,
        "YOSYS_EXE": ctx.executable.yosys.path,
    } | orfs_environment(ctx)

def config_environment(config):
    return {"DESIGN_CONFIG": config.path}

def _runfiles(attrs):
    return depset(
        [tool[DefaultInfo].files_to_run.executable for tool in attrs],
        transitive = flatten(
            [
                [
                    tool[DefaultInfo].default_runfiles.files,
                    tool[DefaultInfo].default_runfiles.symlinks,
                ]
                for tool in attrs
            ],
        ),
    )

def flow_inputs(ctx):
    if ctx.attr.lint:
        return flow_inputs_lite(ctx)
    return depset(
        ctx.files._ruby +
        ctx.files._ruby_dynamic +
        ctx.files._tcl +
        ctx.files._opengl +
        ctx.files._qt_plugins,
        transitive = [
            _runfiles(
                [
                    _klayout_attr(ctx),
                    ctx.attr._make,
                    _openroad_attr(ctx),
                    _opensta_attr(ctx),
                    ctx.attr._python,
                    ctx.attr._makefile,
                ] +
                ctx.attr.tools,
            ),
        ],
    )

def flow_inputs_lite(ctx):
    """Minimal tool inputs for lightweight flows (lint/mock).

    Excludes klayout, opensta, ruby, tcl, opengl, qt — only includes
    make, openroad (or its replacement), python, makefile, and user tools.
    """
    return depset(
        transitive = [
            _runfiles(
                [
                    ctx.attr._make,
                    _openroad_attr(ctx),
                    ctx.attr._python,
                    ctx.attr._makefile,
                ] + ctx.attr.tools,
            ),
        ],
    )

def test_inputs(ctx):
    return depset(
        transitive = [
            _runfiles(
                [
                    ctx.attr._make,
                    ctx.attr._python,
                    ctx.attr._makefile,
                ],
            ),
        ],
    )

def yosys_inputs(ctx):
    return depset(
        ctx.files._tcl + ctx.files._yosys_share,
        transitive = [
            _runfiles(
                [
                    ctx.attr._abc,
                    ctx.attr.yosys,
                    ctx.attr._make,
                    ctx.attr._makefile_yosys,
                    ctx.attr._python,
                ],
            ),
        ],
    )

def data_inputs(ctx):
    return depset(
        ctx.files.data,
        transitive = [datum.default_runfiles.files for datum in ctx.attr.data] +
                     [datum.default_runfiles.symlinks for datum in ctx.attr.data],
    )

def source_inputs(ctx):
    return depset(
        ctx.files.src,
        transitive = [
            ctx.attr.src[OrfsInfo].additional_gds,
            ctx.attr.src[OrfsInfo].additional_lefs,
            ctx.attr.src[OrfsInfo].additional_libs,
            ctx.attr.src[PdkInfo].files,
            ctx.attr.src[PdkInfo].libs,
            # Accumulate all JSON reports, so depend on previous stage.
            ctx.attr.src[LoggingInfo].jsons,
            ctx.attr.src[LoggingInfo].reports,
            # non-idempotent by design transitive dependencies
            # ctx.attr.src[LoggingInfo].logs,
        ],
    )

def rename_inputs(ctx):
    return depset(
        transitive = [target.files for target in ctx.attr.renamed_inputs.values()],
    )

def pdk_inputs(ctx):
    return depset(transitive = [ctx.attr.pdk[PdkInfo].files, ctx.attr.pdk[PdkInfo].libs])

def deps_inputs(ctx):
    return depset(
        [dep[OrfsInfo].gds for dep in ctx.attr.deps if dep[OrfsInfo].gds] +
        [dep[OrfsInfo].lef for dep in ctx.attr.deps if dep[OrfsInfo].lef] +
        [dep[OrfsInfo].lib for dep in ctx.attr.deps if dep[OrfsInfo].lib],
    )

def flow_substitutions(ctx):
    return {
        "${DLN_LIBRARY_PATH}": _optional_commonpath(ctx.files._ruby_dynamic),
        "${FLOW_HOME}": ctx.file._makefile.dirname,
        "${KLAYOUT_PATH}": ctx.executable._klayout.path,
        "${LIBGL_DRIVERS_PATH}": _optional_commonpath(ctx.files._opengl),
        "${MAKEFILE_PATH}": ctx.file._makefile.path,
        "${MAKE_PATH}": "./" + ctx.executable._make.short_path,
        # OpenROAD uses //:openroad, //:opensta here and puts the binary in the pwd
        "${OPENROAD_PATH}": "./" + _openroad_attr(ctx)[DefaultInfo].files_to_run.executable.short_path,
        "${OPENSTA_PATH}": "./" + _opensta_attr(ctx)[DefaultInfo].files_to_run.executable.short_path,
        "${QT_PLUGIN_PATH}": _optional_commonpath(ctx.files._qt_plugins),
        "${RUBY_PATH}": _optional_commonpath(ctx.files._ruby),
        "${STDBUF_PATH}": "",
        "${TCL_LIBRARY}": _optional_commonpath(ctx.files._tcl),
    }

def yosys_substitutions(ctx):
    return {
        "${ABC}": ctx.executable._abc.path,
        "${YOSYS_PATH}": ctx.executable.yosys.path,
    }

def module_top(ctx):
    return (
        ctx.attr.module_top if hasattr(ctx.attr, "module_top") else ctx.attr.src[TopInfo].module_top
    )

def platform(ctx):
    return (
        ctx.attr.pdk[PdkInfo].name if hasattr(ctx.attr, "pdk") else ctx.attr.src[PdkInfo].name
    )

def platform_config(ctx):
    return (
        ctx.attr.pdk[PdkInfo] if hasattr(ctx.attr, "pdk") else ctx.attr.src[PdkInfo]
    ).config.files.to_list()[0]

def required_arguments(ctx):
    return {
        "DESIGN_NAME": module_top(ctx),
        "FLOW_VARIANT": ctx.attr.variant,
        "GENERATE_ARTIFACTS_ON_FAILURE": "1",
        "PLATFORM": platform(ctx),
        "PLATFORM_DIR": platform_config(ctx).dirname,
        "WORK_HOME": "./" + ctx.label.package,
    }

def orfs_additional_arguments(*args, short = False):
    """Returns ADDITIONAL_GDS/LEFS/LIBS arguments from OrfsInfo providers.

    Args:
      *args: OrfsInfo provider instances.
      short: If True, use short_path instead of path.

    Returns:
      A dictionary of ADDITIONAL_GDS/LEFS/LIBS arguments.
    """
    gds = depset(
        [info.gds for info in args if info.gds],
        transitive = [info.additional_gds for info in args],
    )
    lefs = depset(
        [info.lef for info in args if info.lef],
        transitive = [info.additional_lefs for info in args],
    )
    libs = depset(
        [info.lib for info in args if info.lib],
        transitive = [info.additional_libs for info in args],
    )

    arguments = {}
    if gds.to_list():
        arguments["ADDITIONAL_GDS"] = " ".join(
            sorted([file_path(file, short) for file in gds.to_list()]),
        )
    if lefs.to_list():
        arguments["ADDITIONAL_LEFS"] = " ".join(
            sorted(
                [file_path(file, short) for file in lefs.to_list()],
            ),
        )
    if libs.to_list():
        arguments["ADDITIONAL_LIBS"] = " ".join(
            sorted(
                [file_path(file, short) for file in libs.to_list()],
            ),
        )
    return arguments

_ADDITIONAL_KEYS = ("ADDITIONAL_GDS", "ADDITIONAL_LEFS", "ADDITIONAL_LIBS")

def merge_arguments(base, overlay):
    """Merge two argument dicts, concatenating ADDITIONAL_* values.

    For ADDITIONAL_GDS/LEFS/LIBS, values from both dicts are combined
    (space-separated, deduplicated, sorted) instead of the overlay
    overriding the base.  All other keys use standard dict merge
    semantics (overlay wins).

    Args:
      base: Base argument dictionary.
      overlay: Overlay argument dictionary (wins for non-ADDITIONAL keys).

    Returns:
      A merged dictionary.
    """
    result = base | overlay
    for key in _ADDITIONAL_KEYS:
        base_val = base.get(key, "")
        overlay_val = overlay.get(key, "")
        if base_val and overlay_val:
            combined = sorted(set(base_val.split(" ") + overlay_val.split(" ")))
            result[key] = " ".join(combined)
    return result

def verilog_arguments(files, short = False):
    return {
        "VERILOG_FILES": " ".join(
            [file_path(file, short) for file in files],
        ),
    }

# Shell snippet prepended to synthesis commands to expand directory entries
# in VERILOG_FILES to individual .v/.sv/.svh files.  TreeArtifacts (from
# verilog_directory) appear as directory paths that synthesis frontends
# (slang, yosys, verific) cannot process directly.
EXPAND_VERILOG_DIRS = """\
_expanded=""
for _f in $VERILOG_FILES; do
  if [ -d "$_f" ]; then
    _expanded="$_expanded $(find "$_f" \\( -name '*.v' -o -name '*.sv' -o -name '*.svh' \\) | sort | tr '\\n' ' ')"
  else
    _expanded="$_expanded $_f"
  fi
done
export VERILOG_FILES="$_expanded"
"""

def config_overrides(ctx, arguments):
    has_stage = hasattr(ctx.attr, "_stage")
    defines_for_stage = {
        var: value
        for var, value in ctx.var.items()
        if has_stage and
           var in
           (
               ALL_STAGE_TO_VARIABLES[ctx.attr._stage] +
               # FIXME delete this hotfix on next ORFS update
               # https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/pull/3746
               {"synth": ["VERILOG_TOP_PARAMS"]}.get(ctx.attr._stage, [])
           )
    }
    settings = {
        var: value[BuildSettingInfo].value
        for var, value in ctx.attr.settings.items()
    }
    return arguments | defines_for_stage | settings

def _workspace_prefix(ctx):
    """Return the execroot-relative prefix for the workspace containing ctx.

    For targets in the main repo this is empty.  For external repo targets
    (e.g. @@orfs+) this is "external/<repo_name>".
    """
    if ctx.label.workspace_name:
        return "external/" + ctx.label.workspace_name
    return ""

def _prefix_include_dirs(dirs_value, prefix):
    """Prefix each directory in a space-separated VERILOG_INCLUDE_DIRS value."""
    if not prefix or not dirs_value:
        return dirs_value
    parts = dirs_value.replace("\t", " ").split(" ")
    return " ".join([
        prefix + "/" + p.strip() if p.strip() and not p.strip().startswith(prefix) else p
        for p in parts
        if p.strip()
    ])

def config_content(ctx, arguments, paths, pre_paths = []):
    """Generate Makefile-style config content for an ORFS stage.

    Args:
      ctx: The rule context.
      arguments: Dictionary of config variables.
      paths: List of additional config file paths to include at the end.
      pre_paths: List of config file paths to include at the top, before
        the export lines. Included files set with ?= take precedence over
        the export lines that follow.

    Returns:
      A string with export VAR?=value lines and include directives.
    """
    workaround = {
        # https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/issues/3907
        "LEC_CHECK": "0",
    } | arguments

    # Rewrite VERILOG_INCLUDE_DIRS to use sandbox-relative paths
    prefix = _workspace_prefix(ctx)
    if prefix and "VERILOG_INCLUDE_DIRS" in workaround:
        workaround = dict(workaround)
        workaround["VERILOG_INCLUDE_DIRS"] = _prefix_include_dirs(
            workaround["VERILOG_INCLUDE_DIRS"],
            prefix,
        )

    return "".join(
        ["include {}\n".format(path) for path in pre_paths] +
        sorted(
            [
                "export {}?={}\n".format(*pair)
                for pair in config_overrides(ctx, workaround).items()
            ],
        ) +
        ["include {}\n".format(path) for path in paths],
    )

def hack_away_prefix(arguments, prefix):
    return {
        k: " ".join([w.removeprefix(prefix + "/") for w in v.split(" ")])
        for k, v in arguments.items()
    }

def data_arguments(ctx):
    return {
        k: ctx.expand_location(v, ctx.attr.data)
        for k, v in ctx.attr.arguments.items()
    }

def run_arguments(ctx):
    return {"RUN_SCRIPT": ctx.file.script.path}

def environment_string(env):
    return " ".join(['{}="{}"'.format(*pair) for pair in env.items()])

def generation_commands(optional_files):
    if optional_files:
        return [
            "mkdir -p " +
            " ".join(sorted([result.dirname for result in optional_files])),
            "touch " + " ".join(sorted([result.path for result in optional_files])),
        ]
    return []

def _mv_cmds(src, dst):
    dir, _, _ = dst.rpartition("/")
    return [
        "mkdir -p {}".format(dir),
        "mv {} {}".format(src, dst),
    ]

def input_commands(renames):
    cmds = []
    for rename in renames:
        cmds.extend(_mv_cmds(rename.src, rename.dst))
    return cmds

def _remap(s, a, b):
    if s.endswith(a):
        return s.replace("/" + a, "/" + b)
    return s.replace("/" + a + "/", "/" + b + "/")

def renames(ctx, inputs, short = False):
    """Move inputs to the expected input locations.

    Args:
      ctx: The rule context.
      inputs: List of input files to potentially rename.
      short: If True, use short_path instead of path.

    Returns:
      A list of structs with src and dst fields for renaming.
    """
    result = []
    for file in inputs:
        if ctx.attr.src[OrfsInfo].variant != ctx.attr.variant:
            result.append(
                struct(
                    src = file_path(file, short),
                    dst = _remap(
                        file_path(file, short),
                        ctx.attr.src[OrfsInfo].variant,
                        ctx.attr.variant,
                    ),
                ),
            )

    # renamed_inputs win over variant renaming
    for file in inputs:
        if file.basename in ctx.attr.renamed_inputs:
            for src in ctx.attr.renamed_inputs[file.basename].files.to_list():
                result.append(
                    struct(
                        src = file_path(src, short),
                        dst = _remap(
                            file_path(file, short),
                            ctx.attr.src[OrfsInfo].variant,
                            ctx.attr.variant,
                        ),
                    ),
                )
    return result

def _artifact_name(ctx, category, name = None):
    return "/".join(
        [
            category,
            platform(ctx),
            module_top(ctx),
            ctx.attr.variant,
            name,
        ],
    )

def declare_artifact(ctx, category, name):
    return ctx.actions.declare_file(_artifact_name(ctx, category, name))

def declare_artifacts(ctx, category, names):
    """Declares multiple artifacts in one call.

    Args:
      ctx: Rule context.
      category: Artifact category (e.g., "results", "logs", "reports", "objects").
      names: List of artifact file names.

    Returns:
      List of declared File objects.
    """
    return [declare_artifact(ctx, category, name) for name in names]

def extensionless_basename(file):
    return file.basename.removesuffix("." + file.extension)
