#!/bin/sh
# Mock klayout binary — delegates to Python implementation.
# Look for klayout.py as a sibling (direct invocation) or in runfiles (Bazel).
dir="$(cd "$(dirname "$0")" && pwd)"
for py in \
    "$dir/klayout.py" \
    "$dir/klayout.runfiles/mock-klayout+/src/bin/klayout.py" \
    "$dir/klayout.runfiles/mock-klayout/src/bin/klayout.py" \
; do
    [ -f "$py" ] && exec python3 "$py" "$@"
done
echo "error: cannot find klayout.py" >&2
exit 1
