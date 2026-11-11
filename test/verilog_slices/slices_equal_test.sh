#!/bin/bash
# The slice path and the global path give every partition the same name
# and the same netlist, and the design the same netlist. The canonical
# RTLIL may differ: a module under a kept one is named after where the
# slice, not the whole design, first instantiates it, and partition
# synthesis flattens it away.
set -euo pipefail
netlist_global=$1 netlist_slices=$2 kept=$3
shift 3
global=()
while [ "$1" != -- ]; do
    global+=("$1")
    shift
done
shift
slices=("$@")

pick() {
    local name=$1
    shift
    for f in "$@"; do
        if [ "$(basename "$f")" = "$name" ]; then
            echo "$f"
            return
        fi
    done
    echo "FAIL: no $name" >&2
    exit 1
}

same() {
    if ! cmp -s "$1" "$2"; then
        echo "FAIL: $3 differs between the global and the slice path" >&2
        diff "$1" "$2" | head -20 >&2
        exit 1
    fi
}

for m in $kept; do
    pick "partition_${m}_slice.v" "${slices[@]}" > /dev/null
    for name in "partition_${m}_canonical.name" "partition_${m}.v"; do
        same "$(pick "$name" "${global[@]}")" "$(pick "$name" "${slices[@]}")" "$name"
    done
    if ! grep -qE "^module \\\\?$m[\$( ]" "$(pick "partition_${m}.v" "${slices[@]}")"; then
        echo "FAIL: partition_${m}.v does not define $m" >&2
        exit 1
    fi
done
same "$netlist_global" "$netlist_slices" 1_2_yosys.v

# Other's memory is a black box in its partition: AUTO_MEMORIES reached
# the slice.
if grep -q "^module ram_64x16" "$(pick partition_Other.v "${slices[@]}")"; then
    echo "FAIL: ram_64x16 was synthesized into Other's partition" >&2
    exit 1
fi
echo PASS
