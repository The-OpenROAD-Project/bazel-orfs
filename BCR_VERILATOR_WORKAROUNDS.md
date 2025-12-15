# BCR Verilator Workarounds

This document describes the workarounds implemented to fix `bazel test //chisel:life2_test` when using BCR (Bazel Central Registry) verilator package instead of the legacy `@verilator_binary`.

## Issues Fixed

### 1. Repository Reference Migration (@verilator_binary → @verilator)

**Problem**: References to the obsolete `@verilator_binary` repository caused build failures.

**Solution**:
- Updated `toolchains/scala/chisel.bzl:70` to use `@verilator//:bin/verilator` instead of `@verilator_binary` references
- Added `@verilator//:verilator_includes` to data dependencies

**Files Modified**: `toolchains/scala/chisel.bzl`

### 2. Environment Variable Processing Bug

**Problem**: The `_env_impl()` function in `scala_binary.bzl` calculated expanded environment variables but returned the original unexpanded dict.

**Solution**:
- Fixed `toolchains/scala/scala_binary.bzl:90` to return `expanded` instead of re-computing environment variables
- This ensures `CHISEL_FIRTOOL_PATH` is properly derived from `CHISEL_FIRTOOL_BINARY_PATH`

**Files Modified**: `toolchains/scala/scala_binary.bzl`

### 3. VERILATOR_ROOT Configuration

**Problem**: Chisel's svsim requires both `VERILATOR_BIN` and `VERILATOR_ROOT` environment variables, but `VERILATOR_ROOT` wasn't set.

**Solution**:
- Modified test wrapper script (scala_binary.bzl:199-214) to:
  - Calculate runfiles directory from script location
  - Set `VERILATOR_ROOT` to `$RUNFILES_DIR/verilator+`
  - Convert `VERILATOR_BIN` from absolute path to relative path `bin/verilator` (as expected by chisel)

**Files Modified**: `toolchains/scala/scala_binary.bzl`

### 4. Missing verilated.mk File

**Problem**: BCR verilator package doesn't generate `verilated.mk` from `verilated.mk.in` template.

**Workaround**:
- Test wrapper script generates `verilated.mk` at runtime using sed to replace autoconf placeholders:
  ```bash
  sed 's/@AR@/ar/g; s/@CXX@/g++/g; s/@LINK@/g++/g; s/@OBJCACHE@//g; ...' \
    verilated.mk.in > verilated.mk
  ```
- Common tools (ar, g++, perl, python3) are substituted with standard system paths
- Unknown placeholders are removed

**Files Modified**: `toolchains/scala/scala_binary.bzl:205-208`

### 5. Missing verilator_includer Script

**Problem**: BCR verilator package doesn't include the `verilator_includer` utility script needed during compilation.

**Workaround**:
- Created custom `verilator_includer` python script in `toolchains/verilator/`
- Script combines multiple C++ files into one using `#include` directives
- Test wrapper creates symlink: `$VERILATOR_ROOT/bin/verilator_includer` → our custom script

**Files Added**:
- `toolchains/verilator/verilator_includer` (Python script)
- `toolchains/verilator/BUILD` (exports the script)

**Files Modified**:
- `toolchains/scala/chisel.bzl:72` (added to data dependencies)
- `toolchains/scala/scala_binary.bzl:210-212` (symlink creation)

## Summary of Changes

| File | Changes |
|------|---------|
| `toolchains/scala/chisel.bzl` | - Replaced `@verilator_binary` references<br>- Added `@verilator//:verilator_includes` and `verilator_includer` to data |
| `toolchains/scala/scala_binary.bzl` | - Fixed `_env_impl` to use expanded variables<br>- Enhanced test wrapper to set `VERILATOR_ROOT`<br>- Generate `verilated.mk` from template<br>- Symlink `verilator_includer` script |
| `toolchains/verilator/verilator_includer` | New Python script replacing missing BCR utility |
| `toolchains/verilator/BUILD` | Export verilator_includer script |

## Test Results

**Before**: `bazel test //chisel:life2_test` failed with repository and path errors

**After**: Test passes successfully in ~3.9 seconds
```
//chisel:life2_test                      PASSED in 3.9s
Executed 1 out of 1 test: 1 test passes.
```

## Root Cause

The BCR verilator package (version 5.036.bcr.3) is missing several files and configuration steps that exist in a standard verilator installation:
1. Generated `verilated.mk` makefile
2. `verilator_includer` utility script
3. Proper `VERILATOR_ROOT` setup for use outside of bazel-managed builds

These workarounds bridge the gap between BCR's minimal verilator package and chisel's expectations for a complete verilator installation.
