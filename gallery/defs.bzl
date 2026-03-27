"""Flow macros for the OpenROAD Demo Gallery.

These macros provide common settings and patterns used across demo projects,
following the hierarchical synthesis approach from megaboom.

Gallery image macros are in gallery.bzl.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load("@bazel-orfs//:sweep.bzl", _orfs_sweep = "orfs_sweep")
load("@bazel_skylib//rules:build_test.bzl", "build_test")

# Applied to all projects automatically. Not intended for per-project override.
_GLOBAL_SETTINGS = {
    # https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/pull/3797
    "SYNTH_REPEATABLE_BUILD": "1",
    # slang is MUCH faster because .rtlil individualization works.
    "SYNTH_HDL_FRONTEND": "slang",
    # Don't individualize in synthesis, we'd have to run abc once per instance
    "SYNTH_SLANG_ARGS": "--disable-instance-caching=false",
    "OPENROAD_HIERARCHICAL": "1",
    "SYNTH_MOCK_LARGE_MEMORIES": "1",
}

_LINT_TOOLS = {
    "openroad": "@lint-openroad//src/bin:openroad",
    "yosys": "@lint-yosys//src/bin:yosys",
}

_ALL_STAGES = [
    "synth",
    "floorplan",
    "place",
    "cts",
    "grt",
    "route",
    "final",
]

def _add_lint_targets(name, stages, base_tags):
    """Add lint flow test + A/B comparison tests.

    Two separate concerns:
    1. Lint build test — verifies the lint flow completes (always runs)
    2. A/B comparison — compares real vs lint outputs (tagged with base_tags
       since it depends on the base flow completing)
    """

    # Lint flow build test: verify last stage completes
    last = stages[-1]
    build_test(
        name = name + "_lint_test",
        targets = [":" + name + "_lint_" + last],
        tags = base_tags,
    )

    # A/B comparison tests (depends on base flow, so uses base_tags)
    for stage in stages:
        native.py_test(
            name = name + "_" + stage + "_lint_compare",
            srcs = ["//smoketest:mock_compare_test.py"],
            args = [
                "--stage",
                stage,
                "--design",
                name,
            ],
            data = [
                ":" + name + "_" + stage,
                ":" + name + "_lint_" + stage,
            ],
            main = "mock_compare_test.py",
            tags = base_tags,
        )

def demo_flow(
        name,
        verilog_files,
        pdk = None,
        arguments = {},
        macros = [],
        substeps = False,
        lint = False,
        base_tags = ["manual"],
        **kwargs):
    """Create an orfs_flow with demo gallery defaults.

    Global settings (slang frontend, hierarchical flow, mock memories) are
    applied automatically. All other settings — placement density, utilization,
    timing flags — should be set explicitly in each project's BUILD.bazel
    via the arguments dict so they are visible and easy to tweak.

    Args:
        name: Target name (should match the Verilog top module)
        verilog_files: List of Verilog source file labels
        pdk: PDK label to use (default: None = use bazel-orfs default, which is asap7)
        arguments: ORFS arguments — all project-specific settings go here
        macros: List of macro abstract targets for hierarchical designs
        substeps: If True, generate per-substep targets for debugging iteration
        lint: If True, add lint variant alongside real flow
        base_tags: Tags for base (real) variant and A/B comparison targets
        **kwargs: Additional arguments passed to orfs_flow/orfs_sweep
    """
    merged_args = _GLOBAL_SETTINGS | arguments
    if not lint:
        flow_kwargs = dict(
            name = name,
            verilog_files = verilog_files,
            arguments = merged_args,
            macros = macros,
            substeps = substeps,
            **kwargs
        )
        if pdk:
            flow_kwargs["pdk"] = pdk
        orfs_flow(**flow_kwargs)
    else:
        sweep_kwargs = dict(
            name = name,
            verilog_files = verilog_files,
            arguments = merged_args,
            macros = macros,
            substeps = substeps,
            stage = "final",
            sweep = {
                "base": {},
            },
            other_variants = {
                "lint": _LINT_TOOLS,
            },
            tags = base_tags,
            **kwargs
        )
        if pdk:
            sweep_kwargs["pdk"] = pdk
        _orfs_sweep(**sweep_kwargs)

        _add_lint_targets(name, _ALL_STAGES, base_tags)

def demo_sram(
        name,
        verilog_files,
        mock_area,
        abstract_stage = "cts",
        pdk = None,
        arguments = {},
        substeps = False,
        lint = False,
        lint_tags = [],
        base_tags = ["manual"],
        **kwargs):
    """Create an orfs_flow for a sub-macro (SRAM, register file, etc).

    Builds the macro through the specified abstract_stage and generates
    LEF/LIB abstracts that can be used by a parent orfs_flow via the
    macros parameter.

    Args:
        name: Module name
        verilog_files: Verilog sources for this macro
        mock_area: Float scale factor for mock area estimation
        abstract_stage: Stage at which to generate abstracts (default: "cts")
        pdk: PDK (default: None = bazel-orfs default)
        arguments: ORFS arguments — must include CORE_UTILIZATION (or DIE_AREA),
            PLACE_DENSITY, and PDN_TCL (or provide PDN_TCL via sources).
            No defaults are injected beyond _GLOBAL_SETTINGS.
        substeps: If True, generate per-substep targets for debugging iteration
        lint: If True, add lint variant alongside real flow
        lint_tags: Tags for lint variant targets
        base_tags: Tags for base (real) variant targets
        **kwargs: Additional arguments passed to orfs_flow
    """
    merged_args = _GLOBAL_SETTINGS | arguments
    if not lint:
        flow_kwargs = dict(
            name = name,
            abstract_stage = abstract_stage,
            mock_area = mock_area,
            verilog_files = verilog_files,
            arguments = merged_args,
            substeps = substeps,
            **kwargs
        )
        if pdk:
            flow_kwargs["pdk"] = pdk
        orfs_flow(**flow_kwargs)
    else:
        # Can't use orfs_sweep with mock_area: sweep passes mock_area
        # to all variants, but mock_area.tcl uses real OpenROAD to read
        # the floorplan ODB — which is a text stub in the lint variant.
        # Instead, call orfs_flow twice: base with mock_area, lint without.
        # No variant for base — keeps target names like
        # tiny_sram_generate_abstract unchanged for macro refs.
        base_kwargs = dict(
            name = name,
            abstract_stage = abstract_stage,
            mock_area = mock_area,
            verilog_files = verilog_files,
            arguments = merged_args,
            substeps = substeps,
            tags = base_tags,
            **kwargs
        )
        if pdk:
            base_kwargs["pdk"] = pdk
        orfs_flow(**base_kwargs)

        lint_kwargs = dict(
            name = name,
            abstract_stage = abstract_stage,
            verilog_files = verilog_files,
            arguments = merged_args,
            variant = "lint",
            substeps = substeps,
            tags = lint_tags,
            openroad = _LINT_TOOLS["openroad"],
            yosys = _LINT_TOOLS["yosys"],
        )
        lint_kwargs.update(kwargs)
        if pdk:
            lint_kwargs["pdk"] = pdk
        orfs_flow(**lint_kwargs)

def demo_hierarchical(
        name,
        verilog_files,
        macros,
        pdk = None,
        arguments = {},
        substeps = False,
        lint = False,
        base_tags = ["manual"],
        **kwargs):
    """Create an orfs_flow for a hierarchical top-level design.

    This sets up hierarchical synthesis with macro placement, following
    the megaboom pattern for BoomTile.

    Args:
        name: Top-level module name
        verilog_files: Verilog sources
        macros: List of ":macro_generate_abstract" targets
        pdk: PDK (default: None = bazel-orfs default)
        arguments: ORFS arguments — must include SYNTH_HIERARCHICAL,
            MACRO_PLACE_HALO, PLACE_PINS_ARGS, and PDN_TCL (or via sources).
            No defaults are injected beyond _GLOBAL_SETTINGS.
        substeps: If True, generate per-substep targets for debugging iteration
        lint: If True, add lint variant alongside real flow
        base_tags: Tags for base (real) variant and A/B comparison targets
        **kwargs: Additional arguments passed to orfs_flow
    """
    merged_args = _GLOBAL_SETTINGS | arguments
    if not lint:
        flow_kwargs = dict(
            name = name,
            verilog_files = verilog_files,
            macros = macros,
            arguments = merged_args,
            substeps = substeps,
            **kwargs
        )
        if pdk:
            flow_kwargs["pdk"] = pdk
        orfs_flow(**flow_kwargs)
    else:
        sweep_kwargs = dict(
            name = name,
            verilog_files = verilog_files,
            arguments = merged_args,
            macros = macros,
            substeps = substeps,
            stage = "final",
            sweep = {
                "base": {},
            },
            other_variants = {
                "lint": _LINT_TOOLS,
            },
            tags = base_tags,
            **kwargs
        )
        if pdk:
            sweep_kwargs["pdk"] = pdk
        _orfs_sweep(**sweep_kwargs)

        # Hierarchical skips synth comparison (synth is at macro level)
        _add_lint_targets(name, _ALL_STAGES[1:], base_tags)
