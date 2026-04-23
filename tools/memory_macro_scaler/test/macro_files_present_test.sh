#!/bin/sh
# Verify that the scaled orfs_macro()'s files include at least one .lef
# and at least one .lib. Mirrors the shape of //test:macro_test.sh without
# requiring the latter to be publicly exported.
set -e

has_lef=false
has_lib=false
for f in "$@"; do
    case "$f" in
        *.lef) has_lef=true ;;
        *.lib) has_lib=true ;;
    esac
done

fail=false
if [ "$has_lef" != true ]; then
    echo "FAIL: no .lef file in scaled orfs_macro() outputs"
    fail=true
fi
if [ "$has_lib" != true ]; then
    echo "FAIL: no .lib file in scaled orfs_macro() outputs"
    fail=true
fi
if [ "$fail" = true ]; then
    echo "Files provided: $*"
    exit 1
fi

echo "PASS: .lef and .lib files present"
