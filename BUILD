load("@rules_oci//oci:defs.bzl", "oci_tarball")
load("//:openroad.bzl", "add_options_all_stages", "build_openroad", "create_out_rule")

# FIXME: this shouldn't be required
exports_files(glob(["*.mk"]))

exports_files(glob(["scripts/mem_dump.*"]))

exports_files(["mock_area.tcl"])

exports_files([
    "orfs",
    "out_script",
])

exports_files(glob(["test/**/*.sv", "test/**/*.sdc"]), visibility = [":__subpackages__"])

# Config for remote execution
config_setting(
    name = "remote_exec",
    values = {"define": "REMOTE=1"},
    visibility = ["//visibility:public"],
)

create_out_rule()

filegroup(
    name = "util",
    srcs = [
        "test/util.tcl",
    ],
)

filegroup(
    name = "io-sram",
    srcs = [
        "test/io-sram.tcl",
        ":util",
    ],
    visibility = [":__subpackages__"],
)

filegroup(
    name = "io",
    srcs = [
        "test/io.tcl",
        ":util",
    ],
    visibility = [":__subpackages__"],
)

filegroup(
    name = "constraints-sram",
    srcs = [
        "test/constraints-sram.sdc",
        ":util",
    ],
    visibility = [":__subpackages__"],
)

build_openroad(
    name = "tag_array_64x184",
    io_constraints = ":io-sram",
    abstract_stage = "floorplan",
    sdc_constraints = ":constraints-sram",
    stage_args = {
        "floorplan": [
            "CORE_UTILIZATION=40",
            "CORE_ASPECT_RATIO=2",
        ],
        "place": ["PLACE_DENSITY=0.65"],
    },
    verilog_files = ["test/mock/tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)

build_openroad(
    name = "lb_32x128",
    io_constraints = ":io-sram",
    mock_area = 1,
    abstract_stage = "floorplan",
    sdc_constraints = ":constraints-sram",
    stage_args = {
        "floorplan": [
            "CORE_UTILIZATION=40",
            "CORE_ASPECT_RATIO=2",
        ],
        "place": ["PLACE_DENSITY=0.65"],
    },
    verilog_files = ["test/rtl/lb_32x128.sv"],
)

build_openroad(
    name = "L1MetadataArray",
    io_constraints = ":io",
    macros = ["tag_array_64x184"],
    abstract_stage = "grt",
    sdc_constraints = ":test/constraints-top.sdc",
    stage_args = {
        "synth": ["SYNTH_HIERARCHICAL=1"],
        "floorplan": [
            "CORE_UTILIZATION=3",
            "RTLMP_FLOW=True",
            "CORE_MARGIN=2",
            "MACRO_PLACE_HALO=30 30",
        ],
        "place": [
            "PLACE_DENSITY=0.20",
            "PLACE_PINS_ARGS=-annealing",
        ],
    },
    variant = "test",
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)

# buildifier: disable=duplicated-name
build_openroad(
    name = "L1MetadataArray",
    io_constraints = ":io",
    macros = [
        "tag_array_64x184",
        "lb_32x128",
    ],
    sdc_constraints = ":test/constraints-top.sdc",
    stage_args = add_options_all_stages(
        {
            "synth": ["SYNTH_HIERARCHICAL=1"],
            "floorplan": [
                "CORE_UTILIZATION=3",
                "RTLMP_FLOW=True",
                "CORE_MARGIN=2",
                "MACRO_PLACE_HALO=10 10",
            ],
            "place": [
                "PLACE_DENSITY=0.10",
                "PLACE_PINS_ARGS=-annealing",
            ],
        },
        ["SKIP_REPORT_METRICS=1"],
    ),
    variant = "test_gds",
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)

# buildifier: disable=duplicated-name
build_openroad(
    name = "L1MetadataArray",
    io_constraints = ":io",
    macros = ["tag_array_64x184"],
    sdc_constraints = ":test/constraints-top.sdc",
    stage_args = {
        "synth": ["SYNTH_HIERARCHICAL=1"],
        "floorplan": [
            "CORE_UTILIZATION=3",
            "RTLMP_FLOW=True",
            "CORE_MARGIN=2",
            "MACRO_PLACE_HALO=10 10",
        ],
        "place": [
            "PLACE_DENSITY=0.20",
            "PLACE_PINS_ARGS=-annealing",
        ],
    },
    variant = "full",
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)

oci_tarball(
    name = "orfs_env",
    image = "@orfs_image",
    repo_tags = ["openroad/flow-ubuntu22.04-builder:latest"],
)

sh_binary(
    name = "docker_shell",
    srcs = ["docker_shell.sh"],
    visibility = ["//visibility:public"],
)

# buildifier: disable=duplicated-name
build_openroad(
    name = "tag_array_64x184",
    external_pdk = "@external_pdk//asap7",
    io_constraints = ":io-sram",
    abstract_stage = "floorplan",
    sdc_constraints = ":constraints-sram",
    stage_args = {
        "floorplan": [
            "CORE_UTILIZATION=40",
            "CORE_ASPECT_RATIO=2",
        ],
        "place": ["PLACE_DENSITY=0.65"],
    },
    variant = "external_pdk",
    verilog_files = ["test/mock/tag_array_64x184.sv"],
)

# buildifier: disable=duplicated-name
build_openroad(
    name = "L1MetadataArray",
    external_pdk = "@external_pdk//asap7",
    io_constraints = ":io",
    macro_variants = {"tag_array_64x184": "external_pdk"},
    macros = ["tag_array_64x184"],
    abstract_stage = "grt",
    sdc_constraints = ":test/constraints-top.sdc",
    stage_args = {
        "synth": ["SYNTH_HIERARCHICAL=1"],
        "floorplan": [
            "CORE_UTILIZATION=3",
            "RTLMP_FLOW=True",
            "CORE_MARGIN=2",
            "MACRO_PLACE_HALO=30 30",
        ],
        "place": [
            "PLACE_DENSITY=0.20",
            "PLACE_PINS_ARGS=-annealing",
        ],
    },
    variant = "external_pdk",
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)
