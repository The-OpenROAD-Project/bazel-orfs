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
            # Extract output filenames from write_db/write_sdc/write_verilog/write_spef
            # calls that write to $::env(RESULTS_DIR)/
            for ext in odb sdc v spef; do
                grep -oE "(orfs_write_db|write_db|write_sdc|write_verilog|write_spef)\s+.*\.$ext" "$arg" 2>/dev/null | while IFS= read -r line; do
                    fname=$(echo "$line" | grep -oE "[^/]*\.$ext" | tail -1)
                    if [ -n "$fname" ]; then
                        mkdir -p "$RESULTS_DIR"
                        touch "$RESULTS_DIR/$fname"
                    fi
                done
            done

            # generate_abstract.tcl writes .lef and .lib using $::env(DESIGN_NAME)
            if grep -q "write_abstract_lef\|write_timing_model" "$arg" 2>/dev/null && [ -n "$DESIGN_NAME" ]; then
                mkdir -p "$RESULTS_DIR"
                touch "$RESULTS_DIR/${DESIGN_NAME}.lef"
                touch "$RESULTS_DIR/${DESIGN_NAME}_typ.lib"
            fi
        fi
    done
fi

echo "mock openroad (CI stub)"
exit 0
