# Verilog generation rules (bazel-orfs-verilog)

This is a standalone Bazel module (`bazel-orfs-verilog`) providing rules for
FIRRTL-to-SystemVerilog conversion using firtool (CIRCT).

## Rules

| Rule | Purpose |
|------|---------|
| `fir_library` | Run a Chisel generator binary to produce a `.fir` file |
| `verilog_directory` | Convert `.fir` to a directory of split `.sv` files |
| `verilog_file` | Convert `.fir` to a single `.sv` file |
| `verilog_single_file_library` | Concatenate multiple `.sv` files into one |

## Usage

```starlark
load("@bazel-orfs-verilog:generate.bzl", "fir_library")
load("@bazel-orfs-verilog:verilog.bzl", "verilog_directory")

fir_library(
    name = "my_fir",
    generator = ":my_chisel_generator",
    opts = ["mypackage.MyModule"] + FIRTOOL_OPTS,
)

verilog_directory(
    name = "my_verilog",
    srcs = [":my_fir"],
    opts = FIRTOOL_OPTS,
)
```

## firtool flag consistency warning

firtool is invoked **twice** in the Chisel-to-Verilog pipeline:

1. **`fir_library`** -- the Chisel generator calls firtool internally (via
   `CHISEL_FIRTOOL_PATH`) to lower CHIRRTL to FIRRTL.
2. **`verilog_directory` / `verilog_file`** -- firtool converts the `.fir`
   to SystemVerilog.

The same firtool flags (especially `-disable-layers`,
`--disable-all-randomization`) **must** be passed to both invocations via
`opts`. If the two passes disagree, layer bind files or randomization
constructs in the `.fir` won't match what the second pass expects, producing
broken Verilog with dangling `` `include`` directives.

## Dependencies

Requires `@circt` (http_archive for firtool) and `@rules_verilator` (for
`VerilogInfo` provider).
