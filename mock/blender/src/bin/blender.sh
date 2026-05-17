#!/bin/sh
# Mock blender binary — delegates to Python implementation.
# Look for blender.py as a sibling (direct invocation) or in runfiles (Bazel).
dir="$(cd "$(dirname "$0")" && pwd)"
for py in \
    "$dir/blender.py" \
    "$dir/blender.runfiles/mock-blender+/src/bin/blender.py" \
    "$dir/blender.runfiles/mock-blender/src/bin/blender.py" \
; do
    [ -f "$py" ] && exec python3 "$py" "$@"
done
echo "error: cannot find blender.py" >&2
exit 1
