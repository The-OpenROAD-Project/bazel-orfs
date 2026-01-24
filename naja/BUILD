load("//:openroad.bzl", "orfs_deps", "orfs_synth")
load("//:orfs_libs.bzl", "orfs_libs")

orfs_synth(
    name = "foo_synth",
    module_top = "foo",
    sources = {
        "SDC_FILE": [":constraints.sdc"],
    },
    verilog_files = ["dirty.v"],
)

orfs_synth(
    name = "dirty_synth",
    arguments = {
        "SYNTH_BLACKBOXES": "foo",
    },
    module_top = "dirty",
    sources = {
        "SDC_FILE": [":constraints.sdc"],
    },
    verilog_files = ["dirty.v"],
)

orfs_deps(
    name = "dirty_synth_deps",
    src = ":dirty_synth",
)

orfs_libs(
    name = "dirty_synth_libs",
    src = ":dirty_synth",
)

MODULES = [
    "dirty",
    "foo",
]

[filegroup(
    name = "{}_netlist".format(name),
    srcs = [":{}_synth".format(name)],
    output_group = "1_2_yosys.v",
) for name in [
    "dirty",
    "foo",
]]

filegroup(
    name = "netlist",
    srcs = ["{}_netlist".format(name) for name in MODULES],
)

filegroup(
    name = "dirty_vars",
    srcs = [":dirty_synth"],
    output_group = "1_synth.vars",
)

py_binary(
    name = "naja_clean",
    srcs = ["naja_clean.py"],
    deps = [
        "@bazel-orfs-pip//najaeda",
        "@bazel-orfs-pip//pyyaml",
    ],
)

genrule(
    name = "cleaned_synth",
    srcs = [
        ":dirty_synth_libs",
        ":dirty_vars",
        ":netlist",
    ],
    outs = ["cleaned.v"],
    cmd = """
    set -ex
    $(execpath :naja_clean) \
      $(location :dirty_vars) \
      $(location :cleaned.v) \
      $(locations :netlist) \
""",
    tags = ["manual"],
    tools = [":naja_clean"],
)
