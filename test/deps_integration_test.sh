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
# Cases: single_synth, single_floorplan, real_floorplan, hierarchy,
#        make_passthrough, run_substep, lane

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

# deploy <stage target> <dir>: a fresh tree for the stage
deploy() {
    local target="$1" dir="$2"
    echo "--- Deploying: bazelisk run //:deps -- start $target --dir $dir --fresh"
    bazelisk run //:deps -- start "$target" --dir "$WORKSPACE_DIR/$dir" --fresh
}

# --- Test cases ---

test_single_synth() {
    echo "=== Test: single_synth ==="
    local target="//test:lb_32x128_mock_synth"
    local deploy_dir="tmp/deps_it/lb_32x128_mock_synth"

    deploy "$target" "$deploy_dir"

    assert_dir_exists "$deploy_dir"
    assert_executable "$deploy_dir/make"
    assert_file_exists "$deploy_dir/_main/config.mk"
    assert_file_contains "$deploy_dir/_main/config.mk" "VERILOG_FILES"
}

test_single_floorplan() {
    echo "=== Test: single_floorplan ==="
    local target="//test:lb_32x128_mock_floorplan"
    local deploy_dir="tmp/deps_it/lb_32x128_mock_floorplan"

    deploy "$target" "$deploy_dir"

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
    local deploy_dir="tmp/deps_it/tag_array_64x184_mock_floorplan"

    deploy "$target" "$deploy_dir"

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
    local deploy_dir="tmp/deps_it/lb_32x128_top_mock_full_hierarchy_floorplan"

    deploy "$target" "$deploy_dir"

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
    local deploy_dir="tmp/deps_it/tag_array_64x184_mock_floorplan"

    deploy "$target" "$deploy_dir"
    "$deploy_dir/make" print-DESIGN_NAME
    pass "make print-DESIGN_NAME completed in the tree"
}

test_run_substep() {
    echo "=== Test: run_substep ==="
    local target="//test:tag_array_64x184_mock_floorplan"
    local deploy_dir="tmp/deps_it/tag_array_64x184_mock_floorplan"

    deploy "$target" "$deploy_dir"

    # Run a substep — this exercises the full local flow:
    # deploy inputs, then execute a stage substep via make.
    "$deploy_dir/make" do-2_1_floorplan
    pass "make do-2_1_floorplan completed"
}

test_lane() {
    echo "=== Test: lane ==="
    local dir="tmp/deps_it/lane"
    local results="$dir/_main/test/results/asap7/lb_32x128/base"
    deploy "//test:lb_32x128_floorplan" "$dir"
    "$dir/make" do-floorplan
    local before after
    before="$(sha1sum "$results/2_floorplan.odb")"
    bazelisk run //:deps -- next place --dir "$WORKSPACE_DIR/$dir"
    after="$(sha1sum "$results/2_floorplan.odb")"
    [ "$before" = "$after" ] && pass "next kept the hand-made floorplan" ||
        fail "next replaced the hand-made floorplan"
    "$dir/make" do-place
    assert_file_exists "$results/3_place.odb"
    local status
    status="$(bazelisk run //:deps -- status --dir "$WORKSPACE_DIR/$dir" 2>/dev/null)"
    grep -q "ran do-place" <<<"$status" &&
        pass "status records the hand-run place" || fail "status lost the place run"
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
        lane)              test_lane ;;
        all)
            test_single_synth
            test_single_floorplan
            test_real_floorplan
            test_hierarchy
            test_make_passthrough
            test_run_substep
            test_lane
            ;;
        *)
            echo "Usage: $0 <single_synth|single_floorplan|real_floorplan|hierarchy|make_passthrough|run_substep|lane|all>"
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
