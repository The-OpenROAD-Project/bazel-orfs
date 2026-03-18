#!/bin/sh
# Verify that orfs_macro accumulates .lef, .lib, and .gds files.
set -e

has_lef=false
has_lib=false
has_gds=false

for f in "$@"; do
    case "$f" in
        *.lef) has_lef=true ;;
        *.lib) has_lib=true ;;
        *.gds) has_gds=true ;;
    esac
done

fail=false
if [ "$has_lef" != true ]; then
    echo "FAIL: no .lef file found"
    fail=true
fi
if [ "$has_lib" != true ]; then
    echo "FAIL: no .lib file found"
    fail=true
fi
if [ "$has_gds" != true ]; then
    echo "FAIL: no .gds file found"
    fail=true
fi

if [ "$fail" = true ]; then
    echo "Files provided: $*"
    exit 1
fi

echo "PASS: .lef, .lib, and .gds files present"
