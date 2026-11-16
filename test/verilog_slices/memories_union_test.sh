#!/bin/bash
# The memories the slices' union gives the merge and every later stage are
# the whole design's detection's, byte for byte, but for the date FakeRAM
# writes into a Liberty view, which the union leaves out, and the register
# files' generator scripts (*.tcl), which are no view.
set -euo pipefail
global_json=$1 global_dir=$2 union_json=$3 union_dir=$4

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

cmp -s "$global_json" "$union_json" || {
    diff "$global_json" "$union_json" | head -20 >&2
    fail "memories.json differs"
}

views() {
    (cd "$1" && find -L . -type f ! -name '*.tcl' | sort)
}
[ "$(views "$global_dir")" = "$(views "$union_dir")" ] || {
    diff <(views "$global_dir") <(views "$union_dir") >&2
    fail "the views differ"
}
[ -n "$(views "$union_dir" | grep '\.lib$')" ] || fail "no memory became a macro"

undated() {
    sed -E 's/^(\s*date\s*:\s*")[^"]*(";)/\1\2/' "$1"
}
while read -r f; do
    if [[ "$f" == *.lib ]]; then
        cmp -s <(undated "$global_dir/$f") "$union_dir/$f" || fail "$f differs"
    else
        cmp -s "$global_dir/$f" "$union_dir/$f" || fail "$f differs"
    fi
done < <(views "$union_dir")
echo PASS
