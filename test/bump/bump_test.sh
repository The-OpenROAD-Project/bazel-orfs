#!/bin/bash
# Test //:bump logic across all project types without network calls.
#
# These tests use fixture MODULE.bazel files instead of testing against
# real checkouts. This is important for three reasons:
#
# 1. Speed: 23 assertions in 0.1s vs minutes of docker pulls and mod tidy
# 2. Safety: no risk of corrupting MODULE.bazel in private or in-progress
#    projects with untested sed patterns
# 3. Reproducibility: no network, no docker, deterministic results
set -e -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"

# Mock values
LATEST_TAG="26Q1-999-gtest12345"
DIGEST="deadbeef1234567890abcdef"
BAZEL_ORFS_COMMIT="new_bazel_orfs_aaa111"
OPENROAD_COMMIT="new_openroad_bbb222"

PASS=0
FAIL=0

assert_contains() {
    local file="$1" pattern="$2" msg="$3"
    if grep -q "$pattern" "$file"; then
        echo "  PASS: $msg"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $msg (pattern '$pattern' not found)"
        echo "  File contents:"
        cat "$file" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local file="$1" pattern="$2" msg="$3"
    if ! grep -q "$pattern" "$file"; then
        echo "  PASS: $msg"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $msg (pattern '$pattern' unexpectedly found)"
        FAIL=$((FAIL + 1))
    fi
}

# Apply the bump logic to a MODULE.bazel file (extracted from bump.sh)
apply_bump() {
    local MODULE_FILE="$1"

    # --- Detection (from bump.sh) ---
    MODULE_NAME=$(sed -n '/^module(/,/^)/{s/.*name = "\([^"]*\)".*/\1/p}' "$MODULE_FILE" | head -1)
    IS_BAZEL_ORFS=0
    IS_OPENROAD=0
    [[ "$MODULE_NAME" == "bazel-orfs" ]] && IS_BAZEL_ORFS=1
    [[ "$MODULE_NAME" == "openroad" ]] && IS_OPENROAD=1

    # --- Docker image update (all projects) ---
    sed -i -E \
        -e "/orfs\.default\(/,/^\s*\)/ { \
            s|(image = \"docker.io/openroad/orfs:)[^\"]+(\")|\1$LATEST_TAG\2|; \
            s|(sha256 = \")[^\"]+(\")|\1$DIGEST\2| \
        }" \
        "$MODULE_FILE"

    # --- bazel-orfs commit (skip for bazel-orfs itself) ---
    if [[ "$IS_BAZEL_ORFS" -eq 0 ]]; then
        sed -i "/git_override(/{:a;N;/)/!ba};/module_name = \"bazel-orfs\"/s/commit = \"[^\"]*\"/commit = \"$BAZEL_ORFS_COMMIT\"/" "$MODULE_FILE"
    fi

    # --- OpenROAD commit (skip for OpenROAD itself) ---
    if [[ "$IS_OPENROAD" -eq 0 ]]; then
        sed -i "/git_override(/{:a;N;/)/!ba};/module_name = \"openroad\"/s/commit = \"[^\"]*\"/commit = \"$OPENROAD_COMMIT\"/" "$MODULE_FILE"
        sed -i "/#.*git_override(/{:a;N;/#.*)/!ba};/module_name = \"openroad\"/s/commit = \"[^\"]*\"/commit = \"$OPENROAD_COMMIT\"/" "$MODULE_FILE"
    fi

    # --- Inject boilerplate (downstream only) ---
    if [[ "$IS_BAZEL_ORFS" -eq 0 ]] && [[ "$IS_OPENROAD" -eq 0 ]]; then
        if ! grep -q 'Uncomment to build OpenROAD from source' "$MODULE_FILE"; then
            INJECT_AFTER=$(grep -n 'use_repo(orfs' "$MODULE_FILE" | tail -1 | cut -d: -f1)
            if [[ -n "$INJECT_AFTER" ]]; then
                sed -i "${INJECT_AFTER}a\\
\\
# Uncomment to build OpenROAD from source instead of using the docker image.\\
# This is useful to test the latest OpenROAD before the docker image is updated.\\
# See: https://github.com/The-OpenROAD-Project/bazel-orfs/blob/main/docs/openroad.md\\
#\\
# bazel_dep(name = \"openroad\")\\
# git_override(\\
#     module_name = \"openroad\",\\
#     commit = \"$OPENROAD_COMMIT\",\\
#     init_submodules = True,\\
#     patch_strip = 1,\\
#     patches = [\"@bazel-orfs//:openroad-llvm-root-only.patch\", \"@bazel-orfs//:openroad-visibility.patch\"],\\
#     remote = \"https://github.com/The-OpenROAD-Project/OpenROAD.git\",\\
# )\\
# bazel_dep(name = \"qt-bazel\")\\
# git_override(\\
#     module_name = \"qt-bazel\",\\
#     commit = \"df022f4ebaa4130713692fffd2f519d49e9d0b97\",\\
#     remote = \"https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts\",\\
# )\\
# bazel_dep(name = \"toolchains_llvm\", version = \"1.5.0\")" \
                "$MODULE_FILE"
            fi
        fi
    fi
}

