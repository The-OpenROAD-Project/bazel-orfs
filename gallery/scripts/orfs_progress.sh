#!/bin/bash
# orfs_progress.sh — Show what ORFS subcommand is currently running inside bazel.
#
# Usage: scripts/orfs_progress.sh
#
# Finds running ORFS processes by looking for tee'd log files, then tails them.

set -euo pipefail

echo "=== Active ORFS processes ==="

# Find tee processes that indicate ORFS subcommands running
TEES=$(ps -Af | grep '[t]ee.*\.log' || true)

if [[ -z "$TEES" ]]; then
    echo "No active ORFS processes found."
    exit 0
fi

echo "$TEES"
echo

# Extract .log.tmp or .log paths and tail the most recent one
LOG=$(echo "$TEES" | grep -oP '/\S+\.log(\.\S+)?' | head -1)
if [[ -n "$LOG" && -f "$LOG" ]]; then
    echo "=== Tailing: $LOG ==="
    tail -20 "$LOG"
fi
