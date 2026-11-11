#!/bin/bash
# An edit inside Inner reaches Inner's partition and nothing else: Outer,
# which holds Inner, and Other keep their slices, their memories, their
# canonical RTLIL and their netlists, so their partitions are cache hits.
set -euo pipefail
before=()
while [ "$1" != -- ]; do
    before+=("$1")
    shift
done
shift
after=("$@")

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

for m in Outer Other; do
    for name in "partition_${m}_slice.v" "partition_${m}_canonical.rtlil" "partition_${m}.v"; do
        if ! cmp -s "$(pick "$name" "${before[@]}")" "$(pick "$name" "${after[@]}")"; then
            echo "FAIL: $name changed for an edit inside Inner" >&2
            exit 1
        fi
    done
done

# Their memories too: each slice finds its own, so Inner's edit does not
# reach Other's memory macro.
for m in Outer Other; do
    name="partition_${m}_memories"
    if ! diff -r "$(pick "$name" "${before[@]}")" "$(pick "$name" "${after[@]}")" >&2; then
        echo "FAIL: $name changed for an edit inside Inner" >&2
        exit 1
    fi
done
if ! grep -q "^ram_64x16 " "$(pick partition_Other_memories "${after[@]}")/memories/blackboxes.txt"; then
    echo "FAIL: Other's slice did not find its memory" >&2
    exit 1
fi
if [ -s "$(pick partition_Outer_memories "${after[@]}")/memories/blackboxes.txt" ]; then
    echo "FAIL: Outer's slice has memories it does not hold" >&2
    exit 1
fi

# Without this the test passes vacuously.
for name in partition_Inner_slice.v partition_Inner_canonical.rtlil; do
    if cmp -s "$(pick "$name" "${before[@]}")" "$(pick "$name" "${after[@]}")"; then
        echo "FAIL: $name did not change; after.v edits nothing" >&2
        exit 1
    fi
done
echo PASS
