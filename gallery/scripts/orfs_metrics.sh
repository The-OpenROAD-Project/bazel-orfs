#!/bin/bash
# orfs_metrics.sh — Extract key metrics from ORFS build output.
#
# Usage: scripts/orfs_metrics.sh <project> <top_module>
#
# Extracts: cell count, area, WNS, TNS, power from available report files.

set -euo pipefail

PROJECT="${1:?Usage: orfs_metrics.sh <project> <top_module>}"
TOP="${2:?Usage: orfs_metrics.sh <project> <top_module>}"

echo "=== ORFS Metrics for //${PROJECT}:${TOP} ==="
echo

# Find the bazel output base
OUTBASE=$(bazelisk info output_path 2>/dev/null)/k8-opt/bin

# Check each stage's output
for STAGE in synth floorplan place cts grt route final; do
    STAGE_DIR="${OUTBASE}/${PROJECT}/${TOP}_${STAGE}"
    if [[ -d "$STAGE_DIR" ]]; then
        echo "--- ${STAGE} (found) ---"

        # Synthesis stats
        if [[ "$STAGE" == "synth" ]]; then
            STAT_FILE=$(find "$STAGE_DIR" -name "synth_stat.txt" -o -name "*_synth.stats" 2>/dev/null | head -1)
            if [[ -n "$STAT_FILE" ]]; then
                echo "  Synth stats: $STAT_FILE"
                # Extract cell count
                grep -i "number of cells" "$STAT_FILE" 2>/dev/null || true
                grep -i "chip area" "$STAT_FILE" 2>/dev/null || true
            fi
        fi

        # Timing reports (any stage)
        for RPT in $(find "$STAGE_DIR" -name "*timing*" -o -name "*report*" 2>/dev/null); do
            if grep -q "wns\|WNS\|worst.*slack" "$RPT" 2>/dev/null; then
                echo "  Timing: $RPT"
                grep -i "wns\|tns\|worst.*slack\|total.*slack" "$RPT" 2>/dev/null | head -5
            fi
        done

        # Power reports
        for RPT in $(find "$STAGE_DIR" -name "*power*" 2>/dev/null); do
            echo "  Power: $RPT"
            grep -i "total\|internal\|switching\|leakage" "$RPT" 2>/dev/null | head -5
        done

        # Area reports
        for RPT in $(find "$STAGE_DIR" -name "*area*" -o -name "*final_report*" 2>/dev/null); do
            echo "  Area: $RPT"
            grep -i "design area\|total area\|utilization" "$RPT" 2>/dev/null | head -5
        done
    fi
done
