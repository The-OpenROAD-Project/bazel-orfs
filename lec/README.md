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

Run from `lec/`:

    bazelisk test //path:my_lec_test

Every `lec_test` is `manual`: kepler-formal builds from source, with its
own toolchain, which is too slow for CI. `lec/` is a module of its own,
outside bazel-orfs's build (`.bazelignore`), because kepler-formal's
dependencies are not all on the Bazel Central Registry yet: the
registries that stand in for them are in `lec/.bazelrc` and must not reach
bazel-orfs or its consumers. `//test:equivalent_test` and
`//test:difference_test` check the wrapper itself.

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
an old release): the commit in `MODULE.bazel`'s `git_override` and in the
registry URL in `.bazelrc` move together, and `.bazelrc`'s BCR pull
request registries are copied from kepler-formal's own `.bazelrc` at that
commit.
