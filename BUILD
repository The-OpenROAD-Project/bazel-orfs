load("@rules_oci//oci:defs.bzl", "oci_tarball")
load("//:openroad.bzl", "build_openroad")

# FIXME: this shouldn't be required
exports_files(glob(["*.mk"]))

exports_files(glob(["scripts/mem_dump.*"]))

exports_files(["mock_area.tcl"])

exports_files(["orfs"])

exports_files(["make_script.template.sh"])

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
    ],
    data = [
        ":util",
    ],
)

filegroup(
    name = "io",
    srcs = [
        "test/io.tcl",
    ],
    data = [
        ":util",
    ],
)

filegroup(
    name = "constraints-sram",
    srcs = [
        "test/constraints-sram.sdc",
    ],
    data = [
        ":util",
    ],
)

build_openroad(
    name = "tag_array_64x184",
    io_constraints = ":io-sram",
    mock_abstract = True,
    mock_area = 0.20,
    mock_stage = "floorplan",
    sdc_constraints = ":constraints-sram",
    stage_args = {
        "floorplan": [
            "CORE_UTILIZATION=40",
            "CORE_ASPECT_RATIO=2",
        ],
        "place": ["PLACE_DENSITY=0.65"],
    },
    verilog_files = ["test/rtl/tag_array_64x184.sv"],
)

build_openroad(
    name = "lb_32x128",
    io_constraints = ":io-sram",
    mock_abstract = True,
    mock_area = 1,
    mock_stage = "floorplan",
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
    mock_abstract = True,
    mock_stage = "grt",
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
