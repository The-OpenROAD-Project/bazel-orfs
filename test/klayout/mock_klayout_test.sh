#!/bin/bash
set -e

KLAYOUT="$1"
OUTDIR="$(mktemp -d)"
OUTFILE="$OUTDIR/test.gds"

# Test that mock klayout creates a GDS file when invoked with -rd out=...
"$KLAYOUT" -b -r dummy.py -rd out="$OUTFILE"

if [ ! -f "$OUTFILE" ]; then
    echo "FAIL: mock klayout did not create output file"
    rm -rf "$OUTDIR"
    exit 1
fi

if [ ! -s "$OUTFILE" ]; then
    echo "FAIL: output GDS file is empty"
    rm -rf "$OUTDIR"
    exit 1
fi

echo "PASS: mock klayout created dummy GDS file"
rm -rf "$OUTDIR"
