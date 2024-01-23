load("//:openroad.bzl", "build_openroad")

# FIXME: this shouldn't be required
exports_files(glob(["*.mk"]))
exports_files(glob(["scripts/mem_dump.*"]))
exports_files(["mock_area.tcl"])
exports_files(["orfs"])

build_openroad(
        name = "tag_array_64x184",
        io_constraints="io-sram.tcl",
        verilog_files=["rtl/tag_array_64x184.sv"],
        stage_sources={'synth': ["constraints-sram.sdc", "util.tcl"],
        'floorplan': ["util.tcl"],
        'place': ["util.tcl"]},
        stage_args={
                'floorplan': ['CORE_UTILIZATION=40',
                        'CORE_ASPECT_RATIO=2'],
                'place': ['PLACE_DENSITY=0.65']},
        mock_abstract=True,
        mock_stage='floorplan',
        mock_area=0.20,
        )

build_openroad(
        name = "L1MetadataArray",
        verilog_files=["rtl/L1MetadataArray.sv"],
        variant="test",
        macros=["tag_array_64x184"],
        stage_sources={'synth': ["constraints-top.sdc"],
        'floorplan': ["util.tcl"],
        'place': ["util.tcl"]},
        io_constraints="io.tcl",
        stage_args={
                'synth': ['SYNTH_HIERARCHICAL=1'],
                'floorplan': [
                        'CORE_UTILIZATION=3',
                        'RTLMP_FLOW=True',
                        'CORE_MARGIN=2',
                        ],
                'place': ['PLACE_DENSITY=0.20', 'PLACE_PINS_ARGS=-annealing'],
                },
        mock_abstract=True,
        mock_stage="grt"
        )
