"""stdcell_verilog: generate Verilator-simulable behavioral .v from a PDK's .lib + .lef.

Wraps the lib_to_verilog py_binary in a genrule so user BUILDs don't have
to thread `$(execpath)` and `$(location)` placeholders themselves.

A PDK like ASAP7 ships its stdcell behavioral Verilog as UDP primitive
tables that Verilator cannot simulate. `lib_to_verilog` regenerates the
sequential + combinational cells from .lib (Liberty `ff`, `latch`,
`function:`) and emits empty-module stubs for physical-only cells
(TAPCELL, FILLER, DECAP) detected in .lef. The result is a pair of
.v files suitable for `verilator_cc_library(srcs = …)`.

Usage:

    load("@bazel-orfs//tools/lib_to_verilog:lib_to_verilog.bzl",
         "stdcell_verilog")

    stdcell_verilog(
        name = "asap7_stdcell",
        libs = ["@orfs//flow:platforms/asap7/lib/NLDM/SEQ_RVT_TT.lib", ...],
        lefs = ["@orfs//flow:platforms/asap7/lef/asap7sc7p5t_28_R_1x.lef", ...],
    )

Outputs:
  <name>.v        — behavioral models for ff / latch / combinational cells
  <name>_empty.v  — empty-module stubs for cells present in .lef but absent
                    from any .lib (filler/tap/decap).
"""

def stdcell_verilog(
        name,
        libs,
        lefs = [],
        visibility = None,
        tags = []):
    """Emit behavioral Verilog for a PDK's stdcells from .lib + .lef.

    Args:
      name: Base name for the generated files. Outputs are `<name>.v` and
        `<name>_empty.v`.
      libs: List of Liberty .lib (or .lib.gz) labels.
      lefs: Optional list of LEF labels. Cells present in .lef but absent
        from any .lib are emitted as empty-module stubs in `<name>_empty.v`.
      visibility: Forwarded to the genrule.
      tags: Forwarded to the genrule.
    """
    out_v = name + ".v"
    out_empty_v = name + "_empty.v"
    cmd_parts = ["$(execpath @bazel-orfs//tools/lib_to_verilog:lib_to_verilog)"]
    for lib in libs:
        cmd_parts.append("--lib $(execpath {})".format(lib))
    for lef in lefs:
        cmd_parts.append("--lef $(execpath {})".format(lef))
    cmd_parts.append("--dff $(location :{})".format(out_v))
    cmd_parts.append("--empty $(location :{})".format(out_empty_v))

    native.genrule(
        name = name,
        srcs = libs + lefs,
        outs = [out_v, out_empty_v],
        cmd = " ".join(cmd_parts),
        tools = ["@bazel-orfs//tools/lib_to_verilog:lib_to_verilog"],
        visibility = visibility,
        tags = tags,
    )
