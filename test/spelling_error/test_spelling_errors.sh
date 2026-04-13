#!/bin/bash
# Manual test runner for variable-name spelling validation.
#
# Usage: cd test/spelling_error && ./test_spelling_errors.sh
#
# Tests that check_variables() in orfs_flow() catches misspelled
# variable names at load time with clear error messages.

set -euo pipefail

cd "$(dirname "$0")"

pass=0
fail=0

expect_failure() {
    local pkg="$1" expected="$2"
    local output
    if output=$(bazelisk query "//${pkg}:all" 2>&1); then
        echo "FAIL: //${pkg} should have failed but succeeded"
        fail=$((fail + 1))
        return
    fi
    if echo "$output" | grep -q "$expected"; then
        echo "PASS: //${pkg} — got expected error"
        pass=$((pass + 1))
    else
        echo "FAIL: //${pkg} — wrong error message"
        echo "  Expected substring: $expected"
        echo "  Got: $(echo "$output" | grep 'Error in fail' | head -1)"
        fail=$((fail + 1))
    fi
}

expect_success() {
    local pkg="$1"
    if bazelisk query "//${pkg}:all" >/dev/null 2>&1; then
        echo "PASS: //${pkg} — loaded successfully"
        pass=$((pass + 1))
    else
        echo "FAIL: //${pkg} — should have loaded but failed"
        fail=$((fail + 1))
    fi
}

echo "=== Variable spelling validation tests ==="
echo

# Typo in arguments
expect_failure argument_typo "Unknown ORFS variable(s) in arguments: CORE_UTILIZATON"

# Typo in sources
expect_failure source_typo "Unknown ORFS variable(s) in sources: SDC_FLIE"

# Completely unknown variable
expect_failure unknown_var "Unknown ORFS variable(s) in arguments: TOTALLY_FAKE_VAR"

# Multiple typos reported together
expect_failure multiple_typos "CORE_UTILIZATON, PLACE_DENSTY"

# Control: valid variables load fine
expect_success valid

echo
echo "=== Results: ${pass} passed, ${fail} failed ==="
[ "$fail" -eq 0 ]
