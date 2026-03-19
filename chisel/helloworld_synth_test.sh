#!/bin/sh
# Verify that Chisel HelloWorld synthesis produces outputs.
set -e

has_odb=false

for f in "$@"; do
    case "$f" in
        *.odb) has_odb=true ;;
    esac
done

if [ "$has_odb" != true ]; then
    echo "FAIL: no .odb file found in synthesis output"
    echo "Files provided: $*"
    exit 1
fi

echo "PASS: synthesis produced .odb database"
