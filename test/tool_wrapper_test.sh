#!/usr/bin/env bash
# Functional test for tool wrappers (klayout.sh, openroad_wrapper.sh).
# Verifies the wrapper execs the named tool with correct arguments.
set -euo pipefail

WRAPPER="$1"   # path to the wrapper binary
TOOL="$2"      # tool name: "klayout" or "openroad"

MOCK_BIN=$(mktemp -d)
trap 'rm -rf "$MOCK_BIN"' EXIT

# Create a mock tool that prints a marker and all arguments.
cat > "$MOCK_BIN/$TOOL" <<'MOCK'
#!/usr/bin/env bash
echo "MOCK_OK $@"
MOCK
chmod +x "$MOCK_BIN/$TOOL"

export PATH="$MOCK_BIN:$PATH"
output=$("$WRAPPER" --test-arg 2>&1)
echo "$output" | grep -q "MOCK_OK --test-arg" || {
    echo "FAIL: expected mock $TOOL to receive --test-arg. Output:"
    echo "$output"
    exit 1
}
echo "PASS: $TOOL wrapper forwarded arguments correctly"
