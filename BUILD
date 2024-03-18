load("@rules_oci//oci:defs.bzl", "oci_tarball")
load("//:openroad.bzl", "build_openroad")

# FIXME: this shouldn't be required
exports_files(glob(["*.mk"]))

exports_files(glob(["scripts/mem_dump.*"]))

exports_files(["mock_area.tcl"])

exports_files(["orfs"])

exports_files(["make_script.template.sh"])

build_openroad(
    name = "tag_array_64x184",
    io_constraints = "io-sram.tcl",
    mock_abstract = True,
    mock_area = 0.20,
    mock_stage = "floorplan",
    stage_args = {
        "floorplan": [
            "CORE_UTILIZATION=40",
            "CORE_ASPECT_RATIO=2",
        ],
        "place": ["PLACE_DENSITY=0.65"],
    },
    stage_sources = {
        "synth": [
            "test/constraints-sram.sdc",
            "util.tcl",
        ],
        "floorplan": ["util.tcl"],
        "place": ["util.tcl"],
    },
    verilog_files = ["test/rtl/tag_array_64x184.sv"],
)

build_openroad(
    name = "L1MetadataArray",
    io_constraints = "io.tcl",
    macros = ["tag_array_64x184"],
    mock_abstract = True,
    mock_stage = "grt",
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
    stage_sources = {
        "synth": ["test/constraints-top.sdc"],
        "floorplan": ["util.tcl"],
        "place": ["util.tcl"],
    },
    variant = "test",
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)

oci_tarball(
    name = "orfs_env",
    image = "@orfs_image",
    repo_tags = ["bazel-orfs/orfs_env:latest"],
)
