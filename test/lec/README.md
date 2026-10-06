# Logic equivalence checking with kepler-formal

The `lec_test` rule wraps [kepler-formal](https://github.com/nicedayzhu/kepler-formal)
for combinational logic equivalence checking (LEC) between gold (reference) and
gate (modified) Verilog netlists.

## Quick start

```starlark
load("//test/lec:lec.bzl", "lec_test")

lec_test(
    name = "my_lec_test",
    gold_verilog_files = [":generated.sv"],
    gate_verilog_files = ["rtl/MyModule.sv"],
)
```

Run by name:

    bazelisk test //path:my_lec_test

Every `lec_test` is `manual`: kepler-formal builds from source, too slow
for CI, and `//...` never reaches it. kepler-formal is a `dev_dependency`
of bazel-orfs, so the rule lives under `test/`, which a consumer never
loads; its dependencies not yet on the Bazel Central Registry come from
registries in bazel-orfs's `.bazelrc`, which a consumer never reads.
`//test/lec:equivalent_test` and `//test/lec:difference_test` check the
wrapper itself.

## Attributes

| Attribute | Default | Description |
|-----------|---------|-------------|
| `gold_verilog_files` | required | Gold (reference) Verilog files |
| `gate_verilog_files` | required | Gate (modified) Verilog files |
| `liberty_files` | `[]` | Liberty (.lib) files for cell definitions. Optional for RTL-to-RTL checks, required for post-synthesis gate netlists. |
| `frontend` | `"verilog"` | `verilog` for gate netlists (cells from `liberty_files`, combinational LEC; sequential instances must match by name), `sv` for SystemVerilog RTL (sequential check, SEC) |
| `expect_equivalent` | `True` | `False` for a test that proves a difference is caught |
| `log_level` | `"info"` | Log verbosity: `debug`, `info`, `warning`, `error` |

kepler-formal's exit status does not say whether the designs differ; the
test reads the verdict it logs.

## Requirements

kepler-formal operates on Verilog netlists and checks combinational
equivalence. The gold and gate netlists must satisfy:

- **No sequential boundary changes** between gold and gate
- **No name changes** for hierarchical instances, sequential instances, or
  top-level ports

## Bumping kepler-formal

kepler-formal is taken at its `main` (it is being fixed rapidly; never pin
an old release): the commit in the root `MODULE.bazel`'s `git_override`
and in the registry URL in the root `.bazelrc` move together, and the BCR
pull request registries there are copied from kepler-formal's own
`.bazelrc` at that commit.
