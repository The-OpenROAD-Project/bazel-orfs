# Logic equivalence checking with kepler-formal

The `lec_test` rule wraps [kepler-formal](https://github.com/nicedayzhu/kepler-formal)
for combinational logic equivalence checking (LEC) between gold (reference) and
gate (modified) Verilog netlists.

## Quick start

```starlark
load("//lec:lec.bzl", "lec_test")

lec_test(
    name = "my_lec_test",
    gold_verilog_files = [":generated.sv"],
    gate_verilog_files = ["rtl/MyModule.sv"],
)
```

Run:

    bazelisk test :my_lec_test

## Attributes

| Attribute | Default | Description |
|-----------|---------|-------------|
| `gold_verilog_files` | required | Gold (reference) Verilog files |
| `gate_verilog_files` | required | Gate (modified) Verilog files |
| `liberty_files` | `[]` | Liberty (.lib) files for cell definitions. Optional for RTL-to-RTL checks, required for post-synthesis gate netlists. |
| `log_level` | `"info"` | Log verbosity: `debug`, `info`, `warning`, `error` |

## Requirements

kepler-formal operates on Verilog netlists and checks combinational
equivalence. The gold and gate netlists must satisfy:

- **No sequential boundary changes** between gold and gate
- **No name changes** for hierarchical instances, sequential instances, or
  top-level ports

## Temporary home

This directory is hosted in bazel-orfs temporarily until the kepler-formal
repository provides native Bazel support. See
[TESTING.md](../TESTING.md#sub-modules-bazelignore) for details.
