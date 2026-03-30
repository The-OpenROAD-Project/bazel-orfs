# ORFS Integration Testing

This directory is a standalone Bazel module that fetches
[OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
at a pinned commit and applies patches on top. It lets you test bazel-orfs
rules against real ORFS designs without maintaining a separate checkout.

## Motivation

ORFS designs are configured via `config.mk` files. These patches add:

- **config.mk parser** — auto-generates Bazel targets from ~84 design configs
- **`orfs_design()` macro** — single macro per design, dual targets (real flow + lint)
- **Lint flow** — seconds-fast validation using mock-openroad (51/51 designs pass across 6 platforms)
- **Parallel synthesis** — 6.8x speedup on swerv_wrapper via keep-hierarchy + partition

## Quick Start

```bash
cd orfs/
bazelisk build @orfs//flow/designs/asap7/gcd:gcd_lint_synth   # single design lint
bazelisk test @orfs//... --test_tag_filters=-manual            # all CI designs
```

## How It Works

`MODULE.bazel` uses `git_override` to fetch ORFS at a merge-base commit and
applies 41 patches (40 feature commits + 1 fixup removing `local_path_override`
directives that are only valid when ORFS is the root module).

The module provides:
- `bazel-orfs` via `local_path_override` to the parent directory
- `mock-openroad` via `local_path_override` to `../mock/openroad`
- ORFS docker image for yosys/openroad binaries

## Updating Patches

When the ORFS branch gains new commits:

```bash
cd /path/to/OpenROAD-flow-scripts
git format-patch <merge-base>..HEAD -o /path/to/bazel-orfs/orfs/patches/

# Regenerate fixup patch if MODULE.bazel changed, then update
# orfs/MODULE.bazel patches list to include all new patches.
```

## Known Limitations

- Parallel synthesis ODB stage is blocked by Make prerequisite checking
- Some designs are tagged `manual` (no CI rules-base.json)
- The docker image provides yosys/openroad; PDK and flow scripts come from the patched ORFS source
