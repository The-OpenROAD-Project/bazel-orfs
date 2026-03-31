#!/bin/sh
# Mock yosys binary — delegates to Python implementation.
dir="$(cd "$(dirname "$0")" && pwd)"
for py in \
    "$dir/yosys.py" \
    "$dir/yosys.runfiles/mock-yosys+/src/bin/yosys.py" \
    "$dir/yosys.runfiles/mock-yosys/src/bin/yosys.py" \
; do
    [ -f "$py" ] && exec python3 "$py" "$@"
done
echo "error: cannot find yosys.py" >&2
exit 1
