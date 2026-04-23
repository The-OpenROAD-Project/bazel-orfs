#!/bin/sh
# Verify dual-characterization distinction survived scaling:
#   (a) library() names agree between the two .lib files
#   (b) post-CTS clock-tree arc values are strictly greater than pre-layout
#       (which should be ~0).
set -e

post="$1"
pre="$2"

if [ ! -f "$post" ] || [ ! -f "$pre" ]; then
    echo "FAIL: expected two .lib files, got: $*"
    exit 1
fi

post_lib_name=$(grep -m1 '^library(' "$post" | sed 's/.*library(\([^)]*\)).*/\1/')
pre_lib_name=$(grep -m1  '^library(' "$pre"  | sed 's/.*library(\([^)]*\)).*/\1/')
if [ "$post_lib_name" != "$pre_lib_name" ]; then
    echo "FAIL: library() names differ: post='$post_lib_name' pre='$pre_lib_name'"
    exit 1
fi

# Extract the first max_clock_tree_path values("...") from each file.
extract_ck () {
    awk '
        /timing_type *: *max_clock_tree_path/ { flag = 1; next }
        flag && /values/ {
            match($0, /values *\(\s*"([-0-9.e+]+)"/, arr)
            if (arr[1] != "") { print arr[1]; exit }
        }
    ' "$1"
}

post_ck=$(extract_ck "$post")
pre_ck=$(extract_ck "$pre")

if [ -z "$post_ck" ] || [ -z "$pre_ck" ]; then
    echo "FAIL: could not extract max_clock_tree_path from both files"
    echo "  post: $post_ck"
    echo "  pre:  $pre_ck"
    exit 1
fi

awk -v p="$post_ck" -v q="$pre_ck" 'BEGIN{
    if (p+0 > q+0) {
        printf "PASS: post-CTS ck-insertion %s > pre-layout %s\n", p, q
        exit 0
    }
    printf "FAIL: post-CTS ck-insertion %s not > pre-layout %s\n", p, q
    exit 1
}'
