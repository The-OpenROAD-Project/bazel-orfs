#!/bin/bash
# Asserts a forked variant's stage config names the variant it reads from.
#
# A stage writes to its own FLOW_VARIANT and reads its src's. ORFS resolves
# the reads through INPUT_RESULTS_DIR, which FLOW_INPUT_VARIANT names, and
# nothing copies the src's results into this variant's directory first. If
# the two ever collapse to the same value on a forked variant, the stage
# looks for its inputs in its own (empty) results directory.
set -euo pipefail

config="$1"
expected_input_variant="$2"
expected_variant="$3"

fail() {
  echo "FAIL: $1" >&2
  echo "--- $config ---" >&2
  grep -E '^(export )?FLOW(_INPUT)?_VARIANT' "$config" >&2 || true
  exit 1
}

# config.mk writes these as `export NAME?=value`.
actual_input=$(sed -n 's/^\(export \)\?FLOW_INPUT_VARIANT[[:space:]]*?\?=[[:space:]]*//p' "$config" | tail -1)
actual=$(sed -n 's/^\(export \)\?FLOW_VARIANT[[:space:]]*?\?=[[:space:]]*//p' "$config" | tail -1)

[ -n "$actual_input" ] || fail "FLOW_INPUT_VARIANT is not set at all"
[ "$actual_input" = "$expected_input_variant" ] ||
  fail "FLOW_INPUT_VARIANT is '$actual_input', expected '$expected_input_variant'"
[ "$actual" = "$expected_variant" ] ||
  fail "FLOW_VARIANT is '$actual', expected '$expected_variant'"
[ "$actual_input" != "$actual" ] ||
  fail "FLOW_INPUT_VARIANT collapsed onto FLOW_VARIANT ('$actual')"

echo "PASS: reads from '$actual_input', writes to '$actual'"
