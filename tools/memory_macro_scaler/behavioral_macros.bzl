"""behavioral_macros(): emit orfs_macro()s from behavioral Verilog, no P&R.

Given a list of Verilog sources, scan them for memory modules and produce
one orfs_macro() per module with a generated .lib + .lef — no synthesis
quality work, no floorplan, no placement. The only EDA step is a light
Yosys read + elaborate to pin down the real endpoint list; everything
else is fitted numbers from memory_macro_scaler. Downstream flows see a
regular orfs_macro() and cannot tell the difference.

The fast genrule below runs the pure-Python scanner + generator, which
picks up firtool-convention modules correctly. For non-firtool Verilog
the generated `.lib` endpoints may not match the actual post-synth pin
list — use the yosys_endpoints variant (TODO) for those.
"""

load("//:openroad.bzl", "orfs_macro")
load(":scaled_macro_lib.bzl", "scaled_macro_lib")

def behavioral_macros(
        name,
        srcs,
        modules,
        tech_nm = 7,
        target_suffix = "",
        **kwargs):
    """Scan `srcs` for memory modules and expose one orfs_macro per module.

    Args:
        name: Prefix for the aggregate filegroup target.
        srcs: List of Verilog file or directory labels.
        modules: Module names to emit (these must match module names in
                 the Verilog; the scanner filters to this list). Starlark
                 can't scan Verilog at loading time, so this list is
                 explicit.
        tech_nm: Target technology node in nm (default 7 = ASAP7).
        target_suffix: Appended to each emitted Bazel target name so they
                       don't collide with any existing targets that share
                       the module name (e.g. existing demo_sram() loops).
                       The generated FILES keep the bare module name —
                       only the Bazel labels get suffixed.
        **kwargs: Forwarded to the underlying genrule (tags, visibility).
    """
    tool = "@bazel-orfs//tools/memory_macro_scaler:memory_macro_scaler"

    outs = []
    for m in modules:
        outs += [m + ".lib", m + "_pre_layout.lib", m + ".lef"]

    cmd = (
        "$(location " + tool + ")" +
        " --tech-nm " + str(tech_nm) +
        " --out-dir $(RULEDIR)" +
        "".join([" --module " + m for m in modules]) +
        "".join([" --verilog $(location " + src + ")" for src in srcs])
    )
    native.genrule(
        name = name + "_files",
        srcs = srcs,
        outs = outs,
        cmd = cmd,
        tools = [tool],
        **kwargs
    )
    targets = []
    for m in modules:
        t = m + target_suffix
        scaled_macro_lib(
            name = t + "_lib",
            lib = m + ".lib",
            lib_pre_layout = m + "_pre_layout.lib",
        )
        native.filegroup(name = t + "_lef", srcs = [m + ".lef"])
        orfs_macro(
            name = t,
            lef = ":" + t + "_lef",
            lib = ":" + t + "_lib",
            module_top = m,
        )
        targets.append(":" + t)

    # Aggregate filegroup for convenience.
    native.filegroup(
        name = name,
        srcs = targets,
    )
