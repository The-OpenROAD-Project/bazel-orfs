#!/bin/bash
# Test lint OpenROAD/Yosys with the ORFS Makefile directly.
#
# As a Bazel sh_test:
#   bazelisk test //smoketest:mock_make_test
#
# Standalone (from openroad-demo root):
#   bazelisk build @lint-openroad//src/bin:openroad @lint-yosys//src/bin:yosys
#   smoketest/mock_make_test.sh
#
# This mirrors real usage: you have ORFS checked out and want to
# speed-run through the Makefile to debug it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Locate lint binaries ---
# In Bazel: passed via env from sh_test
# Standalone: search bazel-out
if [ -n "${LINT_OPENROAD_EXE:-}" ] && [ -n "${LINT_YOSYS_EXE:-}" ]; then
    OPENROAD_EXE="$LINT_OPENROAD_EXE"
    YOSYS_EXE="$LINT_YOSYS_EXE"
else
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
    OPENROAD_EXE="$(find -L "$REPO_ROOT/bazel-out" -path "*/lint-openroad*/src/bin/openroad" -not -path "*.runfiles*" 2>/dev/null | head -1)"
    YOSYS_EXE="$(find -L "$REPO_ROOT/bazel-out" -path "*/lint-yosys*/src/bin/yosys" -not -path "*.runfiles*" 2>/dev/null | head -1)"
    if [ -z "$OPENROAD_EXE" ] || [ -z "$YOSYS_EXE" ]; then
        echo "ERROR: lint binaries not found. Run:"
        echo "  bazelisk build @lint-openroad//src/bin:openroad @lint-yosys//src/bin:yosys"
        exit 1
    fi
fi

# --- Locate ORFS Makefile ---
# In Bazel: FLOW_HOME passed via env
# Standalone: use upstream checkout
if [ -z "${FLOW_HOME:-}" ]; then
    REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
    FLOW_HOME="$REPO_ROOT/upstream/OpenROAD-flow-scripts/flow"
fi
if [ ! -f "$FLOW_HOME/Makefile" ]; then
    echo "ERROR: ORFS not found at $FLOW_HOME"
    echo "Clone it: git clone https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts upstream/OpenROAD-flow-scripts"
    exit 1
fi

echo "=== Mock ORFS make flow test ==="
echo "OPENROAD_EXE=$OPENROAD_EXE"
echo "YOSYS_EXE=$YOSYS_EXE"
echo "FLOW_HOME=$FLOW_HOME"

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

# Copy design files
mkdir -p "$WORK_DIR/rtl"
cp "$SCRIPT_DIR"/rtl/*.sv "$WORK_DIR/rtl/"
cp "$SCRIPT_DIR"/*.sdc "$WORK_DIR/"
cp "$SCRIPT_DIR"/*.mk "$WORK_DIR/"

cd "$WORK_DIR"

# Run with clean environment — no env vars leak through
env -i \
    PATH="/usr/bin:/bin:/usr/local/bin" \
    HOME="$WORK_DIR" \
    make --file="$FLOW_HOME/Makefile" \
        OPENROAD_EXE="$OPENROAD_EXE" \
        YOSYS_EXE="$YOSYS_EXE" \
        DESIGN_CONFIG="$WORK_DIR/config.mk" \
        WORK_HOME="$WORK_DIR" \
        FLOW_VARIANT=mock_test \
        synth 2>&1 | tail -30

echo ""
echo "=== Checking outputs ==="
for f in results/asap7/counter_with_sram/mock_test/1_synth.odb \
         results/asap7/counter_with_sram/mock_test/1_2_yosys.v \
         results/asap7/counter_with_sram/mock_test/mem.json; do
    if [ -f "$f" ]; then
        echo "OK: $(basename "$f") ($(wc -c < "$f") bytes)"
    else
        echo "MISSING: $f"
        find results -type f 2>/dev/null | head -20
        exit 1
    fi
done

echo ""
echo "=== PASS ==="
