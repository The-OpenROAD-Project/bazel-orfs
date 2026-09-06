"""A/B study of OpenROAD PR 10662 as a fork/join walk over a placed design.

One orfs_run_executable per design. The arm -- which openroad binary runs
the walk -- is chosen at invocation time, not baked into the target:

    bazel run //study:asap7_aes_walk -- \
        OPENROAD_EXE=/abs/path/to/openroad \
        STUDY_ARM=base \
        RESULTS_OUT=/abs/path/to/out

That is deliberate. Baking the binary in would put an absolute local path
into a public repository and make the target unbuildable for anyone else;
make's last-wins argument handling gives the same BYO override with a
committed file that names no path at all.

KEEP_VARS=1 is not optional: the walk sets per-leaf variables that
erase_non_stage_variables would otherwise strip before cts and grt read
them.
"""

load("//:openroad.bzl", "orfs_run_executable")

STUDY_STAGES = [
    "synth",
    "floorplan",
    "place",
    "cts",
    "grt",
]

# Designs are keyed by the platform/design pair they come from, because
# the platform is a variable of the study (asap7 has a multi-Vt ladder
# and a different cell-size ladder from sky130hd) rather than a detail.
DESIGNS = {
    "asap7_riscv32i": "@orfs//flow/designs/asap7/riscv32i:riscv_top_place",
    "asap7_aes": "@orfs//flow/designs/asap7/aes:aes_cipher_top_place",
    "asap7_ibex": "@orfs//flow/designs/asap7/ibex:ibex_core_place",
    "asap7_jpeg": "@orfs//flow/designs/asap7/jpeg:jpeg_encoder_place",
    "asap7_ethmac": "@orfs//flow/designs/asap7/ethmac:ethmac_place",
    "sky130hd_aes": "@orfs//flow/designs/sky130hd/aes:aes_cipher_top_place",
    "sky130hd_ibex": "@orfs//flow/designs/sky130hd/ibex:ibex_core_place",
    "sky130hd_jpeg": "@orfs//flow/designs/sky130hd/jpeg:jpeg_encoder_place",
    "asap7_aes_multivt": "@orfs//flow/designs/asap7/aes_multivt:aes_cipher_top_place",
}

[
    orfs_run_executable(
        name = design + "_walk",
        src = src,
        arguments = {"KEEP_VARS": "1"},
        script = ":buffer_to_inverters.tcl",
        stages = STUDY_STAGES,
        tags = ["manual"],
    )
    for design, src in DESIGNS.items()
]

# Design-suitability probe: measures the conditions PR 10662's generator
# requires before it will emit a candidate at all -- a usable inverter
# after dont_use and cell_footprint filtering, buffers on violating paths,
# and something left to repair -- so designs are chosen by measurement
# rather than intuition. The footprint half is a platform property and
# costs no flow run, so it can rule a platform out before any compute is
# spent on it.
[
    orfs_run_executable(
        name = design + "_probe",
        src = src,
        arguments = {"KEEP_VARS": "1"},
        script = ":probe_buffer_to_inverters.tcl",
        stages = STUDY_STAGES,
        tags = ["manual"],
    )
    for design, src in DESIGNS.items()
]

exports_files([
    "buffer_to_inverters.tcl",
    "probe_buffer_to_inverters.tcl",
])
