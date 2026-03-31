# ORFS Designs in Bazel

This directory is an existence proof: 51 ORFS designs across 5 platforms
(asap7, sky130hd, sky130hs, gf180, ihp-sg13g2) build and pass lint
validation under Bazel using the bazel-orfs rules from the parent
directory.

## What You Can Do

```bash
cd orfs/

# Lint a single design (~seconds, uses mock-openroad)
bazelisk build @orfs//flow/designs/asap7/gcd:gcd_lint_synth

# Lint all CI designs
bazelisk test $(bazelisk query @orfs//flow/designs/... | grep _lint_test)

# Run a real flow stage
bazelisk build @orfs//flow/designs/asap7/gcd:gcd_synth

# Run all synth flows for asap7
bazelisk build $(bazelisk query @orfs//flow/designs/asap7/... | grep _synth)

# Run a full test of one flow, including metadata test, quality of results
# regression test in ORFS
bazelisk test @orfs//flow/designs/asap7/gcd:gcd_test

```

Every `config.mk` design in ORFS automatically gets Bazel targets — no
manual wiring needed.

## What's with the funky `@orfs//` path

Bazel is importing and patching up ORFS so that we have something to
test against and then we get thsi funky path.

When this is merged with ORFS, you would test all designs with
linting and real tests by using a more straightforward syntax:

```
cd flow
bazelisk test designs/asap7/...
```

## How to Contribute

You don't need to touch any code here. If something looks wrong, is
missing, or could work better, file an issue with questions,
suggestions, or feature requests.

Obviously, PRs are welcome, but this is a bit of a tricky setup
so fixing simple things come with a large cognitive load compared
to PRs directly in OpenROAD and ORFS.

## Flow Rules Check (FRC)

The lint flow validates design configuration in seconds using mock
tools. FRC rules catch common errors before expensive real builds.
See the [FRC catalog](FRC.md) for the full list.

## Build Status

Floorplan stage results across all platforms (2026-03-31):

### asap7

| Design | floorplan | Blocking issue |
|--------|-----------|----------------|
| aes | pass | |
| aes-block | pass | |
| aes-mbff | pass | |
| aes_lvt | pass | |
| cva6 | pass | |
| ethmac | pass | |
| ethmac_lvt | pass | |
| gcd | pass | |
| gcd-ccs | pass | |
| ibex | pass | |
| jpeg | pass | |
| jpeg_lvt | pass | |
| mock-alu | pass | |
| mock-cpu | pass | |
| riscv32i | pass | |
| riscv32i-mock-sram (block) | pass | |
| riscv32i-mock-sram (top) | pass | Fixed: [FRC-7](FRC.md) PDN-0232/0233 (patch 0035) |
| swerv_wrapper | pass | |
| uart | pass | |

### sky130hd

| Design | floorplan | Blocking issue |
|--------|-----------|----------------|
| aes | pass | |
| chameleon | pass | |
| gcd | pass | |
| jpeg | pass | |
| microwatt | pass | |
| riscv32i | pass | |

### sky130hs

| Design | floorplan | Blocking issue |
|--------|-----------|----------------|
| aes | pass | |
| gcd | pass | |
| ibex | pass | |
| jpeg | pass | |
| riscv32i | pass | |

### gf180

| Design | floorplan | Blocking issue |
|--------|-----------|----------------|
| aes | pass | |
| aes-hybrid | pass | |
| ibex | pass | |
| jpeg | pass | |
| riscv32i | pass | |

### ihp-sg13g2

| Design | floorplan | Blocking issue |
|--------|-----------|----------------|
| aes | pass | |
| gcd | pass | |
| i2c-gpio-expander | **FAIL** | [FRC-8](FRC.md) synth fixed (patch 0033); [FRC-9](FRC.md) PAD-0102 at floorplan |
| i2c-gpio-expander/I2cDeviceCtrl | **FAIL** | [FRC-8](FRC.md) synth fixed (patch 0033); [FRC-9](FRC.md) PAD-0102 at floorplan |
| ibex | pass | |
| jpeg | pass | |
| riscv32i | pass | |
| spi | pass | |

## Why Patches?

This module carries a stack of patches on top of upstream ORFS. Updating
them is tedious but mechanical — Claude handles the rebasing. The
patches live here so that bazel-orfs features can be tested against real
designs without waiting for upstream merges. As patches become
well-articulated and stable, they get upstreamed to ORFS, which
minimizes long-term churn on both sides.
