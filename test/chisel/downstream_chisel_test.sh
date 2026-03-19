#!/bin/bash
# Integration test: verify that a downstream project can use bazel-orfs
# with Chisel to generate Verilog from a Chisel module.
#
# This runs a nested bazelisk build inside mock/chisel/ with
# --override_module to point bazel-orfs at the local source tree.
#
# Requires tags = ["no-sandbox", "local"] because it needs access to
# the full source tree for --override_module.
set -e -u -o pipefail

# Resolve the bazel-orfs workspace root from the script's real location
# on disk (not runfiles). The no-sandbox tag ensures this is the source tree.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
# test/chisel/downstream_chisel_test.sh -> workspace root is ../..
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MOCK_DIR="$WORKSPACE_ROOT/mock/chisel"

if [ ! -f "$MOCK_DIR/MODULE.bazel" ]; then
    echo "FAIL: mock/chisel/MODULE.bazel not found at $MOCK_DIR"
    exit 1
fi

echo "Building Chisel HelloWorld in mock downstream repo..."
echo "  WORKSPACE_ROOT=$WORKSPACE_ROOT"
echo "  MOCK_DIR=$MOCK_DIR"

cd "$MOCK_DIR"

# Ensure HOME is set for bazelisk (stripped by --incompatible_strict_action_env).
export HOME="${HOME:-/tmp}"

# Build the Chisel -> FIRRTL -> Verilog pipeline.
# --override_module makes the nested build use the local bazel-orfs
# instead of fetching it from a registry or git.
bazelisk build //:helloworld.sv \
    --override_module=bazel-orfs="$WORKSPACE_ROOT" \
    2>&1

echo "PASS: downstream Chisel -> Verilog build succeeded"
