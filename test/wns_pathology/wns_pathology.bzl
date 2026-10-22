"""One read of each ORFS design's global route, as ORFS configures it."""

load("@bazel-orfs//:openroad.bzl", "orfs_run")

# Every flow ORFS's designs declare at the pinned ORFS, "<package>:<top>"
# under flow/designs, from
#   bazelisk query 'attr(name, ".*_synth$", @orfs//flow/designs/...)'
# A block's flow sits in its parent's package.
FLOWS = [
    "asap7/aes:aes_cipher_top",
    "asap7/aes-block:aes_cipher_top",
    "asap7/aes-block:aes_rcon",
    "asap7/aes-block:aes_sbox",
    "asap7/aes-mbff:aes_cipher_top",
    "asap7/aes_lvt:aes_cipher_top",
    "asap7/chi_async_bridge:chi_async_bridge",
    "asap7/coralnpu:CoreMiniAxi",
    "asap7/coralnpu-exmem:CoreMiniAxi",
    "asap7/coralnpu-regfile:CoreMiniAxi",
    "asap7/coralnpu-regfile-exmem:CoreMiniAxi",
    "asap7/coralnpu-regfiles-exmem:CoreMiniAxi",
    "asap7/cva6:cva6",
    "asap7/cva6-regfile:cva6",
    "asap7/ethmac:ethmac",
    "asap7/ethmac_lvt:ethmac",
    "asap7/gcd:gcd",
    "asap7/gcd-ccs:gcd",
    "asap7/ibex:ibex_core",
    "asap7/ibex-regfile:ibex_core",
    "asap7/jpeg:jpeg_encoder",
    "asap7/jpeg_lvt:jpeg_encoder",
    "asap7/mock-alu:MockAlu",
    "asap7/picorv32:picorv32",
    "asap7/picorv32-regfile:picorv32",
    "asap7/riscv32i:riscv_top",
    "asap7/riscv32i-mock-sram:fakeram7_256x32",
    "asap7/riscv32i-mock-sram:riscv_top",
    "asap7/swerv_wrapper:swerv_wrapper",
    "asap7/swerv_wrapper-regfile:swerv_wrapper",
    "asap7/swerv_wrapper-yosys:swerv_wrapper",
    "asap7/tinyRocket:RocketTile",
    "asap7/tinyRocket-regfile:RocketTile",
    "asap7/tpu:tpu",
    "asap7/uart:uart",
    "gf180/aes:aes_cipher_top",
    "gf180/aes-hybrid:aes_cipher_top",
    "gf180/ibex:ibex_core",
    "gf180/jpeg:jpeg_encoder",
    "gf180/riscv32i:riscv",
    "gf180/uart-blocks:uart_rx",
    "gf180/uart-blocks:uart",
    "ihp-sg13g2/aes:aes_cipher_top",
    "ihp-sg13g2/gcd:gcd",
    "ihp-sg13g2/i2c-gpio-expander:I2cDeviceCtrl",
    "ihp-sg13g2/i2c-gpio-expander:I2cGpioExpanderTop",
    "ihp-sg13g2/ibex:ibex_core",
    "ihp-sg13g2/jpeg:jpeg_encoder",
    "ihp-sg13g2/riscv32i:riscv",
    "ihp-sg13g2/spi:spi",
    "nangate45/aes:aes_cipher_top",
    "nangate45/ariane133:ariane",
    "nangate45/ariane136:ariane",
    "nangate45/black_parrot:black_parrot",
    "nangate45/bp_be_top:bp_be_top",
    "nangate45/bp_fe_top:bp_fe_top",
    "nangate45/bp_multi_top:bp_multi_top",
    "nangate45/bp_quad:bsg_chip",
    "nangate45/cva6:cva6",
    "nangate45/dynamic_node:dynamic_node_top_wrap",
    "nangate45/gcd:gcd",
    "nangate45/ibex:ibex_core",
    "nangate45/jpeg:jpeg_encoder",
    "nangate45/mempool_group:mempool_group",
    "nangate45/picorv32:picorv32",
    "nangate45/swerv:swerv",
    "nangate45/swerv_wrapper:swerv_wrapper",
    "nangate45/tinyRocket:RocketTile",
    "nangate45/tpu:tpu",
    "sky130hd/aes:aes_cipher_top",
    "sky130hd/chameleon:soc_core",
    "sky130hd/gcd:gcd",
    "sky130hd/ibex:ibex_core",
    "sky130hd/jpeg:jpeg_encoder",
    "sky130hd/microwatt:microwatt",
    "sky130hd/riscv32i:riscv",
    "sky130hs/aes:aes_cipher_top",
    "sky130hs/gcd:gcd",
    "sky130hs/ibex:ibex_core",
    "sky130hs/jpeg:jpeg_encoder",
    "sky130hs/riscv32i:riscv",
]

def target_name(flow):
    """asap7/gcd:gcd -> asap7_gcd_gcd: one name per flow."""
    return flow.replace("/", "_").replace("-", "_").replace(":", "_")

def wns_pathology_reads(name):
    """An orfs_run per flow, reading its _grt.

    Args:
      name: a filegroup of every flow's global route, for asking the remote
        cache which of them it holds (tools/cache_evidence capture takes
        one target).
    """
    for flow in FLOWS:
        read = target_name(flow)
        orfs_run(
            name = read,
            src = "@orfs//flow/designs/%s_grt" % flow,
            outs = [read + ".tsv"],
            script = ":read.tcl",
            tags = ["manual"],
            user_arguments = {"OUT": "$(location %s.tsv)" % read},
            user_sources = {"FLOOR_TCL": ["//tools/headroom:report_floor_cycles.tcl"]},
        )
    native.filegroup(
        name = name,
        srcs = ["@orfs//flow/designs/%s_grt" % flow for flow in FLOWS],
        tags = ["manual"],
    )
    for flow in FLOWS:
        read = target_name(flow) + "_endpoints"
        orfs_run(
            name = read,
            src = "@orfs//flow/designs/%s_grt" % flow,
            outs = [read + ".tsv"],
            script = ":endpoints.tcl",
            tags = ["manual"],
            user_arguments = {"OUT": "$(location %s.tsv)" % read},
        )
    native.filegroup(
        name = "endpoints",
        srcs = [":" + target_name(flow) + "_endpoints" for flow in FLOWS],
        tags = ["manual"],
    )
    native.filegroup(
        name = "reads",
        srcs = [":" + target_name(flow) for flow in FLOWS],
        tags = ["manual"],
    )
