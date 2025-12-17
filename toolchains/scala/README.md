# Chisel Bazel Rules

This directory contains Bazel rule wrappers for Chisel hardware design, built on top of [BCR rules_scala](https://github.com/bazelbuild/rules_scala).

## Architecture

The project uses **BCR rules_scala 7.1.5** from Bazel Central Registry as the underlying Scala toolchain. The Chisel wrappers (`chisel_binary`, `chisel_library`, `chisel_test`) provide a convenient API that:

- Automatically includes Chisel 7.2.0 and its dependencies
- Pre-configures Scala compiler options for Chisel
- Sets up Verilator and firtool for hardware simulation (tests only)

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

## IDE Support with Bazel BSP

This project uses [Bazel BSP](https://github.com/JetBrains/bazel-bsp) (Build Server Protocol) for IDE integration with Metals.

### Quick Setup

1. **Install Bazel BSP**:
   ```bash
   cs install bsp
   ```

2. **Initialize BSP**:
   ```bash
   cd /path/to/bazel-orfs-local
   bsp
   ```

3. **Configure targets** (`.bazelproject` in project root):
   ```
   targets:
       //:blooplib
       //chisel:all
       //sby:all

   allow_manual_targets_sync: false
   derive_targets_from_directories: false

   enabled_rules:
       rules_scala
       rules_java
       rules_jvm
   ```

4. **Build project first**:
   ```bash
   bazel build //chisel:codegenlib //chisel:applicationlib
   ```

5. **Open in VSCode** and Metals will auto-connect to BSP

### Troubleshooting

**No targets found**:
- Verify `.bazelproject` exists in project root
- Check targets: `bazel query "//chisel:all"`
- Rebuild BSP index: VSCode → "Metals: Import Build"

**Metals doesn't connect**:
- Ensure `bsp` is in PATH: `which bsp`
- Check `.bsp/bazelbsp.json` exists
- Restart: VSCode → "Metals: Restart Build Server"

**No IntelliSense**:
- Wait for initial indexing (check status bar)
- Verify build succeeds: `bazel build //chisel:codegenlib`
- Check logs: VSCode → Output → Metals

### Resources

- [Metals Bazel Documentation](http://scalameta.org/metals/docs/build-tools/bazel/)
- [Bazel BSP Server](https://github.com/JetBrains/bazel-bsp)
- [BSP Protocol Specification](https://build-server-protocol.github.io/)

## See Also

- [rules_scala documentation](https://github.com/bazelbuild/rules_scala)
- [Chisel documentation](https://www.chisel-lang.org/)
- [Verilator documentation](https://verilator.org/)
