#!/bin/sh
# Mock openroad binary for testing the openroad override mechanism.
#
# Creates dummy .odb output files so the ORFS flow can proceed.
# The flow script sets RESULTS_DIR and the TCL scripts write
# <stage>.odb files there.

case "$1" in
    -version)
        echo "OpenROAD v0.0.0 (mock)"
        exit 0
        ;;
    -help)
        echo "mock openroad (CI stub)"
        exit 0
        ;;
esac

# Create any .odb files referenced in the TCL scripts via $env(RESULTS_DIR)
if [ -n "$RESULTS_DIR" ]; then
    for arg in "$@"; do
        if [ -f "$arg" ]; then
            # Extract output filenames from write_db/write_sdc calls
            for ext in odb sdc; do
                grep -oE "(orfs_write_db|write_db|write_sdc)\s+.*\.$ext" "$arg" 2>/dev/null | while IFS= read -r line; do
                    fname=$(echo "$line" | grep -oE "[^/]*\.$ext" | tail -1)
                    if [ -n "$fname" ]; then
                        mkdir -p "$RESULTS_DIR"
                        touch "$RESULTS_DIR/$fname"
                    fi
                done
            done
        fi
    done
fi

echo "mock openroad (CI stub)"
exit 0
