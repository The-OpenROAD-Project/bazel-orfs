load("@rules_python//python:defs.bzl", "py_binary", "py_library")

# The sweep target itself (tagged manual). The full definition would
# enumerate every SWEEP_SHAPES entry in sweep_configs.py, synthesize a
# tiny SystemVerilog wrapper module per shape, drive it through an
# orfs_flow() targeting ASAP7, and feed the resulting .lib files into
# generate_sweep.py to produce the committed asap7_sweep.yaml. The
# per-shape orfs_flow()s are intentionally NOT declared here yet — they
# depend on ascenium's (or another consumer's) SystemVerilog memory
# generator, and we want the schema + Python pieces landed first so
# the shape of the contribution is visible before the slow part.
#
# Once the upstream SV generator is wired in, this target becomes:
#
#     py_binary(
#         name = "asap7_sweep",
#         srcs = ["generate_sweep.py"],
#         main = "generate_sweep.py",
#         args = [
#             "--output", "$(location :asap7_sweep.yaml)",
#             "--result-files",
#         ] + [
#             "$(location :ff_{rows}x{bits}_{ports}_wm{wm}_abstract)".format(
#                 rows=s["rows"], bits=s["bits"],
#                 ports=s["ports_key"], wm=s["write_mask_bits"],
#             )
#             for s in SWEEP_SHAPES
#         ],
#         data = [":ff_{rows}x{bits}_...".format(...) for s in SWEEP_SHAPES],
#         deps = [requirement("PyYAML")],
#         tags = ["manual"],
#     )
#
# For now we ship only generate_sweep.py and the result-harvest shape;
# running the sweep is a follow-up wiring step.

py_library(
    name = "generate_sweep_lib",
    srcs = ["generate_sweep.py"],
    imports = ["."],
    deps = ["@bazel-orfs-pip//pyyaml"],
)

py_binary(
    name = "generate_sweep",
    srcs = ["generate_sweep.py"],
    main = "generate_sweep.py",
    tags = ["manual"],
    visibility = ["//visibility:public"],
    deps = [":generate_sweep_lib"],
)

# bazel run //tools/memory_macro_scaler/characterization:pin_asap7_sweep
# regenerates asap7_sweep.yaml and writes it back into the source tree.
# Pins the ASAP7 sweep numbers into git so subsequent fit invocations
# pick them up without re-running the (slow) per-shape flows.
py_binary(
    name = "pin_asap7_sweep",
    srcs = ["pin_asap7_sweep.py"],
    main = "pin_asap7_sweep.py",
    tags = ["manual"],
    visibility = ["//visibility:public"],
    deps = [":generate_sweep_lib"],
)

exports_files(["asap7_sweep.yaml", "sweep_configs.py"])
