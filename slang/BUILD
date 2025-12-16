load("//:openroad.bzl", "orfs_flow")

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
