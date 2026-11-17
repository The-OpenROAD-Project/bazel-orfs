#!/bin/bash
# partition_arguments changes the named module's partition netlist and
# leaves every other partition, the top's included, byte-identical.
# Usage: partition_arguments_test.sh MODULE BASE_PARTITIONS... -- ARGUMENTS_PARTITIONS...
set -euo pipefail
changed=$1
shift
base=()
while [ "$1" != -- ]; do
    base+=("$1")
    shift
done
shift
with=("$@")

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

for f in "${base[@]}"; do
    name=$(basename "$f")
    case "$name" in
    partition_*.v) ;;
    *) continue ;;
    esac
    other=$(pick "$name" "${with[@]}")
    if [ "$name" = "partition_${changed}.v" ]; then
        if cmp -s "$f" "$other"; then
            echo "FAIL: $name is the same with and without partition_arguments" >&2
            exit 1
        fi
    elif ! cmp -s "$f" "$other"; then
        echo "FAIL: $name changed, but partition_arguments names only $changed" >&2
        diff "$f" "$other" | head -20 >&2
        exit 1
    fi
done
pick "partition_${changed}.v" "${base[@]}" >/dev/null
echo PASS
