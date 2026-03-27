# bazel-orfs: Lint-Optimized Flow Changes

## Background

openroad-demo has lint OpenROAD/Yosys — Python drop-in replacements that
validate ORFS parameters in seconds. They use `orfs_flow` with per-variant
tool overrides (`openroad = "@lint-openroad//..."`). This works but creates
massive runfiles overhead: ~4,691 symlinks per stage, 99.9% identical.

## Problem 1: `_deps` targets (33% of all targets)

Every stage unconditionally creates a `_deps` target for GUI debugging.
These are never used in CI or production builds.

### Fix: `add_deps` parameter

**File: `private/flow.bzl`**

In `_orfs_pass()`, the `orfs_deps()` call is unconditional. Gate it:

```python
def _orfs_pass(
        ...,
        add_deps = False,
        ...):
    ...
    # Currently ~line 70-80 in _orfs_pass:
    # orfs_deps(name = step + "_deps", src = ":" + step, ...)
    # Change to:
    if add_deps:
        orfs_deps(name = step + "_deps", src = ":" + step, ...)
```

**File: `private/flow.bzl`**

Thread `add_deps` through `orfs_flow()` → `_orfs_pass()`:

```python
def orfs_flow(
        ...,
        add_deps = False,
        ...):
    ...
    _orfs_pass(..., add_deps = add_deps, ...)
```

**File: `sweep.bzl`**

Thread `add_deps` through `orfs_sweep()` → `orfs_flow()`.

### Testing

```bash
# Existing tests should still pass (add_deps defaults to False,
# but tests that use _deps targets need add_deps=True)
bazelisk test //...

# Check _deps targets are gone by default
bazelisk query 'kind(".*", //test/...)' | grep _deps
# Should be empty unless test explicitly sets add_deps=True
```

## Problem 2: `flow_inputs()` pulls everything

**File: `private/environment.bzl`, line 94**

`flow_inputs(ctx)` returns a depset with klayout, opensta, ruby, tcl,
opengl, qt_plugins — ~4,500 files that lint tools don't need.

### Fix: `flow_inputs_lite()`

**File: `private/environment.bzl`**

Add after `flow_inputs()`:

```python
def flow_inputs_lite(ctx):
    """Minimal tool inputs for lightweight flows (lint/mock).

    Excludes klayout, opensta, ruby, tcl, opengl, qt — only includes
    make, openroad (or its replacement), makefile, and user tools.
    """
    return depset(
        transitive = [
            _runfiles([
                ctx.attr._make,
                _openroad_attr(ctx),
                ctx.attr._python,
                ctx.attr._makefile,
            ] + ctx.attr.tools),
        ],
    )
```

**File: `private/attrs.bzl`**

Add `lite_flow` attribute to `flow_attrs()`:

```python
def flow_attrs():
    return {
        ...
        "lite_flow": attr.bool(
            doc = "Use minimal tool dependencies (for lint/mock flows).",
            default = False,
        ),
        ...
    }
```

**File: `private/rules.bzl`**

In `_make_impl()` (line 751-764), switch based on `lite_flow`:

```python
    tools_depset = flow_inputs_lite(ctx) if ctx.attr.lite_flow else flow_inputs(ctx)

    ctx.actions.run_shell(
        ...
        tools = tools_depset,
    )

    # Also update runfiles (lines 801-822):
    runfiles_transitive = [tools_depset, ...]
```

And in the `OrfsDepInfo` runfiles (lines 844-854), same switch.

### What's kept in lite mode

- `_make` — the Make binary (from docker_orfs)
- `_openroad_attr(ctx)` — lint-openroad Python binary
- `_python` — Python interpreter (for lint tools)
- `_makefile` — ORFS Makefile
- `ctx.attr.tools` — user-specified extra tools

### What's dropped in lite mode

- `_klayout` — not used by lint
- `_opensta` — not used by lint
- `_ruby`, `_ruby_dynamic` — klayout dependency
- `_tcl` — klayout dependency
- `_opengl`, `_qt_plugins` — GUI dependencies

### Testing

```bash
# Existing non-lite tests unchanged
bazelisk test //...

# Test lite flow with mock/lint tools
# (need a test design that uses lite_flow=True)
```

## Problem 3: Per-stage runfiles duplication (future)

Even with `flow_inputs_lite()`, each stage still creates its own runfiles
tree. With lite mode this is ~200 symlinks per stage instead of ~4,691,
which is acceptable for now.

The ultimate fix is a shared deploy target, but that's a larger refactor:
stage rules would need to receive tool paths from a provider instead of
having their own tool attributes.

## Implementation Order

1. Add `add_deps` parameter (smallest, most contained change)
2. Add `lite_flow` + `flow_inputs_lite()` (second change)
3. Thread both through `orfs_flow()` and `orfs_sweep()`
4. Test with existing test suite
5. Test with openroad-demo lint variant

## Files Changed

| File | Change |
|------|--------|
| `private/flow.bzl` | `add_deps` param in `orfs_flow` + `_orfs_pass` |
| `private/environment.bzl` | Add `flow_inputs_lite()` |
| `private/attrs.bzl` | Add `lite_flow` attr |
| `private/rules.bzl` | Use `lite_flow` in `_make_impl` runfiles |
| `sweep.bzl` | Forward `add_deps` + `lite_flow` |
| `openroad.bzl` | Re-export new params |

## Debugging

To verify the changes work, add a test in ~/bazel-orfs/ that creates a
flow with `lite_flow=True` and `add_deps=False`, then checks:

1. No `_deps` targets created
2. Runfiles manifest is < 500 lines (vs ~4,700 for full flow)
3. The stage still completes (make + openroad binary accessible)
