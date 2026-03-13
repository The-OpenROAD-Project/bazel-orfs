"""Rules for the building the OpenROAD-flow-scripts stages"""

load(
    "//private:attrs.bzl",
    _flow_provides = "flow_provides",
)
load(
    "//private:flow.bzl",
    _orfs_flow = "orfs_flow",
    _orfs_synth = "orfs_synth",
    _orfs_update = "orfs_update",
)
load(
    "//private:providers.bzl",
    _LoggingInfo = "LoggingInfo",
    _OrfsDepInfo = "OrfsDepInfo",
    _OrfsInfo = "OrfsInfo",
    _PdkInfo = "PdkInfo",
    _TopInfo = "TopInfo",
)
load(
    "//private:rules.bzl",
    _ABSTRACT_IMPL = "ABSTRACT_IMPL",
    _FINAL_STAGE_IMPL = "FINAL_STAGE_IMPL",
    _GENERATE_METADATA_STAGE_IMPL = "GENERATE_METADATA_STAGE_IMPL",
    _STAGE_IMPLS = "STAGE_IMPLS",
    _TEST_STAGE_IMPL = "TEST_STAGE_IMPL",
    _UPDATE_RULES_IMPL = "UPDATE_RULES_IMPL",
    _orfs_abstract = "orfs_abstract",
    _orfs_cts = "orfs_cts",
    _orfs_deps = "orfs_deps",
    _orfs_final = "orfs_final",
    _orfs_floorplan = "orfs_floorplan",
    _orfs_generate_metadata = "orfs_generate_metadata",
    _orfs_grt = "orfs_grt",
    _orfs_macro = "orfs_macro",
    _orfs_pdk = "orfs_pdk",
    _orfs_place = "orfs_place",
    _orfs_route = "orfs_route",
    _orfs_run = "orfs_run",
    _orfs_test = "orfs_test",
    _orfs_update_rules = "orfs_update_rules",
)
load(
    "//private:stages.bzl",
    _ALL_STAGES = "ALL_STAGES",
    _ALL_STAGE_TO_VARIABLES = "ALL_STAGE_TO_VARIABLES",
    _ALL_VARIABLE_TO_STAGES = "ALL_VARIABLE_TO_STAGES",
    _BAZEL_STAGE_TO_VARIABLES = "BAZEL_STAGE_TO_VARIABLES",
    _BAZEL_VARIABLE_TO_STAGES = "BAZEL_VARIABLE_TO_STAGES",
    _ORFS_VARIABLE_TO_STAGES = "ORFS_VARIABLE_TO_STAGES",
    _get_sources = "get_sources",
    _get_stage_args = "get_stage_args",
)
load(
    "//private:utils.bzl",
    _flatten = "flatten",
    _set = "set",
)

# Providers
OrfsInfo = _OrfsInfo
PdkInfo = _PdkInfo
TopInfo = _TopInfo
OrfsDepInfo = _OrfsDepInfo
LoggingInfo = _LoggingInfo

# Utils
flatten = _flatten
set = _set

# Stages
ALL_STAGES = _ALL_STAGES
ALL_STAGE_TO_VARIABLES = _ALL_STAGE_TO_VARIABLES
ALL_VARIABLE_TO_STAGES = _ALL_VARIABLE_TO_STAGES
BAZEL_STAGE_TO_VARIABLES = _BAZEL_STAGE_TO_VARIABLES
BAZEL_VARIABLE_TO_STAGES = _BAZEL_VARIABLE_TO_STAGES
ORFS_VARIABLE_TO_STAGES = _ORFS_VARIABLE_TO_STAGES
get_stage_args = _get_stage_args
get_sources = _get_sources

# Attrs
flow_provides = _flow_provides

# Rules
orfs_pdk = _orfs_pdk
orfs_macro = _orfs_macro
orfs_deps = _orfs_deps
orfs_run = _orfs_run
orfs_test = _orfs_test
orfs_floorplan = _orfs_floorplan
orfs_place = _orfs_place
orfs_cts = _orfs_cts
orfs_grt = _orfs_grt
orfs_route = _orfs_route
orfs_final = _orfs_final
orfs_generate_metadata = _orfs_generate_metadata
orfs_update_rules = _orfs_update_rules
orfs_abstract = _orfs_abstract
STAGE_IMPLS = _STAGE_IMPLS
FINAL_STAGE_IMPL = _FINAL_STAGE_IMPL
GENERATE_METADATA_STAGE_IMPL = _GENERATE_METADATA_STAGE_IMPL
UPDATE_RULES_IMPL = _UPDATE_RULES_IMPL
TEST_STAGE_IMPL = _TEST_STAGE_IMPL
ABSTRACT_IMPL = _ABSTRACT_IMPL

# Flow macros
orfs_flow = _orfs_flow
orfs_synth = _orfs_synth
orfs_update = _orfs_update
