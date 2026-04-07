#!/bin/sh
# Mock openroad binary — delegates to Python implementation.
dir="$(cd "$(dirname "$0")" && pwd)"
for py in \
    "$dir/openroad.py" \
    "$dir/openroad.runfiles/_main/mock/openroad/src/bin/openroad.py" \
; do
    [ -f "$py" ] && exec python3 "$py" "$@"
done
echo "error: cannot find openroad.py" >&2
exit 1
