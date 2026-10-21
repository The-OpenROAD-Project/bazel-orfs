#!/bin/bash
set -euo pipefail
checkpoint_before=$1 checkpoint_after=$2 slice_before=$3 slice_after=$4

# Without these the test passes vacuously: the counter must differ
# between the two designs, and the slice must hold private names for it
# to have numbered.
if [ "$(grep '^autoidx' "$checkpoint_before")" = "$(grep '^autoidx' "$checkpoint_after")" ]; then
    echo "FAIL: both checkpoints end at the same autoidx; after.v adds no cells" >&2
    exit 1
fi
if ! grep -qE '^ +cell \S+ \$' "$slice_before"; then
    echo "FAIL: the slice of unit has no private cell names" >&2
    exit 1
fi

if ! cmp -s "$slice_before" "$slice_after"; then
    echo "FAIL: the slice of unit changed although only other did" >&2
    diff "$slice_before" "$slice_after" | head -20 >&2
    exit 1
fi
echo PASS
