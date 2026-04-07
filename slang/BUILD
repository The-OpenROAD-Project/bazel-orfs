load("//:openroad.bzl", "orfs_flow")

# TODO: re-enable once yosys-slang plugin is built separately
# (slang.so is not included in BCR yosys)
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
    tags = ["manual"],
    verilog_files = [
        "test.sv",
    ],
)
