#!/usr/bin/env bash
# Integration test for //:deps workflow.
#
# Exercises the real bazelisk run //:deps workflow end-to-end.
# Cannot run inside bazel test (creates files outside sandbox, nested bazelisk).
#
# Usage:
#   test/deps_integration_test.sh <case>
#   test/deps_integration_test.sh all
#
# Cases: single_synth, single_floorplan, real_floorplan, hierarchy, make_passthrough

set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE_DIR"

PASS=0
FAIL=0
ERRORS=()

# --- Assertion helpers ---

fail() {
    echo "FAIL: $1"
    ERRORS+=("$1")
    FAIL=$((FAIL + 1))
    return 1
}

pass() {
    echo "PASS: $1"
    PASS=$((PASS + 1))
}

assert_dir_exists() {
    [ -d "$1" ] && pass "$1 exists" || fail "$1 directory not found"
}

assert_file_exists() {
    [ -f "$1" ] && pass "$1 exists" || fail "$1 file not found"
}

assert_executable() {
    [ -x "$1" ] && pass "$1 is executable" || fail "$1 not executable"
}

assert_file_contains() {
    grep -q "$2" "$1" 2>/dev/null && pass "$1 contains '$2'" || fail "$1 does not contain '$2'"
}

# --- Deploy helper ---

deploy() {
    local target="$1"; shift
    echo "--- Deploying: bazelisk run //:deps -- $target $*"
    bazelisk run //:deps -- "$target" "$@"
}

# Clean previous deploy for a given directory
clean_deploy() {
    local deploy_dir="$1"
    if [ -d "$deploy_dir" ]; then
        chmod -R u+w "$deploy_dir" 2>/dev/null || true
        rm -rf "$deploy_dir"
    fi
}

# --- Test cases ---

test_single_synth() {
    echo "=== Test: single_synth ==="
    local target="//test:lb_32x128_mock_synth"
    local deploy_dir="tmp/test/lb_32x128_mock_synth_deps"

    clean_deploy "$deploy_dir"
    deploy "$target"

    assert_dir_exists "$deploy_dir"
    assert_executable "$deploy_dir/make"
    assert_file_exists "$deploy_dir/_main/config.mk"
    assert_file_contains "$deploy_dir/_main/config.mk" "VERILOG_FILES"
}

test_single_floorplan() {
    echo "=== Test: single_floorplan ==="
    local target="//test:lb_32x128_mock_floorplan"
    local deploy_dir="tmp/test/lb_32x128_mock_floorplan_deps"

    clean_deploy "$deploy_dir"
    deploy "$target"

    assert_dir_exists "$deploy_dir"
    assert_executable "$deploy_dir/make"
    assert_file_exists "$deploy_dir/_main/config.mk"

    # Verify make wrapper can resolve FLOW_HOME
    local flow_home
    flow_home=$("$deploy_dir/make" print-FLOW_HOME 2>&1 | tail -1)
    [ -n "$flow_home" ] && pass "print-FLOW_HOME returned: $flow_home" \
                        || fail "print-FLOW_HOME returned empty"
}

test_real_floorplan() {
    echo "=== Test: real_floorplan ==="
    local target="//test:tag_array_64x184_mock_floorplan"
    local deploy_dir="tmp/test/tag_array_64x184_mock_floorplan_deps"

    clean_deploy "$deploy_dir"
    deploy "$target"

    assert_dir_exists "$deploy_dir"
    assert_executable "$deploy_dir/make"
    assert_file_exists "$deploy_dir/_main/config.mk"

    # Verify make wrapper can resolve FLOW_HOME (requires external repo)
    local flow_home
    flow_home=$("$deploy_dir/make" print-FLOW_HOME 2>&1 | tail -1)
    [ -n "$flow_home" ] && pass "print-FLOW_HOME returned: $flow_home" \
                        || fail "print-FLOW_HOME returned empty"
}

test_hierarchy() {
    echo "=== Test: hierarchy ==="
    local target="//test:lb_32x128_top_mock_full_hierarchy_floorplan"
    local deploy_dir="tmp/test/lb_32x128_top_mock_full_hierarchy_floorplan_deps"

    clean_deploy "$deploy_dir"
    deploy "$target"

    assert_dir_exists "$deploy_dir"
    assert_executable "$deploy_dir/make"
    assert_file_exists "$deploy_dir/_main/config.mk"

    # Config must reference macro LEF/LIB (hierarchical design)
    assert_file_contains "$deploy_dir/_main/config.mk" "ADDITIONAL_LEFS"
    assert_file_contains "$deploy_dir/_main/config.mk" "ADDITIONAL_LIBS"
}

test_make_passthrough() {
    echo "=== Test: make_passthrough ==="
    local target="//test:tag_array_64x184_mock_floorplan"
    local deploy_dir="tmp/test/tag_array_64x184_mock_floorplan_deps"

    clean_deploy "$deploy_dir"

    # Pass a make arg — deploy + run print-DESIGN_NAME
    deploy "$target" print-DESIGN_NAME

    assert_dir_exists "$deploy_dir"
    pass "make print-DESIGN_NAME completed via passthrough"
}

test_run_substep() {
    echo "=== Test: run_substep ==="
    local target="//test:tag_array_64x184_mock_floorplan"
    local deploy_dir="tmp/test/tag_array_64x184_mock_floorplan_deps"

    clean_deploy "$deploy_dir"
    deploy "$target"

    # Run a substep — this exercises the full local flow:
    # deploy inputs, then execute a stage substep via make.
    "$deploy_dir/make" do-2_1_floorplan
    pass "make do-2_1_floorplan completed"
}

# --- Dispatch ---

run_case() {
    case "$1" in
        single_synth)      test_single_synth ;;
        single_floorplan)  test_single_floorplan ;;
        real_floorplan)    test_real_floorplan ;;
        hierarchy)         test_hierarchy ;;
        make_passthrough)  test_make_passthrough ;;
        run_substep)       test_run_substep ;;
        all)
            test_single_synth
            test_single_floorplan
            test_real_floorplan
            test_hierarchy
            test_make_passthrough
            test_run_substep
            ;;
        *)
            echo "Usage: $0 <single_synth|single_floorplan|real_floorplan|hierarchy|make_passthrough|run_substep|all>"
            exit 1
            ;;
    esac
}

run_case "${1:?Usage: $0 <case>}"

# --- Summary ---

echo ""
echo "=== Summary: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "Failures:"
    for err in "${ERRORS[@]}"; do
        echo "  - $err"
    done
    exit 1
fi
