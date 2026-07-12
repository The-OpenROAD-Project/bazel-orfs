load("//:openroad.bzl", "orfs_flow", "orfs_synth")

# The slang yosys plugin (slang.so) is provided from BCR sv-elab via
# orfs.default(yosys_plugins=...) in MODULE.bazel.
orfs_flow(
    name = "test",
    abstract_stage = "place",
    arguments = {
        "CORE_UTILIZATION": "10",
        "SYNTH_HDL_FRONTEND": "slang",
    },
    sources = {
        "SDC_FILE": ["constraints.sdc"],
    },
    verilog_files = [
        "test.sv",
    ],
)

# Regression coverage for the slang blackboxed-module path (the sv-elab
# slang-11 failure class from OpenROAD #10884, where --ignore-unknown-modules
# was rejected). Exercises SYNTH_BLACKBOXES + --empty-blackboxes through the
# slang frontend; canonicalize + synth only (save_odb = False: the blackboxed
# leaf has no LEF master). A future sv-elab bump that breaks blackboxing fails
# here in CI.
orfs_synth(
    name = "blackbox_synth",
    arguments = {
        "SYNTH_BLACKBOXES": "leaf",
        "SYNTH_HDL_FRONTEND": "slang",
        "SYNTH_SLANG_ARGS": "--empty-blackboxes",
    },
    module_top = "blackbox_top",
    save_odb = False,
    sources = {
        "SDC_FILE": ["constraints.sdc"],
    },
    verilog_files = ["blackbox.sv"],
)
