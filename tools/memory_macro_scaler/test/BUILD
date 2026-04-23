load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//test:provider_test_rule.bzl", "lib_pre_layout_test")
load("//tools/memory_macro_scaler:scale_macro.bzl", "scale_macro")

# Drive scale_macro() against hand-crafted tiny fixtures. No real flow runs.
scale_macro(
    name = "tiny_scaled",
    module_top = "tiny_128x64",
    reference_lef = "fixtures/tiny.lef",
    reference_lib_post_cts = "fixtures/tiny_post_cts.lib",
    reference_lib_pre_layout = "fixtures/tiny_pre_layout.lib",
)

# Single-input variant: simulates a place-stage source macro where only
# one reference .lib exists (no pre_layout sibling from the upstream
# abstract). The scaler still emits the dual pair by rewriting ck-insertion
# arcs from the idiomatic table.
scale_macro(
    name = "tiny_scaled_place_only",
    module_top = "tiny_128x64",
    reference_lef = "fixtures/tiny.lef",
    reference_lib_post_cts = "fixtures/tiny_post_cts.lib",
)

# (a) Analysis-level: the scaled orfs_macro() re-exposes OrfsInfo.lib_pre_layout.
lib_pre_layout_test(
    name = "scaled_macro_lib_pre_layout_test",
    target = ":tiny_scaled",
)

# (b) Runtime: the scaled orfs_macro() accumulates .lef + .lib.
sh_test(
    name = "scaled_macro_accumulation_test",
    srcs = ["macro_files_present_test.sh"],
    args = ["$(locations :tiny_scaled)"],
    data = [":tiny_scaled"],
)

# (c) Content: post-CTS ck-insertion > pre-layout, library names match.
sh_test(
    name = "scaled_macro_dual_char_content_test",
    srcs = ["dual_char_content_test.sh"],
    args = [
        "$(location :tiny_scaled.lib)",
        "$(location :tiny_scaled_pre_layout.lib)",
    ],
    data = [
        ":tiny_scaled.lib",
        ":tiny_scaled_pre_layout.lib",
    ],
)

# (d) Place-stage variant: same lib_pre_layout OrfsInfo-forwarding check.
lib_pre_layout_test(
    name = "scaled_macro_place_only_lib_pre_layout_test",
    target = ":tiny_scaled_place_only",
)

# (e) Place-stage variant: same content-diff — pre ≈ 0 < post-CTS.
#     Confirms the scaler synthesizes the dual from a single input.
sh_test(
    name = "scaled_macro_place_only_dual_char_content_test",
    srcs = ["dual_char_content_test.sh"],
    args = [
        "$(location :tiny_scaled_place_only.lib)",
        "$(location :tiny_scaled_place_only_pre_layout.lib)",
    ],
    data = [
        ":tiny_scaled_place_only.lib",
        ":tiny_scaled_place_only_pre_layout.lib",
    ],
)