# ============================================================
# Test 1: bazel-orfs project
# ============================================================
echo ""
echo "=== Test 1: bazel-orfs project ==="
TMPFILE=$(mktemp)
cp "$FIXTURES_DIR/self.MODULE.bazel" "$TMPFILE"
apply_bump "$TMPFILE"

assert_contains "$TMPFILE" "$LATEST_TAG" "docker image tag updated"
assert_contains "$TMPFILE" "$DIGEST" "docker sha256 updated"
assert_contains "$TMPFILE" "$OPENROAD_COMMIT" "OpenROAD commit updated"
assert_not_contains "$TMPFILE" "$BAZEL_ORFS_COMMIT" "bazel-orfs commit NOT updated (is self)"
assert_not_contains "$TMPFILE" "Uncomment to build OpenROAD" "no boilerplate injected"
rm "$TMPFILE"

# ============================================================
# Test 2: OpenROAD project
# ============================================================
echo ""
echo "=== Test 2: OpenROAD project ==="
TMPFILE=$(mktemp)
cp "$FIXTURES_DIR/openroad.MODULE.bazel" "$TMPFILE"
apply_bump "$TMPFILE"

assert_contains "$TMPFILE" "$LATEST_TAG" "docker image tag updated"
assert_contains "$TMPFILE" "$DIGEST" "docker sha256 updated"
assert_contains "$TMPFILE" "$BAZEL_ORFS_COMMIT" "bazel-orfs commit updated"
assert_not_contains "$TMPFILE" "$OPENROAD_COMMIT" "OpenROAD commit NOT updated (is self)"
assert_not_contains "$TMPFILE" "Uncomment to build OpenROAD" "no boilerplate injected"
assert_contains "$TMPFILE" 'openroad = "//:openroad"' "openroad = //:openroad preserved"
rm "$TMPFILE"

# ============================================================
# Test 3: downstream project (fresh, no boilerplate)
# ============================================================
echo ""
echo "=== Test 3: downstream project (fresh) ==="
TMPFILE=$(mktemp)
cp "$FIXTURES_DIR/downstream.MODULE.bazel" "$TMPFILE"
apply_bump "$TMPFILE"

assert_contains "$TMPFILE" "$LATEST_TAG" "docker image tag updated"
assert_contains "$TMPFILE" "$DIGEST" "docker sha256 updated"
assert_contains "$TMPFILE" "$BAZEL_ORFS_COMMIT" "bazel-orfs commit updated"
assert_contains "$TMPFILE" "Uncomment to build OpenROAD" "boilerplate injected"
assert_contains "$TMPFILE" "commit = \"$OPENROAD_COMMIT\"" "boilerplate has correct OpenROAD commit"
rm "$TMPFILE"

# ============================================================
# Test 4: downstream project (already has boilerplate — idempotent)
# ============================================================
echo ""
echo "=== Test 4: downstream project (idempotent update) ==="
TMPFILE=$(mktemp)
cp "$FIXTURES_DIR/downstream-with-boilerplate.MODULE.bazel" "$TMPFILE"
apply_bump "$TMPFILE"

assert_contains "$TMPFILE" "$LATEST_TAG" "docker image tag updated"
assert_contains "$TMPFILE" "$DIGEST" "docker sha256 updated"
assert_contains "$TMPFILE" "$BAZEL_ORFS_COMMIT" "bazel-orfs commit updated"
assert_not_contains "$TMPFILE" "old_openroad_commit" "old OpenROAD commit replaced"
assert_contains "$TMPFILE" "commit = \"$OPENROAD_COMMIT\"" "commented-out OpenROAD commit updated"
# Verify boilerplate appears exactly once
BOILERPLATE_COUNT=$(grep -c 'Uncomment to build OpenROAD' "$TMPFILE")
if [[ "$BOILERPLATE_COUNT" -eq 1 ]]; then
    echo "  PASS: boilerplate appears exactly once (not duplicated)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: boilerplate appears $BOILERPLATE_COUNT times (expected 1)"
    FAIL=$((FAIL + 1))
fi
rm "$TMPFILE"

# ============================================================
# Test 5: downstream project (run bump twice — still idempotent)
# ============================================================
echo ""
echo "=== Test 5: downstream project (double bump) ==="
TMPFILE=$(mktemp)
cp "$FIXTURES_DIR/downstream.MODULE.bazel" "$TMPFILE"
apply_bump "$TMPFILE"
apply_bump "$TMPFILE"  # second run

BOILERPLATE_COUNT=$(grep -c 'Uncomment to build OpenROAD' "$TMPFILE")
if [[ "$BOILERPLATE_COUNT" -eq 1 ]]; then
    echo "  PASS: boilerplate appears exactly once after double bump"
    PASS=$((PASS + 1))
else
    echo "  FAIL: boilerplate appears $BOILERPLATE_COUNT times after double bump (expected 1)"
    FAIL=$((FAIL + 1))
fi
rm "$TMPFILE"

# ============================================================
# Summary
# ============================================================
echo ""
echo "==============================="
echo "Results: $PASS passed, $FAIL failed"
echo "==============================="

[[ "$FAIL" -eq 0 ]] || exit 1
