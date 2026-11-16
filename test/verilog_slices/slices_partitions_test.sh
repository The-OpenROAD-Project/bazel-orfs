#!/bin/bash
# Two kept modules with a memory each in one partition: each finds its
# own slice's memory, and the design synthesizes as it does with one
# partition per module. The kept list's order makes the round-robin
# order the merge's, by module name, so the netlists are byte-identical.
set -euo pipefail
netlist_modules=$1 netlist_grouped=$2
shift 2
modules=()
while [ "$1" != -- ]; do
    modules+=("$1")
    shift
done
shift
grouped=("$@")

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
        echo "FAIL: $3" >&2
        diff "$1" "$2" | head -20 >&2
        exit 1
    fi
}

for m in MemA MemB; do
    part=$(pick "partition_${m}.v" "${modules[@]}")
    if grep -q "^module ram_64x16" "$part" || ! grep -q "ram_64x16 " "$part"; then
        echo "FAIL: $m's memory is not a black box in its partition" >&2
        exit 1
    fi
done
same <(cat "$(pick partition_MemA.v "${modules[@]}")" "$(pick partition_MemB.v "${modules[@]}")") \
    "$(pick partition_0.v "${grouped[@]}")" "partition_0.v is not MemA's and MemB's"
same "$(pick partition_Plain.v "${modules[@]}")" "$(pick partition_1.v "${grouped[@]}")" \
    "partition_1.v is not Plain's"
same "$netlist_modules" "$netlist_grouped" "1_2_yosys.v differs between the partitionings"
echo PASS
