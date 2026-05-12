load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//tools/lib_to_verilog:lib_to_verilog.bzl", "stdcell_verilog")

# Integration smoke for stdcell_verilog() against hand-crafted tiny
# fixtures. No real PDK fetch. Fast: the underlying py_binary runs in
# milliseconds.
stdcell_verilog(
    name = "tiny_stdcell",
    lefs = ["tiny.lef"],
    libs = ["tiny.lib"],
)

sh_test(
    name = "stdcell_verilog_smoke_test",
    srcs = ["stdcell_verilog_smoke_test.sh"],
    args = [
        "$(location :tiny_stdcell.v)",
        "$(location :tiny_stdcell_empty.v)",
    ],
    data = [
        ":tiny_stdcell.v",
        ":tiny_stdcell_empty.v",
    ],
)
