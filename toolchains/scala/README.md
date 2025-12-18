# Chisel Bazel Rules

This directory contains Bazel rule wrappers for Chisel hardware design, built on top of [BCR rules_scala](https://github.com/bazelbuild/rules_scala).

## Architecture

The project uses **BCR rules_scala 7.1.5 or newer** (as per `MODULE.bazel`) from Bazel Central Registry as the underlying Scala toolchain. The Chisel wrappers (`chisel_binary`, `chisel_library`, `chisel_test`) provide a convenient API that:

* Automatically includes Chisel and its dependencies
* Pre-configures Scala compiler options for Chisel
* Sets up Verilator and firtool for hardware simulation (tests only)

## Usage

For another minimal working example, please refer to [bazel-chisel-verilator-openroad-demo](https://github.com/MrAMS/bazel-chisel-verilator-openroad-demo).

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

## Verilator Integration

The `chisel_test` rule includes workarounds for BCR verilator compatibility:

1. **Runtime configuration generation**: Generates `verilated.mk` and `verilated_config.h` from templates at test runtime
2. **Path resolution**: Automatically sets `VERILATOR_ROOT`, `VERILATOR_BIN`, and `PATH`
3. **Forward compatibility**: Workarounds are conditional and will automatically disable when BCR verilator is fixed

## IDE Support with Bazel BSP

This project uses [Bazel BSP](https://github.com/JetBrains/bazel-bsp) (Build Server Protocol) for IDE integration. Modern editors like **Zed**, **VS Code**, and **IntelliJ IDEA** can automatically detect and initialize the BSP server via Metals or their respective plugins without manual installation.

### Quick Setup

1. **Set up your MODULE.bazel** Copy relevant bits from bazel-orfs MODULE.bazel, don't forget to search bazel-orfs for `semanticdb` and set up the bits in MODULE.bazel as well as BUILD target.

1. **Configure targets** (`.bazelproject` in project root):
Ensure your `.bazelproject` lists the targets you want to index. You check this [doc](https://ij.bazel.build/docs/project-views.html) more information.

2. **Open in Editor**:
Open the project directory in your preferred editor (VS Code, Zed, etc.). The editor (via Metals) will detect the `.bazelproject` file and automatically initialize the Bazel BSP connection.

### Troubleshooting

Run the bsp setup script, it will diagnose your setup and clean (delete) various files:

    bazelisk run @bazel-orfs//:bsp

### No targets found

* Verify `.bazelproject` exists in project root
* Check targets validity: `bazel query "//chisel:all"`
* Re-import build:
* **VS Code**: "Metals: Import Build"
* **Zed**: Trigger a build server reconnect or restart the editor

### No IntelliSense

* Wait for initial indexing (check status bar)
* Verify build succeeds via command line
* Check logs: Editor Output -> Metals
