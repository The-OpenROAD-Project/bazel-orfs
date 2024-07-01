load("//:openroad.bzl", "synth")

synth(
    name = "test_synth",
    module_top = "tag_array_64x184",
    arguments = {
        "SDC_FILE": "$(location //:constraints-sram)",
    },
    data = [
        "//:constraints-sram",
    ],
    verilog_files = [":rtl/tag_array_64x184.sv"],
)
