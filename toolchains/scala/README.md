# Chisel Bazel Rules

This directory contains Bazel rule wrappers for Chisel hardware design, built on top of [BCR rules_scala](https://github.com/bazelbuild/rules_scala).

## Architecture

The project uses **BCR rules_scala 7.1.5** from Bazel Central Registry as the underlying Scala toolchain. The Chisel wrappers (`chisel_binary`, `chisel_library`, `chisel_test`) provide a convenient API that:

- Automatically includes Chisel 7.2.0 and its dependencies
- Pre-configures Scala compiler options for Chisel
- Sets up Verilator and firtool for hardware simulation (tests only)
- Maintains API compatibility with existing BUILD files

## Usage

### chisel_library

Use for Chisel library targets:

```python
load("@bazel-orfs//toolchains/scala:chisel.bzl", "chisel_library")

chisel_library(
    name = "mylib",
    srcs = ["MyModule.scala"],
    visibility = ["//visibility:public"],
)
```

### chisel_binary

Use for Chisel binary targets (e.g., Verilog generators):

```python
load("@bazel-orfs//toolchains/scala:chisel.bzl", "chisel_binary")

chisel_binary(
    name = "generate_verilog",
    srcs = ["Generate.scala"],
    main_class = "myproject.Generate",
    deps = [":mylib"],
)
```

### chisel_test

Use for Chisel tests with Verilator support:

```python
load("@bazel-orfs//toolchains/scala:chisel.bzl", "chisel_test")

chisel_test(
    name = "mymodule_test",
    srcs = ["MyModuleTest.scala"],
    deps = [":mylib"],
)
```

**Note**: Tests run locally (`tags = ["local"]`) to allow Verilator to generate files during simulation.

## Dependencies

The following dependencies are automatically included:

- Chisel 7.2.0 (`org.chipsalliance.chisel`)
- Chisel plugin for Scala 2.13.17
- Circe (JSON library)
- Shapeless (generic programming)
- Cats (functional programming)

For tests, additional tools are provided:
- Verilator 5.036 (from BCR)
- firtool from CIRCT

## Verilator Integration

The `chisel_test` rule includes workarounds for BCR verilator compatibility:

1. **Runtime configuration generation**: Generates `verilated.mk` and `verilated_config.h` from templates at test runtime
2. **Path resolution**: Automatically sets `VERILATOR_ROOT`, `VERILATOR_BIN`, and `PATH`
3. **Forward compatibility**: Workarounds are conditional and will automatically disable when BCR verilator is fixed

These workarounds are based on previous fixes (commits 0a3c114, c58bf7d) and ensure tests work without manual configuration.

## Migration from Custom Toolchain

This project was migrated from a custom Scala toolchain (~1500 lines) to BCR rules_scala (~250 lines of wrappers) in early 2025. The Chisel API remained unchanged, requiring no modifications to BUILD files.

### Benefits of BCR Migration

- **Reduced maintenance**: No custom toolchain to maintain
- **Standard compliance**: Uses Bazel community standard
- **Easy upgrades**: Can upgrade rules_scala independently
- **Community support**: Can get help from wider Bazel community

### What Changed

**Deleted**:
- Custom Scala toolchain implementation (`impl/`, `args/`, `tools/`, etc.)
- Custom `scala_library`, `scala_binary` rule definitions

**Preserved**:
- Chisel wrapper API (`chisel_*` rules)
- All BUILD files using Chisel rules

**Modified**:
- `MODULE.bazel`: Uses BCR rules_scala 7.1.5
- `toolchains/scala/chisel.bzl`: Simplified to thin wrappers

## Bloop Integration (Disabled)

The bloop integration for IDE support is temporarily disabled during the BCR migration:

```python
# Temporarily disabled in BUILD file
# load("@bazel-orfs//toolchains/scala:scala_bloop.bzl", "scala_bloop")
# scala_bloop(name = "bloop", src = "blooplib")
```

To re-enable in the future, the `scala_bloop` rule needs to be updated to work with BCR rules_scala.

## Files

- **chisel.bzl**: Main implementation of `chisel_binary`, `chisel_library`, `chisel_test`
- **scala_bloop.bzl**: Bloop integration (currently disabled)
- **BUILD.bazel**: Example usage (empty after migration)
- **README.md**: This file

## See Also

- [rules_scala documentation](https://github.com/bazelbuild/rules_scala)
- [Chisel documentation](https://www.chisel-lang.org/)
- [Verilator documentation](https://verilator.org/)
