#!/bin/bash
# orfs_reports.sh — Find and display ORFS report files for a given build target.
#
# Usage: scripts/orfs_reports.sh <bazel_target> [report_pattern]
#
# Examples:
#   scripts/orfs_reports.sh //vlsiffra:multiplier_synth
#   scripts/orfs_reports.sh //vlsiffra:multiplier_final "*.rpt"
#   scripts/orfs_reports.sh //vlsiffra:multiplier_route timing

set -euo pipefail

TARGET="${1:?Usage: orfs_reports.sh <bazel_target> [report_pattern]}"
PATTERN="${2:-}"

# Get the output directory for the target
OUTPUT_DIR=$(bazelisk cquery "$TARGET" --output=files 2>/dev/null | head -1)

if [[ -z "$OUTPUT_DIR" ]]; then
    echo "ERROR: Could not find output for $TARGET" >&2
    exit 1
fi

# The output is a file; go up to the target's results directory
RESULTS_DIR=$(dirname "$OUTPUT_DIR")

echo "=== Output directory: $RESULTS_DIR ==="
echo

if [[ -n "$PATTERN" ]]; then
    # Search for specific pattern in report files
    find "$RESULTS_DIR" -type f \( -name "*.rpt" -o -name "*.txt" -o -name "*.log" \) \
        -exec grep -l "$PATTERN" {} + 2>/dev/null || echo "No files matching pattern '$PATTERN'"
else
    # List all report files
    find "$RESULTS_DIR" -type f \( -name "*.rpt" -o -name "*.txt" -o -name "*.log" -o -name "*.json" \) \
        -printf "%f\t%s\t%p\n" 2>/dev/null | sort | column -t
fi
