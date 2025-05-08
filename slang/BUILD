load("//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "test",
    abstract_stage = "place",
    verilog_files = [
        "test.sv",
    ],
    arguments = {
        "SYNTH_HDL_FRONTEND" : "slang",
        "CORE_UTILIZATION" : "10",

    },
    sources = {
                       "SDC_FILE": ["constraints.sdc"],

    }
)
