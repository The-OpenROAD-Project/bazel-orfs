#!/usr/bin/env bash
# Functional test for //pythonwrapper:python3.
# Verifies the wrapper executes a script with correct argv and pyyaml
# available, and that no python it runs writes bytecode beside a source.
set -euo pipefail

PYTHON="$1"
DIR=$(mktemp -d)
trap 'rm -rf "$DIR"' EXIT
SCRIPT="$DIR/main.py"

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

# The shape of ORFS's AUTO_MEMORIES: a flow script imports a sibling in
# the wrapper's own interpreter, then runs another script with
# sys.executable, which imports its own sibling package (FakeRAM's run.py
# and utils/). Neither may leave a __pycache__ in the source tree.
mkdir -p "$DIR/flow" "$DIR/tool/utils"
cat > "$DIR/flow/helper.py" <<'PY'
VALUE = "helper"
PY
cat > "$DIR/flow/gen.py" <<'PY'
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helper

tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tool", "run.py")
subprocess.check_call([sys.executable, tool])
print(f"OK {helper.VALUE}")
PY
cat > "$DIR/tool/utils/__init__.py" <<'PY'
VALUE = "utils"
PY
cat > "$DIR/tool/run.py" <<'PY'
import utils

print(f"OK {utils.VALUE}")
PY

output=$("$PYTHON" "$DIR/flow/gen.py" 2>&1)
echo "$output" | grep -q "OK utils" && echo "$output" | grep -q "OK helper" || {
    echo "FAIL: unexpected output: $output"
    exit 1
}
cached=$(find "$DIR" -name __pycache__ -o -name '*.pyc')
if [ -n "$cached" ]; then
    echo "FAIL: bytecode written beside the sources:"
    echo "$cached"
    exit 1
fi
echo "PASS: no bytecode written by the wrapper or a child python"
