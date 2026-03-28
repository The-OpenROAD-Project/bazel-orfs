#!/usr/bin/env bash
# Functional test for //pythonwrapper:python3.
# Verifies the wrapper executes a script with correct argv and pyyaml available.
set -euo pipefail

PYTHON="$1"
SCRIPT=$(mktemp --suffix=.py)
trap 'rm -f "$SCRIPT"' EXIT

cat > "$SCRIPT" <<'PY'
import sys
import yaml
print(f"OK args={sys.argv[1:]}")
PY

output=$("$PYTHON" "$SCRIPT" hello world 2>&1)
echo "$output" | grep -q "OK args=\['hello', 'world'\]" || {
    echo "FAIL: unexpected output: $output"
    exit 1
}
echo "PASS: python3 wrapper executed script with correct argv"
