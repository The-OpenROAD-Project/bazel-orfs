#!/bin/bash
# Each slice's top module (partition_<module>_slice.rtlil among the
# arguments), the design's top included, is in the slice's
# canonicalized RTLIL as it is in the whole design's, byte for byte.
set -euo pipefail
global=$1
shift

module() {
    M="module $2" awk '$0 == ENVIRON["M"] { on = 1 } on { print } on && $0 == "end" { exit }' "$1"
}

checked=0
for slice in "$@"; do
    case "$slice" in
    *_slice.rtlil) ;;
    *) continue ;;
    esac
    checked=$((checked + 1))
    name=$(awk 'prev == "attribute \\top 1" && /^module / { print $2 } { prev = $0 }' "$slice")
    if [ -z "$name" ]; then
        echo "FAIL: no top module in $(basename "$slice")" >&2
        exit 1
    fi
    if ! diff <(module "$global" "$name") <(module "$slice" "$name") > /dev/null ||
        [ -z "$(module "$slice" "$name")" ]; then
        echo "FAIL: $name differs between the global and the slice path" >&2
        diff <(module "$global" "$name") <(module "$slice" "$name") | head -20 >&2
        exit 1
    fi
done
if [ "$checked" = 0 ]; then
    echo "FAIL: no slice RTLIL" >&2
    exit 1
fi
echo PASS
