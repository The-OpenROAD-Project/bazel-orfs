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

## Why Patches?

This module carries a stack of patches on top of upstream ORFS. Updating
them is tedious but mechanical — Claude handles the rebasing. The
patches live here so that bazel-orfs features can be tested against real
designs without waiting for upstream merges. As patches become
well-articulated and stable, they get upstreamed to ORFS, which
minimizes long-term churn on both sides.
