"""scale_macro: scale a reference dual-characterized macro to idiomatic ASAP7.

Public API: the scale_macro() macro below. Composes a genrule that runs
memory_macro_scaler.py on a reference `.lib` pair + `.lef`, wraps the two
scaled `.lib` files into a scaled_macro_lib (so the OrfsInfo provider keeps
carrying both lib and lib_pre_layout), and hands that + the scaled `.lef`
to orfs_macro().
"""

load("//:openroad.bzl", "orfs_macro")
load(":scaled_macro_lib.bzl", "scaled_macro_lib")

def scale_macro(
        name,
        reference_lib_post_cts,
        reference_lef,
        module_top,
        reference_lib_pre_layout = None,
        **kwargs):
    """Scale a reference characterization and wrap it as an orfs_macro().

    Dual-input mode (typical): pass both reference_lib_post_cts (from the
    post-CTS abstract) and reference_lib_pre_layout (from the auto-emitted
    post-place sibling, present when the source orfs_flow's abstract_stage
    is past "place"). Both scaled outputs come from their respective
    inputs, preserving any shape differences between the two.

    Single-input mode (place-stage macros): omit reference_lib_pre_layout
    (or pass None). The source orfs_flow's abstract_stage = "place"
    produces only one .lib — ideal-clock at post-place. Pass it as
    reference_lib_post_cts anyway; the scaler synthesizes the pre-layout
    output by rewriting clock-insertion arcs to 0 and the post-CTS output
    by rewriting them to the idiomatic post-CTS insertion latency from
    the built-in ASAP7 table. The input's own clock-insertion values are
    not load-bearing — the scaler overwrites them from the idiomatic
    table regardless.

    Args:
        name: Base target name. Creates `<name>` (orfs_macro), `<name>_lib`
              (scaled_macro_lib providing OrfsInfo), `<name>_lef`
              (filegroup), `<name>_files` (the genrule), and the scaled
              files `<name>.lib`, `<name>_pre_layout.lib`, `<name>.lef`.
        reference_lib_post_cts: Label providing the reference .lib. In
              dual-input mode this is the post-CTS lib; in single-input
              mode it is the (ideal-clock) post-place lib.
        reference_lef: Label providing the reference .lef.
        module_top: The Verilog module name the macro implements.
        reference_lib_pre_layout: Optional label providing the reference
              pre-layout (post-place, ideal-clock) .lib. Pass when the
              upstream orfs_flow auto-emits a pre_layout sibling
              abstract. Leave as None for place-stage macros.
        **kwargs: Forwarded to the genrule (e.g. tags, visibility).
    """
    tool = "@bazel-orfs//tools/memory_macro_scaler:memory_macro_scaler"
    srcs = [reference_lib_post_cts, reference_lef]
    cmd_parts = [
        "$(location " + tool + ")",
        " --in-lib-post-cts    $(location " + reference_lib_post_cts + ")",
        " --in-lef             $(location " + reference_lef + ")",
        " --out-lib-post-cts   $(location " + name + ".lib)",
        " --out-lib-pre-layout $(location " + name + "_pre_layout.lib)",
        " --out-lef            $(location " + name + ".lef)",
    ]
    if reference_lib_pre_layout != None:
        srcs.append(reference_lib_pre_layout)
        cmd_parts.insert(
            2,
            " --in-lib-pre-layout  $(location " + reference_lib_pre_layout + ")",
        )

    native.genrule(
        name = name + "_files",
        srcs = srcs,
        outs = [
            name + ".lib",
            name + "_pre_layout.lib",
            name + ".lef",
        ],
        cmd = "".join(cmd_parts),
        tools = [tool],
        **kwargs
    )
    scaled_macro_lib(
        name = name + "_lib",
        lib = name + ".lib",
        lib_pre_layout = name + "_pre_layout.lib",
    )
    native.filegroup(
        name = name + "_lef",
        srcs = [name + ".lef"],
    )
    orfs_macro(
        name = name,
        lef = ":" + name + "_lef",
        lib = ":" + name + "_lib",
        module_top = module_top,
    )
