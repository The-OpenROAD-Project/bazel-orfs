load("//:openroad.bzl", "orfs_flow")

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
