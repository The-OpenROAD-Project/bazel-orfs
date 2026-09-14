load("@coremark_joule_designs//:designs.bzl", "design")
load("@rules_shell//shell:sh_test.bzl", "sh_test")

design(
    config = "config.mk",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# AUTO_MEMORIES must reach the netlist, not merely run.
#
# The flow can infer cpuregs, generate a .lib and .lef for it, list it in
# blackboxes.txt and then synthesise the register file as flip-flops
# anyway -- completing, with plausible area and power, having measured a
# different design from the one asked for. This turns that into a failure.
filegroup(
    name = "netlist",
    srcs = [":cmj_picorv32_synth"],
    output_group = "1_2_yosys.v",
)

filegroup(
    name = "memories_dir",
    srcs = [":cmj_picorv32_synth"],
    output_group = "memories",
)

sh_test(
    name = "memories_applied_test",
    srcs = ["//test/coremark_joule/scripts:run_memories_check.sh"],
    args = [
        "$(location //test/coremark_joule/scripts:check_memories_applied)",
        "$(location :memories_dir)",
        "$(location :netlist)",
        # picorv32's register file: 32 registers of 32 bits.
        "cpuregs",
    ],
    data = [
        ":memories_dir",
        ":netlist",
        "//test/coremark_joule/scripts:check_memories_applied",
    ],
    tags = ["manual"],
)
