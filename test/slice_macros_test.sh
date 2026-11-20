#!/bin/bash
# A slice's RTLIL holds the macros the slice stubs and no other: the top's
# slice does not reach the macro, lb_32x128_top's does.
set -euo pipefail

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

if grep -q '^module \\lb_32x128$' "$(pick partition_lb_32x128_keep_top_slice.rtlil "$@")"; then
    echo "FAIL: the top's slice holds the macro lb_32x128 it does not reach" >&2
    exit 1
fi
if ! grep -q '^module \\lb_32x128$' "$(pick partition_lb_32x128_top_canonical.rtlil "$@")"; then
    echo "FAIL: lb_32x128_top's slice lacks the macro it instantiates" >&2
    exit 1
fi
